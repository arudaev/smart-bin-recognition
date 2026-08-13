"""A miniature legacy archive, built the way the real one is actually named.

Shared by the archive-contract tests and the import tests. It is small but it is
not simplified: the label names carry a Label Studio task id and byte-escaped
umlauts, the images carry the renamed form with the join hash, the CSV carries
the original camera filename, and the JPEGs carry EXIF capture times. Every one
of those is load-bearing somewhere, and a fixture that smoothed them away would
test a dataset this project does not have.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml
from PIL import Image

from sbr.dataset.archive import decode_export_name, inventory

#: task id, escaped class, join hash, annotator, split, capture time, label lines
#:
#: The capture times are chosen to make three capture clusters for Alex: two
#: shots seconds apart, then one an hour later.
FIXTURE = [
    ("004c3856", "Restm_C3_BCll", "1c64fee5", "Alex", "train",
     "2025:05:06 11:59:48", ["3 0.5 0.5 0.4 0.6"]),
    ("01f3bdb3", "Papier", "00d305ba", "Alex", "train",
     "2025:05:06 11:59:57", ["2 0.4 0.5 0.3 0.5"]),
    ("7c1d0a55", "Restm_C3_BCll", "9a782339", "Alex", "train",
     "2025:05:06 13:04:11", ["3 0.5 0.5 0.4 0.6"]),
    ("0b4c9d86", "Biom_C3_BCll", "47489532", "Fares", "val",
     "2025:06:03 17:08:39", ["0 0.5 0.5 0.5 0.5"]),
    # two bins in one frame - the only multi-bin case the archive really offers
    ("10b07159", "Glas", "a404290d", "Fares", "train",
     "2025:06:03 17:09:02", ["1 0.3 0.5 0.2 0.4", "1 0.7 0.5 0.2 0.4"]),
]

DATE_TIME_ORIGINAL = 36867
DATE_TIME = 306


def _jpeg_with_exif(captured: str) -> bytes:
    """A JPEG carrying a capture time, because that is what builds the clusters."""
    image = Image.new("RGB", (256, 256), (120, 120, 120))
    exif = Image.Exif()
    exif[DATE_TIME_ORIGINAL] = captured
    exif[DATE_TIME] = captured
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """A complete miniature archive that ``verify`` accepts."""
    root = tmp_path / "cv_garbage"
    for split in ("train", "val"):
        (root / "YOLO_Dataset" / "labels" / split).mkdir(parents=True)
        (root / "YOLO_Dataset" / "images" / split).mkdir(parents=True)
    (root / "raw_images").mkdir(parents=True)

    csv_rows = ["original_filename,new_filename,label,timestamp"]
    for task, escaped, digest, annotator, split, captured, lines in FIXTURE:
        (root / "YOLO_Dataset" / "labels" / split / f"{task}-{escaped}_{digest}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        person = root / "labeled" / annotator
        person.mkdir(parents=True, exist_ok=True)
        readable = decode_export_name(escaped)
        (person / f"{readable}_{digest}.jpg").write_bytes(_jpeg_with_exif(captured))
        # The CSV timestamp is the ANNOTATION time - weeks after capture, and
        # deliberately wrong as a capture date, so a test can catch code that
        # reaches for it first.
        csv_rows.append(
            f"IMG_{digest}.JPG,{readable}_{digest}.jpg,{readable},2025-07-01T23:13:58+00:00"
        )

    (root / "labeled" / "labels.csv").write_text("\n".join(csv_rows) + "\n", encoding="utf-8")
    (root / "YOLO_Dataset" / "data.yaml").write_text(
        yaml.safe_dump(
            {"nc": 4, "names": {0: "Biomüll", 1: "Glas", 2: "Papier", 3: "Restmüll"}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (root / "models" / "run_one").mkdir(parents=True)
    return root


@pytest.fixture
def expectations(archive: Path) -> dict:
    """Expectations matching the fixture, so a test can break exactly one thing."""
    found = inventory(archive)
    return {
        "source": {
            "repo": "arudaev/Painfully-Trivial",
            "release": "v1.0.0",
            "asset": "cv_garbage.zip",
            "url": "https://example.invalid/cv_garbage.zip",
            "sha256": "0" * 64,
            "licence": "MIT",
            "region_id": "de-by-deggendorf",
            "label_origin": "legacy",
        },
        "import": {
            "max_edge": 128,
            "jpeg_quality": 80,
            "crop_padding": 0.12,
            "min_crop_px": 8,
            "cluster_gap_seconds": 180,
        },
        "expected": {
            "yolo_labels": found.yolo_labels,
            "yolo_images": found.yolo_images,
            "labeled_images": found.labeled_images,
            "raw_images": found.raw_images,
            "labels_csv_rows": found.labels_csv_rows,
            "model_runs": found.model_runs,
            "pairable_labels": found.pairable_labels,
            "orphan_labels": len(found.orphan_labels),
            "unlabelled_images": len(found.unlabelled_images),
            "boxes": found.boxes,
            "boxes_per_class": found.boxes_per_class,
            "bins_per_frame": found.bins_per_frame,
            "data_yaml": {"nc": found.data_yaml_nc, "names": found.data_yaml_names},
        },
    }
