"""The legacy archive's contract, so an incomplete copy fails loudly.

This module exists because it already went wrong twice. ``legacy_import.py`` was
written against an incomplete copy and said so at the top; ``docs/08 § 7.1`` then
recorded an inventory that does not describe the published release asset either.
Both were honest mistakes with the same shape: code and prose asserting a layout
that nobody had checked against the artefact people would actually download.

So the layout is now data (``ml/configs/legacy_archive.yaml``), :func:`inventory`
measures it, and :func:`verify` refuses to proceed on any mismatch.

What the published archive actually is
--------------------------------------
``cv_garbage.zip`` from release ``v1.0.0`` is a **partial** copy of the dataset
the predecessor trained on:

- ``YOLO_Dataset/labels/`` holds **401** of the 466 label files.
- ``YOLO_Dataset/images/`` holds **16** images, not 466.
- ``labeled/<person>/`` holds **427** images – this is where the pixels are.
- ``raw_images/`` holds 258 originals and contributes no label pairing at all.
- ``labeled/labels.csv`` has all **466** rows: original name, renamed file,
  class, annotation timestamp.
- **370** labels can be paired with an image. That is the usable dataset.

That the full 466 once existed is not in doubt: the Ultralytics label caches
shipped inside the archive record ``results=(372, 0, 0, 0, 372)`` for train and
``(94, 0, 0, 0, 94)`` for val – 466 images, nothing missing, at training time.
The publishing step is what lost them.

How things are linked
---------------------
Nothing pairs by filename. Label Studio renamed every image to
``<Class>_<hash8>.<ext>`` and then exported labels as
``<taskid8>-<Class-with-utf8-bytes-escaped>_<hash8>.txt``. The **trailing eight
hex characters are the join key**, and they are the only part of the name that
is neither mojibake nor percent-escaped.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}

#: The predecessor's class index order, from cv_garbage/2-Computer-Vision.py:323
#: and confirmed by YOLO_Dataset/classes.txt. The index in a label file is an
#: index into this list; it is permanent.
LEGACY_CLASS_ORDER = ["Biomüll", "Glas", "Papier", "Restmüll"]

#: Label Studio escapes non-ASCII bytes in exported filenames as ``_XX`` pairs,
#: upper-case hex. ``Restm_C3_BCll`` is ``Restmüll``.
#:
#: The first nibble is restricted to ``[89A-F]`` deliberately. Only bytes ≥ 0x80
#: are ever escaped – they are what "non-ASCII" means – and without that bound
#: the pattern eats the join key: ``Papier_00d305ba`` would decode ``_00`` to a
#: NUL and hand back a hash that pairs with nothing.
_ESCAPED_BYTES = re.compile(r"(?:_[89A-F][0-9A-F])+")


def decode_export_name(stem: str) -> str:
    """Undo Label Studio's ``_XX`` byte escaping in an exported filename."""

    def replace(match: re.Match[str]) -> str:
        pairs = match.group(0).split("_")[1:]
        return bytes(int(p, 16) for p in pairs).decode("utf-8", errors="replace")

    return _ESCAPED_BYTES.sub(replace, stem)


def join_key(name: str) -> str:
    """The eight-hex tail that links a label to its image.

    This is the only reliable link in the archive: image names are mojibake on
    any filesystem that is not the one they were written on, and label names
    carry both a task id prefix and an escaped class.
    """
    return Path(name).stem.split("_")[-1].lower()


def class_from_export_name(name: str) -> str | None:
    """The class Label Studio baked into a label filename, or None."""
    stem = decode_export_name(Path(name).stem)
    stem = stem.split("-", 1)[1] if "-" in stem else stem
    candidate = stem.rsplit("_", 1)[0]
    return candidate if candidate in LEGACY_CLASS_ORDER else None


# --------------------------------------------------------------------------- #
# Reading the archive
# --------------------------------------------------------------------------- #


def find_root(path: Path) -> Path:
    """Accept either the extracted parent or ``cv_garbage/`` itself."""
    if (path / "YOLO_Dataset").is_dir():
        return path
    nested = path / "cv_garbage"
    if (nested / "YOLO_Dataset").is_dir():
        return nested
    raise FileNotFoundError(
        f"no YOLO_Dataset/ under {path} or {nested} – point --archive-dir at the "
        "extracted cv_garbage archive"
    )


def read_labels_csv(root: Path) -> list[dict[str, str]]:
    """``labeled/labels.csv``: original name, renamed file, class, timestamp.

    It is UTF-8 and it is the archive's best provenance: it is the only place the
    original camera filename survives, and it covers all 466 images including the
    ones whose pixels did not make it into the release.
    """
    path = root / "labeled" / "labels.csv"
    if not path.exists():
        return []
    raw = path.read_bytes()
    for encoding in ("utf-8", "cp1252"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "�" in text:
            continue
        logger.debug("labels.csv decoded as %s", encoding)
        return list(csv.DictReader(io.StringIO(text)))
    raise ValueError(f"cannot decode {path} as utf-8 or cp1252")


def read_boxes(label: Path) -> list[tuple[int, float, float, float, float]]:
    """Parse a YOLO label file into ``(class_id, cx, cy, w, h)`` tuples."""
    boxes: list[tuple[int, float, float, float, float]] = []
    for line in label.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 5:
            boxes.append((int(parts[0]), *(float(v) for v in parts[1:5])))  # type: ignore[arg-type]
    return boxes


def read_cache_results(root: Path) -> dict[str, tuple]:
    """What the Ultralytics label cache says the training run actually saw.

    ``results`` is ``(found, missing, empty, corrupt, total)``. This is the
    evidence that the full 466 existed once, and it is the reason the shortfall
    in the release is a publishing bug rather than a dataset that never was.
    """
    results: dict[str, tuple] = {}
    for split in ("train", "val"):
        path = root / "YOLO_Dataset" / "labels" / f"{split}.cache"
        if not path.exists():
            continue
        try:
            import numpy as np

            cached = np.load(io.BytesIO(path.read_bytes()), allow_pickle=True).item()
            if "results" in cached:
                results[split] = tuple(cached["results"])
        except Exception as error:  # noqa: BLE001 – a stale cache must not stop an import
            logger.debug("could not read %s: %s", path, error)
    return results


@dataclass(frozen=True)
class Pair:
    """One label file and the image it belongs to."""

    key: str
    label: Path
    image: Path
    annotator: str | None
    legacy_split: str
    image_source: str          # "labeled" | "yolo"
    boxes: list[tuple[int, float, float, float, float]]

    @property
    def class_ids(self) -> list[int]:
        return [b[0] for b in self.boxes]


def index_images(root: Path) -> tuple[dict[str, tuple[Path, str]], dict[str, Path]]:
    """Index every available image by join key.

    Returns ``(labeled, yolo)``. ``labeled`` carries the annotator, which is a
    free grouping key and a plausible confound worth being able to hold out.
    """
    labeled: dict[str, tuple[Path, str]] = {}
    labeled_dir = root / "labeled"
    if labeled_dir.is_dir():
        for person in sorted(p for p in labeled_dir.iterdir() if p.is_dir()):
            for image in sorted(person.glob("*")):
                if image.suffix.lower() in IMAGE_SUFFIXES:
                    labeled.setdefault(join_key(image.name), (image, person.name))

    yolo: dict[str, Path] = {}
    for split in ("train", "val"):
        directory = root / "YOLO_Dataset" / "images" / split
        if directory.is_dir():
            for image in sorted(directory.glob("*")):
                if image.suffix.lower() in IMAGE_SUFFIXES:
                    yolo.setdefault(join_key(image.name), image)

    return labeled, yolo


def resolve_pairs(root: Path) -> tuple[list[Pair], list[str]]:
    """Pair every label with an image. Returns ``(pairs, orphan_label_names)``.

    ``labeled/`` wins over ``YOLO_Dataset/images/`` because it carries the
    annotator and holds 427 images against the latter's 16.
    """
    labeled, yolo = index_images(root)
    pairs: list[Pair] = []
    orphans: list[str] = []

    for split in ("train", "val"):
        directory = root / "YOLO_Dataset" / "labels" / split
        if not directory.is_dir():
            continue
        for label in sorted(directory.glob("*.txt")):
            key = join_key(label.name)
            if key in labeled:
                image, annotator = labeled[key]
                source = "labeled"
            elif key in yolo:
                image, annotator, source = yolo[key], None, "yolo"
            else:
                orphans.append(label.name)
                continue
            pairs.append(
                Pair(
                    key=key,
                    label=label,
                    image=image,
                    annotator=annotator,
                    legacy_split=split,
                    image_source=source,
                    boxes=read_boxes(label),
                )
            )

    return pairs, orphans


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ArchiveInventory:
    """Everything worth asserting about the archive, measured rather than assumed."""

    root: Path
    yolo_images: dict[str, int] = field(default_factory=dict)
    yolo_labels: dict[str, int] = field(default_factory=dict)
    labeled_images: dict[str, int] = field(default_factory=dict)
    raw_images: int = 0
    labels_csv_rows: int = 0
    data_yaml_nc: int | None = None
    data_yaml_names: list[str] = field(default_factory=list)
    model_runs: int = 0
    pairable_labels: int = 0
    orphan_labels: list[str] = field(default_factory=list)
    unlabelled_images: list[str] = field(default_factory=list)
    boxes: int = 0
    boxes_per_class: dict[str, int] = field(default_factory=dict)
    bins_per_frame: dict[int, int] = field(default_factory=dict)
    name_class_disagreements: list[str] = field(default_factory=list)
    cache_results: dict[str, tuple] = field(default_factory=dict)

    @property
    def total_labels(self) -> int:
        return sum(self.yolo_labels.values())

    @property
    def total_labeled_images(self) -> int:
        return sum(self.labeled_images.values())

    def summary(self) -> dict[str, Any]:
        return {
            "yolo_images": self.yolo_images,
            "yolo_labels": self.yolo_labels,
            "labeled_images": self.labeled_images,
            "raw_images": self.raw_images,
            "labels_csv_rows": self.labels_csv_rows,
            "data_yaml": {"nc": self.data_yaml_nc, "names": self.data_yaml_names},
            "model_runs": self.model_runs,
            "pairable_labels": self.pairable_labels,
            "orphan_labels": len(self.orphan_labels),
            "unlabelled_images": len(self.unlabelled_images),
            "boxes": self.boxes,
            "boxes_per_class": self.boxes_per_class,
            "bins_per_frame": self.bins_per_frame,
            "name_class_disagreements": len(self.name_class_disagreements),
            "cache_results": {k: list(v) for k, v in self.cache_results.items()},
        }


def _count_images(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def _read_data_yaml(root: Path) -> tuple[int | None, list[str]]:
    path = root / "YOLO_Dataset" / "data.yaml"
    if not path.exists():
        return None, []
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = raw.get("names", {})
    ordered = [names[i] for i in sorted(names)] if isinstance(names, dict) else list(names)
    return raw.get("nc"), ordered


def inventory(archive: Path) -> ArchiveInventory:
    """Measure the archive. No expectations applied – that is :func:`verify`."""
    root = find_root(archive)

    yolo_images = {
        split: _count_images(root / "YOLO_Dataset" / "images" / split) for split in ("train", "val")
    }
    yolo_labels = {
        split: len(list((root / "YOLO_Dataset" / "labels" / split).glob("*.txt")))
        if (root / "YOLO_Dataset" / "labels" / split).is_dir()
        else 0
        for split in ("train", "val")
    }

    labeled_images: dict[str, int] = {}
    labeled_dir = root / "labeled"
    if labeled_dir.is_dir():
        for person in sorted(p for p in labeled_dir.iterdir() if p.is_dir()):
            labeled_images[person.name] = _count_images(person)

    pairs, orphans = resolve_pairs(root)
    paired_keys = {p.key for p in pairs}
    labeled_index, yolo_index = index_images(root)
    unlabelled = sorted(
        (set(labeled_index) | set(yolo_index)) - paired_keys
    )

    boxes_per_class: Counter[str] = Counter()
    bins_per_frame: Counter[int] = Counter()
    total_boxes = 0
    disagreements: list[str] = []
    for pair in pairs:
        bins_per_frame[len(pair.boxes)] += 1
        total_boxes += len(pair.boxes)
        for class_id in pair.class_ids:
            if 0 <= class_id < len(LEGACY_CLASS_ORDER):
                boxes_per_class[LEGACY_CLASS_ORDER[class_id]] += 1
            else:
                disagreements.append(f"{pair.label.name}: class index {class_id} out of range")
        # The class Label Studio baked into the filename should appear among the
        # boxes. Where it does not, one of the two is wrong about that image.
        named = class_from_export_name(pair.label.name)
        if named is not None:
            present = {
                LEGACY_CLASS_ORDER[i] for i in pair.class_ids if 0 <= i < len(LEGACY_CLASS_ORDER)
            }
            if present and named not in present:
                disagreements.append(
                    f"{pair.label.name}: filename says {named!r}, boxes say {sorted(present)}"
                )

    nc, names = _read_data_yaml(root)

    models_dir = root / "models"
    model_runs = len([p for p in models_dir.iterdir() if p.is_dir()]) if models_dir.is_dir() else 0

    return ArchiveInventory(
        root=root,
        yolo_images=yolo_images,
        yolo_labels=yolo_labels,
        labeled_images=labeled_images,
        raw_images=_count_images(root / "raw_images"),
        labels_csv_rows=len(read_labels_csv(root)),
        data_yaml_nc=nc,
        data_yaml_names=names,
        model_runs=model_runs,
        pairable_labels=len(pairs),
        orphan_labels=orphans,
        unlabelled_images=unlabelled,
        boxes=total_boxes,
        boxes_per_class=dict(sorted(boxes_per_class.items())),
        bins_per_frame=dict(sorted(bins_per_frame.items())),
        name_class_disagreements=disagreements,
        cache_results=read_cache_results(root),
    )


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def load_expectations(path: Path | None = None) -> dict[str, Any]:
    """The recorded layout. Measured, not guessed – see the module docstring."""
    import yaml

    from sbr.config import CONFIG_DIR

    path = path or CONFIG_DIR / "legacy_archive.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _compare(problems: list[str], what: str, got: Any, want: Any) -> None:
    if want is not None and got != want:
        problems.append(f"{what}: got {got!r}, expected {want!r}")


def verify(found: ArchiveInventory, expected: dict[str, Any] | None = None) -> list[str]:
    """Return the list of mismatches. Empty means this is the archive we know.

    Every number here was measured from the release asset, so a mismatch means
    one of three things and all of them deserve a stop: the archive changed, the
    extraction was partial, or something is being pointed at the wrong directory.
    """
    want = (expected or load_expectations()).get("expected", {})
    problems: list[str] = []

    for split in ("train", "val"):
        _compare(problems, f"YOLO_Dataset/labels/{split}",
                 found.yolo_labels.get(split, 0), want.get("yolo_labels", {}).get(split))
        _compare(problems, f"YOLO_Dataset/images/{split}",
                 found.yolo_images.get(split, 0), want.get("yolo_images", {}).get(split))

    for person, count in (want.get("labeled_images") or {}).items():
        _compare(problems, f"labeled/{person}", found.labeled_images.get(person, 0), count)
    extra = set(found.labeled_images) - set(want.get("labeled_images") or {})
    if extra:
        problems.append(f"labeled/: unexpected annotator directories {sorted(extra)}")

    _compare(problems, "raw_images/", found.raw_images, want.get("raw_images"))
    _compare(problems, "labeled/labels.csv rows", found.labels_csv_rows, want.get("labels_csv_rows"))
    _compare(problems, "models/ runs", found.model_runs, want.get("model_runs"))
    _compare(problems, "pairable labels", found.pairable_labels, want.get("pairable_labels"))
    _compare(problems, "orphan labels", len(found.orphan_labels), want.get("orphan_labels"))
    _compare(problems, "unlabelled images", len(found.unlabelled_images), want.get("unlabelled_images"))
    _compare(problems, "boxes", found.boxes, want.get("boxes"))

    if (want_classes := want.get("boxes_per_class")) is not None:
        _compare(problems, "boxes per class", found.boxes_per_class, dict(want_classes))
    if (want_frames := want.get("bins_per_frame")) is not None:
        _compare(problems, "bins per frame", found.bins_per_frame,
                 {int(k): v for k, v in want_frames.items()})

    data_yaml = want.get("data_yaml") or {}
    _compare(problems, "data.yaml nc", found.data_yaml_nc, data_yaml.get("nc"))
    if (want_names := data_yaml.get("names")) is not None and found.data_yaml_names != list(want_names):
        # Order is the class index. A reordering here silently remaps every label
        # file in the archive.
        problems.append(
            f"data.yaml names: got {found.data_yaml_names!r}, expected {list(want_names)!r} "
            "– this order IS the class index in every label file"
        )

    return problems


def describe(found: ArchiveInventory) -> str:
    """A human-readable inventory, ASCII-safe for any console."""
    lines = [
        f"archive root        : {found.root}",
        f"YOLO_Dataset labels : {found.yolo_labels} = {found.total_labels}",
        f"YOLO_Dataset images : {found.yolo_images} = {sum(found.yolo_images.values())}",
        f"labeled/ images     : {found.labeled_images} = {found.total_labeled_images}",
        f"raw_images/         : {found.raw_images}",
        f"labels.csv rows     : {found.labels_csv_rows}",
        f"models/ runs        : {found.model_runs}",
        "",
        f"PAIRABLE            : {found.pairable_labels} labels have an image",
        f"orphan labels       : {len(found.orphan_labels)} (label, no image)",
        f"unlabelled images   : {len(found.unlabelled_images)} (image, no label)",
        "",
        f"boxes               : {found.boxes}",
        f"boxes per class     : {found.boxes_per_class}",
        f"bins per frame      : {found.bins_per_frame}",
        f"  4 or more         : {sum(v for k, v in found.bins_per_frame.items() if k >= 4)}",
        f"name/box mismatches : {len(found.name_class_disagreements)}",
    ]
    if found.cache_results:
        lines += [
            "",
            "what the training run saw, per the shipped label caches:",
            *(
                f"  {split}: found={r[0]} missing={r[1]} empty={r[2]} corrupt={r[3]} total={r[4]}"
                for split, r in sorted(found.cache_results.items())
            ),
        ]
    return "\n".join(lines)


def annotator_counts(pairs: list[Pair]) -> dict[str, int]:
    """Pairs per annotator – the grouping key an annotator holdout would use."""
    counts: dict[str, int] = defaultdict(int)
    for pair in pairs:
        counts[pair.annotator or "(unattributed)"] += 1
    return dict(sorted(counts.items()))
