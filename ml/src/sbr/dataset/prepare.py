"""Build training trees from the pooled dataset, per role.

The interesting thing here is the splitting, and it is interesting because the
predecessor got it wrong in a way that made its headline number meaningless: a
random 20 % split of 466 photos taken in one city in one week measures
memorisation, not generalisation.

Three rules fix that:

1. **Group-aware.** Frames are grouped by capture cluster – one visit to one
   bin, reconstructed from EXIF capture times in ``legacy_import``. A group
   lands entirely in one split. Without it the model sees a bin in training and
   is tested on the next frame of the same bin.
2. **Region holdout.** Whole cities are excluded from train and val and kept as
   their own evaluated split. This is the number that predicts launch behaviour.
3. **Annotator holdout, optionally.** Annotator style is a plausible confound
   and the archive hands us the grouping key for free, so it can be swapped in
   as the grouping dimension to check for it.

Two roles, two trees, because the models are different shapes:

- the **validator** gets a YOLO detection tree, one class, ``bin``, with the
  negative corpus mixed in as background images;
- the **identifier** gets a **classification** tree, ``split/<form_factor>/``,
  built only from adjudicated crops.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sbr.dataset.pool import crop_path, image_path, label_path, layout_of
from sbr.taxonomy import load_taxonomy

logger = logging.getLogger(__name__)

SPLITS = ("train", "val", "test", "holdout_region", "holdout_annotator")

#: Below this share of the pool, a split is too small to mean anything and the
#: caller is told rather than left to read it off a summary line later.
DEGENERATE_SPLIT_SHARE = 0.05

#: Below this many frames per group, "group-aware" is a random split wearing a
#: group-aware label. 1.5 is deliberately generous: the legacy pool runs at ~3.7
#: (370 frames, 100 clusters) and video pools should run at tens or hundreds.
MIN_FRAMES_PER_GROUP = 1.5

#: Small pools legitimately have one frame per group – 40 unrelated photographs
#: are 40 groups and that is correct. Only judge the grouping once there is
#: enough data for the question to be meaningful.
MIN_FRAMES_TO_JUDGE_GROUPING = 200

#: The validator's entire class list. It is class-agnostic on purpose: it must
#: fire on a bin type it has never seen, because that is exactly the case the
#: improvement loop depends on detecting.
VALIDATOR_CLASSES = ["bin"]

#: A crop may train the identifier only with one of these. "pending" may not.
ADJUDICATED = {"confirmed", "corrected"}


@dataclass(frozen=True)
class Record:
    """One frame in the pool."""

    file: str
    region_id: str
    capture_cluster: str
    boxes: int
    annotator: str | None = None
    bins_in_frame: int = 0

    @classmethod
    def from_manifest(cls, entry: dict[str, Any]) -> Record:
        cluster = entry.get("capture_cluster")

        # Video frames are the dangerous case, so they get an explicit path.
        #
        # Consecutive frames of one walk-around are near-identical. If they land
        # in different splits the test set is the training set, mAP goes to 0.99
        # and means nothing - which is precisely the predecessor's failure
        # (docs/08 7.3), reproduced at a hundred times the scale and just as
        # invisible. The tightest honest group is the TRACK: one physical bin
        # through one video. The video is the fallback when tracks are absent.
        video = entry.get("video_id")
        if not cluster and video:
            track = entry.get("track_id")
            cluster = f"video/{video}/{track}" if track else f"video/{video}"

        if not cluster:
            if entry.get("source") == "video":
                raise ValueError(
                    f"{entry['file']} declares source 'video' but carries no "
                    "video_id, track_id or capture_cluster. Splitting it would "
                    "put near-identical frames on both sides of the split and "
                    "report memorisation as generalisation."
                )
            # A frame with no cluster is its own cluster. Falling back to a
            # filename prefix here is how "group-aware" silently becomes either
            # a random split or one giant group.
            cluster = f"unclustered/{entry['file']}"

        return cls(
            file=entry["file"],
            region_id=entry.get("region_id", "unknown"),
            capture_cluster=cluster,
            boxes=entry.get("boxes", 0),
            annotator=entry.get("annotator"),
            bins_in_frame=entry.get("bins_in_frame", entry.get("boxes", 0)),
        )


def _bucket(key: str, buckets: int = 1000) -> int:
    """Stable hash bucket – deterministic across machines and Python versions."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % buckets


def assign_splits(
    records: Iterable[Record],
    train: float = 0.70,
    val: float = 0.15,
    holdout_regions: Iterable[str] = (),
    holdout_annotators: Iterable[str] = (),
    group_by: str = "capture_cluster",
) -> dict[str, str]:
    """Map each file to one of :data:`SPLITS`.

    Assignment is by group, so every frame of one capture cluster shares a split.

    Holdouts are **named**, not hashed. That matters for annotators: this archive
    has three of them, and hashing three groups into 70/15/15 gives 369/1/0 – a
    knob that looks like a confound check and is not one. Naming the annotator to
    hold out is the only version of that check which works at this scale.
    """
    if group_by not in ("capture_cluster", "annotator", "region_id"):
        raise ValueError(f"cannot group by {group_by!r}")

    held_regions = set(holdout_regions)
    held_annotators = set(holdout_annotators)
    grouped: dict[str, list[Record]] = defaultdict(list)
    records = list(records)
    for record in records:
        key = getattr(record, group_by) or f"unknown/{record.file}"
        grouped[key].append(record)

    assignment: dict[str, str] = {}
    train_cut = int(train * 1000)
    val_cut = int((train + val) * 1000)

    for group, members in grouped.items():
        if any(r.region_id in held_regions for r in members):
            split = "holdout_region"
        elif held_annotators and any(r.annotator in held_annotators for r in members):
            split = "holdout_annotator"
        else:
            bucket = _bucket(group)
            split = "train" if bucket < train_cut else "val" if bucket < val_cut else "test"
        for record in members:
            assignment[record.file] = split

    counts: Counter[str] = Counter(assignment.values())
    total = len(assignment)
    frames_per_group = total / len(grouped) if grouped else 0
    logger.info(
        "split by %s: %d groups over %d frames (%.1f frames/group) -> %s",
        group_by, len(grouped), total, frames_per_group, dict(sorted(counts.items())),
    )

    # A group-aware split where almost every frame is its own group IS a random
    # split, and it is silent: the numbers look better, not worse. Cheap to say
    # out loud, expensive to discover in a results table six weeks later.
    if total >= MIN_FRAMES_TO_JUDGE_GROUPING and frames_per_group < MIN_FRAMES_PER_GROUP:
        logger.warning(
            "grouping by %r yields %.2f frames per group over %d frames – this is "
            "effectively a RANDOM split, and near-identical frames will straddle "
            "it. If these came from video, group by track or video id.",
            group_by, frames_per_group, total,
        )

    for split in ("train", "val", "test"):
        share = counts.get(split, 0) / total if total else 0
        if share < DEGENERATE_SPLIT_SHARE:
            logger.warning(
                "split %r holds %d of %d frames (%.1f %%) – too few to measure "
                "anything with. Check the grouping key: %d groups over %d frames.",
                split, counts.get(split, 0), total, share * 100, len(grouped), total,
            )
    return assignment


def split_config(config: dict[str, Any]) -> dict[str, Any]:
    data = config.get("data", {})
    split = data.get("split", {})
    return {
        "train": split.get("train", 0.70),
        "val": split.get("val", 0.15),
        "holdout_regions": data.get("holdout_regions", ()) or (),
        "holdout_annotators": data.get("holdout_annotators", ()) or (),
        "group_by": split.get("group_by", "capture_cluster"),
    }


def load_manifest(pool_dir: Path) -> dict[str, Any]:
    return json.loads((pool_dir / "manifest.json").read_text(encoding="utf-8"))


def discover_pools(root: Path) -> list[Path]:
    """Every subset under a dataset snapshot, in a stable order.

    The HF dataset repo holds one directory per subset – ``legacy/``,
    ``open_images/``, ``negatives/`` – each a self-contained pool with its own
    manifest and its own provenance. Keeping them separate is what lets a
    subset's contribution be measured, and rolled back if it turns out to hurt.
    """
    if (root / "manifest.json").exists():
        return [root]
    pools = sorted(p.parent for p in root.glob("*/manifest.json"))
    if not pools:
        raise FileNotFoundError(f"no pool manifests under {root}")
    logger.info("pools: %s", [p.name for p in pools])
    return pools


def load_pool_manifests(pools: Iterable[Path]) -> list[tuple[Path, dict[str, Any]]]:
    """``(pool_dir, manifest)`` per subset, parsed exactly once.

    Once matters: the harvested negatives manifest is 13 MB of provenance, and
    both builders want the records, the crop records and the layout out of it.
    """
    return [(pool, load_manifest(pool)) for pool in pools]


def load_pool_records(
    manifests: Iterable[tuple[Path, dict[str, Any]]]
) -> list[tuple[Path, dict[str, Any]]]:
    """``(pool_dir, record)`` for every frame across every subset.

    Filenames are only unique within a subset, so the pool directory travels
    with each record rather than being resolved later.
    """
    return [(pool, entry) for pool, manifest in manifests for entry in manifest["records"]]


def _qualified(pool: Path, file: str) -> str:
    """A name unique across subsets, used as the training-tree filename."""
    return f"{pool.name}__{file}"


# --------------------------------------------------------------------------- #
# Model A – detection tree
# --------------------------------------------------------------------------- #


def build_yolo_tree(pool_root: Path, out_dir: Path, config: dict[str, Any]) -> Path:
    """Materialise a YOLO detection tree and its ``data.yaml`` for the validator.

    ``pool_root`` is either one pool or a dataset snapshot holding several
    subsets. Frames with no boxes are kept, not dropped: an image with an empty
    label file is a background image, and the negative corpus is most of what
    buys the validator its precision.
    """
    manifests = load_pool_manifests(discover_pools(pool_root))
    layouts = {pool: layout_of(manifest) for pool, manifest in manifests}
    entries = load_pool_records(manifests)

    records = []
    origin: dict[str, Path] = {}
    source_name: dict[str, str] = {}
    for pool, entry in entries:
        qualified = _qualified(pool, entry["file"])
        record = Record.from_manifest({**entry, "file": qualified})
        records.append(record)
        origin[qualified] = pool
        source_name[qualified] = entry["file"]

    assignment = assign_splits(records, **split_config(config))

    # The tree written here is deliberately FLAT, unlike the sharded pools it is
    # assembled from. It is local scratch that ultralytics reads directly and
    # that is never pushed anywhere, so the Hub's 10 000-file cap does not apply
    # and YOLO's `images/train` <-> `labels/train` convention does.
    for split in SPLITS:
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    per_split: Counter[str] = Counter()
    per_pool: Counter[str] = Counter()
    negatives = 0
    for record in records:
        split = assignment[record.file]
        pool = origin[record.file]
        per_split[split] += 1
        per_pool[pool.name] += 1

        original = source_name[record.file]
        layout = layouts[pool]
        shutil.copy2(image_path(pool, original, layout), out_dir / "images" / split / record.file)

        source_label = label_path(pool, Path(original).stem, layout)
        target_label = out_dir / "labels" / split / f"{Path(record.file).stem}.txt"
        if source_label.exists():
            shutil.copy2(source_label, target_label)
        else:
            # A background image. YOLO wants the file to exist and be empty.
            target_label.write_text("", encoding="utf-8")
            negatives += 1

    classes = resolve_classes(config)
    data_yaml = {
        "path": str(out_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": len(classes),
        "names": dict(enumerate(classes)),
    }
    if (out_dir / "images" / "holdout_region").exists() and per_split.get("holdout_region"):
        data_yaml["holdout_region"] = "images/holdout_region"

    data_path = out_dir / "data.yaml"
    data_path.write_text(yaml.safe_dump(data_yaml, sort_keys=False), encoding="utf-8")

    positives = len(records) - negatives
    (out_dir / "composition.json").write_text(
        json.dumps(
            {
                "per_split": dict(sorted(per_split.items())),
                "per_pool": dict(sorted(per_pool.items())),
                "positives": positives,
                "background_images": negatives,
                "negative_ratio": round(negatives / positives, 1) if positives else None,
                "classes": classes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    logger.info(
        "wrote %s: %d classes %s, splits %s, pools %s, %d positives + %d background (%.1f:1)",
        data_path, len(classes), classes, dict(sorted(per_split.items())),
        dict(sorted(per_pool.items())), positives, negatives,
        negatives / positives if positives else 0,
    )
    return data_path


def resolve_classes(config: dict[str, Any]) -> list[str]:
    """The class list for a role, and never the wrong one.

    ``classes_from_taxonomy`` is what separates the two models: the identifier's
    classes are the form factors in file order – that order is the ONNX class
    index – while the validator has exactly one class and must not be handed ten.
    """
    data = config.get("data", {})
    if data.get("classes_from_taxonomy"):
        return load_taxonomy().detector_classes
    declared = data.get("classes")
    if declared:
        return list(declared)
    raise ValueError(
        "config declares neither data.classes nor data.classes_from_taxonomy; "
        "refusing to guess a class list"
    )


# --------------------------------------------------------------------------- #
# Model B – classification tree
# --------------------------------------------------------------------------- #


def build_classification_tree(pool_root: Path, out_dir: Path, config: dict[str, Any]) -> Path:
    """Materialise ``split/<form_factor>/`` from **adjudicated** crops only.

    A crop whose form factor was inferred from a legacy stream label is not a
    label. It carries ``adjudication: "pending"`` and is skipped here, loudly.
    """
    manifests = load_pool_manifests(discover_pools(pool_root))

    frames = [
        Record.from_manifest({**entry, "file": _qualified(pool, entry["file"])})
        for pool, entry in load_pool_records(manifests)
    ]
    assignment = assign_splits(frames, **split_config(config))

    require = config.get("data", {}).get("require_adjudication", True)
    classes = resolve_classes(config)

    kept: Counter[str] = Counter()
    per_split: Counter[str] = Counter()
    skipped_pending = skipped_unknown = 0

    for pool, manifest in manifests:
        layout = layout_of(manifest)
        for crop in manifest.get("crop_records", []):
            state = crop.get("adjudication")
            form_factor = crop.get("form_factor")
            if require and state not in ADJUDICATED:
                skipped_pending += 1
                continue
            if not form_factor or form_factor not in classes:
                skipped_unknown += 1
                continue

            # The crop inherits its frame's split, so a crop and the frame it
            # came from can never straddle one.
            split = assignment.get(_qualified(pool, crop["frame"]))
            if split is None:
                continue

            destination = out_dir / split / form_factor
            destination.mkdir(parents=True, exist_ok=True)
            name = _qualified(pool, crop["file"])
            shutil.copy2(crop_path(pool, crop["file"], layout), destination / name)
            kept[form_factor] += 1
            per_split[split] += 1

    if skipped_pending:
        logger.warning(
            "%d crops skipped: still pending adjudication. Run "
            "`python ml/scripts/adjudicate.py` – the identifier cannot be trained "
            "on a form factor nobody confirmed.",
            skipped_pending,
        )
    if skipped_unknown:
        logger.warning("%d crops skipped: no usable form factor", skipped_unknown)
    if not kept:
        raise SystemExit(
            "no adjudicated crops - there is nothing to train the identifier on.\n"
            "This is the expected state until the human pass is done; the "
            "validator does not depend on it."
        )

    missing = [c for c in classes if c not in kept]
    if missing:
        logger.warning(
            "%d of %d form factors have no crops at all: %s. The identifier will "
            "ship supporting fewer classes than the taxonomy defines, and the "
            "results doc must name which.",
            len(missing), len(classes), missing,
        )

    summary = {
        "classes_present": dict(sorted(kept.items())),
        "classes_absent": missing,
        "per_split": dict(sorted(per_split.items())),
        "skipped_pending_adjudication": skipped_pending,
        "skipped_no_form_factor": skipped_unknown,
    }
    (out_dir / "classification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("classification tree: %s", summary)
    return out_dir


def bins_per_frame_buckets(
    records: Iterable[Record], assignment: dict[str, str], split: str
) -> dict[str, list[str]]:
    """Files in ``split``, bucketed by how many bins are in the frame.

    docs/04 § 5 commits to reporting detection recall this way, so that a model
    which only works on one big centred bin cannot hide behind an aggregate.
    """
    buckets: dict[str, list[str]] = defaultdict(list)
    for record in records:
        if assignment.get(record.file) != split:
            continue
        count = record.bins_in_frame
        buckets["4+" if count >= 4 else str(count)].append(record.file)
    return dict(sorted(buckets.items()))
