"""Rebuild the predecessor's dataset: resize, rename, and carry provenance.

Two things this module deliberately does **not** do.

**It does not trust the archive.** It calls :func:`sbr.dataset.archive.verify`
first and refuses to import a copy that does not match the recorded layout. The
previous version of this file opened with a warning that its path resolution was
unverified; that warning is now a check.

**It does not invent form factors.** The legacy labels are *streams* – Biomüll,
Glas, Papier, Restmüll – and a stream does not determine a shape. The same
Restmüll is a small wheelie bin outside a house and a large one behind a block
of flats. So every crop leaves this module with ``form_factor: null``, a list of
candidates, and ``adjudication: "pending"``. A human decides, via
``ml/scripts/adjudicate.py``, and only adjudicated crops train the identifier.

The validator does not need any of that: its one class is "bin", which every box
in the archive is regardless of what goes in it. That is why model A can be
trained the moment this import finishes and model B cannot.

Output pool, shared with :mod:`sbr.dataset.prepare`::

    <out>/
    ├── manifest.json     provenance for every frame and every crop
    ├── images/           full frames, resized
    ├── labels/           validator labels - every box collapsed to class 0
    └── crops/            identifier candidates, pending adjudication
"""

from __future__ import annotations

import argparse
import json
import logging
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image

from sbr.dataset.archive import (
    LEGACY_CLASS_ORDER,
    find_root,
    inventory,
    load_expectations,
    read_labels_csv,
    resolve_pairs,
    verify,
)

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
_EXIF_DATE_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "DateTimeOriginal")


@dataclass(frozen=True)
class LegacyMapping:
    """What a legacy stream label can and cannot tell us about shape.

    ``candidates`` is the honest content of a legacy label: the set of form
    factors it leaves open. ``proposed`` is a pre-fill for the reviewer – one
    keystroke to confirm – and never a label in its own right.
    """

    candidates: tuple[str, ...]
    proposed: str
    deggendorf_stream: str
    note: str


#: What each legacy class leaves open. Note that *every* entry is a candidate
#: list, including Glas: the old code marked glass "unambiguous" on the strength
#: of a comment, and an unverified assertion about shape is the thing this
#: pipeline exists not to make. Confirming a pre-filled proposal is cheap.
LEGACY_MAP: dict[str, LegacyMapping] = {
    "Biomüll": LegacyMapping(
        candidates=("wheelie_small", "wheelie_large"),
        proposed="wheelie_small",
        deggendorf_stream="bio",
        note="household bio bins are usually 2-wheel; communal blocks use 4-wheel",
    ),
    "Papier": LegacyMapping(
        candidates=("wheelie_small", "wheelie_large", "crate", "container_bank"),
        proposed="wheelie_small",
        deggendorf_stream="paper",
        note="a Papiertonne may be 240 L or 1100 L; some kerbsides use crates",
    ),
    "Restmüll": LegacyMapping(
        candidates=("wheelie_small", "wheelie_large"),
        proposed="wheelie_small",
        deggendorf_stream="residual",
        note="the same stream is 2-wheel outside a house and 4-wheel behind a block",
    ),
    "Glas": LegacyMapping(
        candidates=("igloo", "underground", "container_bank"),
        proposed="igloo",
        deggendorf_stream="glass_mixed",
        note="communal bottle banks dominate here, but underground columns and "
             "rows of containers look nothing alike and are both glass",
    ),
}


def normalise_filename(name: str) -> str:
    """ASCII-safe, lower-case filename. Fixes the umlaut problem at the source.

    The predecessor had to rename files by hand because umlauts broke YOLO
    ingestion (08-legacy-audit § 1). Doing it here means it never recurs.
    """
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    for char, replacement in {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "ae", "Ö": "oe", "Ü": "ue",
    }.items():
        stem = stem.replace(char, replacement)
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    stem = "".join(c if c.isalnum() else "_" for c in stem).strip("_").lower()
    while "__" in stem:
        stem = stem.replace("__", "_")
    return f"{stem or 'image'}{suffix or '.jpg'}"


# --------------------------------------------------------------------------- #
# Capture time, and the clusters built from it
# --------------------------------------------------------------------------- #


def capture_datetime(image: Path, original_name: str = "", fallback: str = "") -> tuple[str | None, str]:
    """When the photograph was taken. Returns ``(iso8601 or None, source)``.

    EXIF first because it is the only one of the three that describes the
    *capture*: the filename can be a sequence number and the CSV timestamp is
    when somebody got round to labelling it, weeks later.
    """
    try:
        with Image.open(image) as handle:
            exif = handle.getexif()
        raw = exif.get(_EXIF_DATE_TAG) or exif.get(306)
        if raw:
            return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").isoformat(), "exif"
    except (OSError, ValueError):
        pass

    stem = Path(original_name).stem
    parts = stem.split("_")
    if len(parts) >= 3 and len(parts[1]) == 8 and len(parts[2]) == 6:
        try:
            return datetime.strptime(f"{parts[1]}{parts[2]}", "%Y%m%d%H%M%S").isoformat(), "filename"
        except ValueError:
            pass

    if fallback:
        return fallback, "annotation_timestamp"
    return None, "unknown"


def assign_capture_clusters(
    records: list[dict[str, Any]], gap_seconds: int, region_id: str
) -> None:
    """Group frames photographed in one burst, in place.

    A capture cluster is the unit the split assigns, so two frames of the same
    bin can never straddle train and test. Without it, "group-aware" degenerates
    to random and the eval number becomes the predecessor's eval number.

    Grouping is by annotator, then by gaps in capture time: consecutive shots
    closer together than ``gap_seconds`` are one visit to one bin.
    """
    by_annotator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_annotator[record.get("annotator") or "unattributed"].append(record)

    for annotator, group in by_annotator.items():
        timed = [r for r in group if r.get("capture_date")]
        untimed = [r for r in group if not r.get("capture_date")]
        timed.sort(key=lambda r: r["capture_date"])

        index = 0
        previous: datetime | None = None
        for record in timed:
            moment = datetime.fromisoformat(record["capture_date"])
            if previous is not None and (moment - previous).total_seconds() > gap_seconds:
                index += 1
            previous = moment
            record["capture_cluster"] = f"{region_id}/{annotator}/{index:04d}"

        # No capture time means no evidence it belongs with anything else, so it
        # becomes its own cluster rather than being folded into a neighbour's.
        for offset, record in enumerate(untimed):
            record["capture_cluster"] = f"{region_id}/{annotator}/untimed-{offset:04d}"


# --------------------------------------------------------------------------- #
# The import
# --------------------------------------------------------------------------- #


def _provenance(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": f"{source['repo']}@{source['release']}/{source['asset']}",
        "source_url": source["url"],
        "source_sha256": source["sha256"],
        "licence": source["licence"],
        "region_id": source["region_id"],
        "label_origin": source["label_origin"],
    }


def import_legacy(
    archive: Path,
    out_dir: Path,
    allow_drift: bool = False,
    write_crops: bool = True,
    config: dict[str, Any] | None = None,
) -> dict:
    """Rebuild, resize, rename and carry provenance. Emits one pool."""
    config = config or load_expectations()
    settings = config["import"]
    source = config["source"]
    region_id = source["region_id"]

    root = find_root(archive)
    problems = verify(inventory(root), config)
    if problems:
        message = "\n  ".join(problems)
        if not allow_drift:
            raise SystemExit(
                f"archive does not match ml/configs/legacy_archive.yaml:\n  {message}\n"
                "Importing anyway would quietly produce a smaller dataset than the "
                "one every downstream number assumes. Re-extract, or pass "
                "--allow-drift if the archive legitimately changed."
            )
        logger.warning("importing a drifted archive:\n  %s", message)

    pairs, orphans = resolve_pairs(root)
    if not pairs:
        raise SystemExit(f"no label/image pairs resolved under {root}")

    csv_by_key = {
        Path(row["new_filename"]).stem.split("_")[-1].lower(): row
        for row in read_labels_csv(root)
    }

    images_dir, labels_dir, crops_dir = out_dir / "images", out_dir / "labels", out_dir / "crops"
    for directory in (images_dir, labels_dir, crops_dir):
        directory.mkdir(parents=True, exist_ok=True)

    provenance = _provenance(source)
    max_edge = int(settings["max_edge"])
    quality = int(settings["jpeg_quality"])
    padding = float(settings["crop_padding"])
    min_crop = int(settings["min_crop_px"])

    records: list[dict[str, Any]] = []
    crops: list[dict[str, Any]] = []
    bytes_in = bytes_out = 0
    class_counts: Counter[str] = Counter()
    skipped_crops = 0

    for pair in sorted(pairs, key=lambda p: p.key):
        row = csv_by_key.get(pair.key, {})
        original = row.get("original_filename", pair.image.name)
        stem = Path(normalise_filename(f"{pair.key}_{original}")).stem
        target = images_dir / f"{stem}.jpg"

        bytes_in += pair.image.stat().st_size
        with Image.open(pair.image) as opened:
            captured, date_source = capture_datetime(
                pair.image, original, row.get("timestamp", "")
            )
            frame = opened.convert("RGB")
            width, height = frame.size
            scale = min(1.0, max_edge / max(width, height))
            if scale < 1.0:
                frame = frame.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
            frame.save(target, "JPEG", quality=quality, optimize=True)
            new_width, new_height = frame.size

            # --- validator: every box collapses to class 0, "bin" ------------
            (labels_dir / f"{stem}.txt").write_text(
                "\n".join(f"0 {cx} {cy} {w} {h}" for _, cx, cy, w, h in pair.boxes) + "\n",
                encoding="utf-8",
            )

            # --- identifier candidates: crops, all pending adjudication ------
            for index, (class_id, cx, cy, w, h) in enumerate(pair.boxes):
                legacy_class = LEGACY_CLASS_ORDER[class_id]
                class_counts[legacy_class] += 1
                if not write_crops:
                    continue

                padded_w, padded_h = w * (1 + padding), h * (1 + padding)
                left = max(0, int((cx - padded_w / 2) * new_width))
                top = max(0, int((cy - padded_h / 2) * new_height))
                right = min(new_width, int((cx + padded_w / 2) * new_width))
                bottom = min(new_height, int((cy + padded_h / 2) * new_height))
                if right - left < min_crop or bottom - top < min_crop:
                    skipped_crops += 1
                    continue

                crop_name = f"{stem}_{index}.jpg"
                frame.crop((left, top, right, bottom)).save(
                    crops_dir / crop_name, "JPEG", quality=quality
                )
                mapping = LEGACY_MAP[legacy_class]
                crops.append(
                    {
                        "file": crop_name,
                        "frame": f"{stem}.jpg",
                        "box_index": index,
                        "bbox_norm": [cx, cy, w, h],
                        "crop_px": [left, top, right, bottom],
                        "bins_in_frame": len(pair.boxes),
                        "legacy_class": legacy_class,
                        "legacy_class_index": class_id,
                        "deggendorf_stream": mapping.deggendorf_stream,
                        # The three fields that matter, and the reason this
                        # module cannot produce a trainable identifier alone.
                        "form_factor": None,
                        "form_factor_candidates": list(mapping.candidates),
                        "form_factor_proposed": mapping.proposed,
                        "adjudication": "pending",
                        "adjudication_note": mapping.note,
                        "capture_date": captured,
                        "annotator": pair.annotator,
                        **provenance,
                    }
                )

        bytes_out += target.stat().st_size
        records.append(
            {
                "file": f"{stem}.jpg",
                "original_file": original,
                "join_key": pair.key,
                "width": new_width,
                "height": new_height,
                "boxes": len(pair.boxes),
                "bins_in_frame": len(pair.boxes),
                "annotator": pair.annotator,
                "image_source": pair.image_source,
                "legacy_split": pair.legacy_split,
                "capture_date": captured,
                "capture_date_source": date_source,
                "capture_cluster": None,       # assigned below, across all records
                "adjudication": "not_required",  # the validator needs no form factor
                **provenance,
            }
        )

    assign_capture_clusters(records, int(settings["cluster_gap_seconds"]), region_id)
    cluster_sizes = Counter(r["capture_cluster"] for r in records)

    manifest = {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "archive": {k: source[k] for k in ("repo", "release", "asset", "sha256")},
        "drifted": bool(problems),
        "images": len(records),
        "boxes": sum(r["boxes"] for r in records),
        "orphan_labels": len(orphans),
        "crops": len(crops),
        "crops_skipped_too_small": skipped_crops,
        "crops_pending_adjudication": sum(1 for c in crops if c["adjudication"] == "pending"),
        "legacy_class_counts": dict(sorted(class_counts.items())),
        "bins_per_frame": dict(sorted(Counter(r["boxes"] for r in records).items())),
        "capture_clusters": len(cluster_sizes),
        "largest_capture_cluster": max(cluster_sizes.values()) if cluster_sizes else 0,
        "capture_date_sources": dict(sorted(Counter(r["capture_date_source"] for r in records).items())),
        "annotators": dict(sorted(Counter(r["annotator"] or "unattributed" for r in records).items())),
        "bytes_in": bytes_in,
        "bytes_out": bytes_out,
        "reduction": round(bytes_in / bytes_out, 1) if bytes_out else None,
        "validator_classes": ["bin"],
        "legacy_map": {
            name: {
                "candidates": list(m.candidates),
                "proposed": m.proposed,
                "deggendorf_stream": m.deggendorf_stream,
                "note": m.note,
            }
            for name, m in LEGACY_MAP.items()
        },
        "records": records,
        "crop_records": crops,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.info(
        "imported %d frames / %d boxes (%.0f MB -> %.0f MB, %sx smaller); "
        "%d capture clusters, largest %d; %d crops all pending adjudication",
        len(records), manifest["boxes"], bytes_in / 1e6, bytes_out / 1e6,
        manifest["reduction"], manifest["capture_clusters"],
        manifest["largest_capture_cluster"], len(crops),
    )
    return manifest


def load_manifest(pool: Path) -> dict:
    return json.loads((pool / "manifest.json").read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive-dir", type=Path, required=True, help="unpacked cv_garbage/ directory")
    parser.add_argument("--out", type=Path, default=Path("data/legacy"))
    parser.add_argument("--no-crops", action="store_true")
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help="import an archive that does not match the recorded layout, and say so in the manifest",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import_legacy(
        args.archive_dir,
        args.out,
        allow_drift=args.allow_drift,
        write_crops=not args.no_crops,
    )


if __name__ == "__main__":
    main()
