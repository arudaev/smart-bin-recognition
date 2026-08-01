"""UNVERIFIED path resolution - written against an incomplete copy of the archive.

The archive has since been inventoried against the complete copy and its real
layout is recorded in docs/08-legacy-audit.md section 7.1: YOLO_Dataset/ holds
466 images with a 1:1 label file (372 train / 94 val, no orphans), raw_images/
holds 470, and labeled/ is split by annotator (Alex 156, Fares 161, Sameer 149).

What still needs checking before this module is trusted: that its path globbing
matches that layout, multi-bin image counts, and class balance.
"""

from __future__ import annotations

import argparse
import json
import logging
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from sbr.taxonomy import load_taxonomy

logger = logging.getLogger(__name__)

MAX_EDGE = 960
JPEG_QUALITY = 88
CROP_PADDING = 0.12
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}

#: The predecessor's class index order, from cv_garbage/2-Computer-Vision.py:323.
LEGACY_CLASS_ORDER = ["Biomüll", "Glas", "Papier", "Restmüll"]


@dataclass(frozen=True)
class LegacyMapping:
    """How one legacy class projects onto the new axes.

    ``needs_review`` marks classes whose form factor the old label cannot
    determine: a German 'Papiertonne' may be a 240 L two-wheeler or an 1100 L
    communal container, and only a human looking at the photo can say which.
    That is ~370 binary decisions – an afternoon.
    """

    form_factor: str
    expected_lid_color: str | None
    expected_body_color: str | None
    deggendorf_stream: str
    needs_review: bool


LEGACY_MAP: dict[str, LegacyMapping] = {
    "Biomüll": LegacyMapping("wheelie_small", "brown", None, "bio", needs_review=True),
    "Papier": LegacyMapping("wheelie_small", "blue", None, "paper", needs_review=True),
    "Restmüll": LegacyMapping("wheelie_small", "black", None, "residual", needs_review=True),
    # Glass was only ever communal bottle banks in the source city – unambiguous.
    "Glas": LegacyMapping("igloo", None, None, "glass_mixed", needs_review=False),
}


def normalise_filename(name: str) -> str:
    """ASCII-safe, lowercase filename. Fixes the umlaut problem at the source."""
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
    return f"{stem or 'image'}{suffix}"


def hash_suffix(name: str) -> str:
    """The 8-hex-char tail that links a label to its image."""
    return Path(name).stem.split("_")[-1].lower()


def build_image_index(archive: Path) -> dict[str, Path]:
    """Index every source image by its hash suffix.

    Images are under ``labeled/<person>/``; ``raw_images/`` and the near-empty
    ``YOLO_Dataset/images/`` are searched too, as a safety net.
    """
    index: dict[str, Path] = {}
    for root in ("labeled", "raw_images", "YOLO_Dataset/images"):
        base = archive / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                index.setdefault(hash_suffix(path.name), path)
    return index


def resolve_pairs(archive: Path) -> dict[Path, Path]:
    """Map each label file to its image. Returns {label_path: image_path}."""
    index = build_image_index(archive)
    logger.info("indexed %d source images by hash", len(index))

    # _pairs.json is authoritative where present, but its image names are
    # mojibake, so we still resolve through the hash.
    declared: dict[str, str] = {}
    pairs_file = archive / "_pairs.json"
    if not pairs_file.exists():
        pairs_file = archive.parent / "_pairs.json"
    if pairs_file.exists():
        for label_rel, image_rel, _split in json.loads(pairs_file.read_text(encoding="utf-8")):
            declared[Path(label_rel).name] = hash_suffix(Path(image_rel).name)
        logger.info("read %d declared pairs from %s", len(declared), pairs_file.name)

    resolved: dict[Path, Path] = {}
    unresolved: list[str] = []
    for label in sorted((archive / "YOLO_Dataset" / "labels").rglob("*.txt")):
        key = declared.get(label.name) or hash_suffix(label.name)
        image = index.get(key)
        if image is None:
            unresolved.append(label.name)
        else:
            resolved[label] = image

    logger.info("resolved %d/%d labels", len(resolved), len(resolved) + len(unresolved))
    if unresolved:
        logger.warning("unresolved labels (first 5): %s", unresolved[:5])
    return resolved


def read_boxes(label: Path) -> list[tuple[int, float, float, float, float]]:
    """Parse a YOLO label file into (class_id, cx, cy, w, h) tuples."""
    boxes = []
    for line in label.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 5:
            boxes.append((int(parts[0]), *(float(v) for v in parts[1:5])))
    return boxes


def import_legacy(archive: Path, out_dir: Path, write_crops: bool = True) -> dict:
    """Rebuild, resize, rename and remap. Emits validator + identifier datasets."""
    taxonomy = load_taxonomy()
    form_index = {name: i for i, name in enumerate(taxonomy.detector_classes)}

    pairs = resolve_pairs(archive)
    if not pairs:
        raise FileNotFoundError(f"no label/image pairs resolved under {archive}")

    val_img = out_dir / "validator" / "images"
    val_lbl = out_dir / "validator" / "labels"
    crop_dir = out_dir / "identifier" / "crops"
    for d in (val_img, val_lbl, crop_dir):
        d.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    crop_records: list[dict] = []
    bytes_in = bytes_out = 0
    multi_bin = 0
    class_counts: dict[str, int] = {}

    for label, source_image in sorted(pairs.items()):
        boxes = read_boxes(label)
        if not boxes:
            continue
        if len(boxes) > 1:
            multi_bin += 1

        new_name = normalise_filename(source_image.name)
        stem = Path(new_name).stem
        target = val_img / f"{stem}.jpg"

        bytes_in += source_image.stat().st_size
        with Image.open(source_image) as img:
            img = img.convert("RGB")
            width, height = img.size
            scale = min(1.0, MAX_EDGE / max(width, height))
            if scale < 1.0:
                img = img.resize((round(width * scale), round(height * scale)), Image.LANCZOS)
            img.save(target, "JPEG", quality=JPEG_QUALITY, optimize=True)
            new_w, new_h = img.size

            # --- validator labels: every box collapses to class 0 ("bin") ----
            (val_lbl / f"{stem}.txt").write_text(
                "\n".join(f"0 {cx} {cy} {w} {h}" for _, cx, cy, w, h in boxes) + "\n",
                encoding="utf-8",
            )

            # --- identifier crops, labelled by form factor -------------------
            needs_review = False
            for n, (cls_id, cx, cy, w, h) in enumerate(boxes):
                legacy_name = LEGACY_CLASS_ORDER[cls_id]
                mapping = LEGACY_MAP[legacy_name]
                needs_review |= mapping.needs_review
                class_counts[legacy_name] = class_counts.get(legacy_name, 0) + 1

                if write_crops:
                    pw, ph = w * (1 + CROP_PADDING), h * (1 + CROP_PADDING)
                    left = max(0, int((cx - pw / 2) * new_w))
                    top = max(0, int((cy - ph / 2) * new_h))
                    right = min(new_w, int((cx + pw / 2) * new_w))
                    bottom = min(new_h, int((cy + ph / 2) * new_h))
                    if right - left >= 64 and bottom - top >= 64:
                        crop_name = f"{stem}_{n}.jpg"
                        img.crop((left, top, right, bottom)).save(
                            crop_dir / crop_name, "JPEG", quality=JPEG_QUALITY
                        )
                        crop_records.append({
                            "file": crop_name,
                            "form_factor": mapping.form_factor,
                            "form_factor_index": form_index[mapping.form_factor],
                            "legacy_class": legacy_name,
                            "expected_lid_color": mapping.expected_lid_color,
                            "deggendorf_stream": mapping.deggendorf_stream,
                            "needs_form_factor_review": mapping.needs_review,
                            "label_source": "legacy",
                        })

        bytes_out += target.stat().st_size
        records.append({
            "file": f"{stem}.jpg",
            "original_file": source_image.name,
            "contributor": source_image.parent.name,
            "width": new_w,
            "height": new_h,
            "boxes": len(boxes),
            "capture_cluster": stem,
            "region_id": "de-by-deggendorf",
            "source": "painfully-trivial-v1.0.0",
            "needs_form_factor_review": needs_review,
        })

    manifest = {
        "images": len(records),
        "boxes": sum(r["boxes"] for r in records),
        "multi_bin_images": multi_bin,
        "crops": len(crop_records),
        "needs_review": sum(1 for r in crop_records if r["needs_form_factor_review"]),
        "legacy_class_counts": class_counts,
        "bytes_in": bytes_in,
        "bytes_out": bytes_out,
        "reduction": round(bytes_in / bytes_out, 1) if bytes_out else None,
        "validator_classes": ["bin"],
        "identifier_classes": taxonomy.detector_classes,
        "legacy_map": {k: asdict(v) for k, v in LEGACY_MAP.items()},
        "records": records,
        "crop_records": crop_records,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.info(
        "imported %d images / %d boxes (%.0f MB -> %.0f MB, %sx smaller); "
        "%d multi-bin; %d crops, %d need form-factor review",
        len(records), manifest["boxes"], bytes_in / 1e6, bytes_out / 1e6,
        manifest["reduction"], multi_bin, len(crop_records), manifest["needs_review"],
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, required=True,
                        help="unpacked cv_garbage/ directory")
    parser.add_argument("--out", type=Path, default=Path("data/legacy"))
    parser.add_argument("--no-crops", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import_legacy(args.archive_dir, args.out, write_crops=not args.no_crops)


if __name__ == "__main__":
    main()
