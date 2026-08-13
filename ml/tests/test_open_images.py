"""Tests for the Open Images corpus builder.

No network. The CSVs are tiny fixtures with the real column names, because the
things worth testing here are decisions, not I/O:

- a bin image never becomes a negative
- an unknown class name stops the build instead of shrinking it
- group-of boxes are dropped as targets but still exclude their image
- sampling is deterministic, so a rebuild is the same corpus
"""

from __future__ import annotations

import csv
import io

import pytest

from sbr.dataset.open_images import (
    Box,
    OpenImagesError,
    image_url,
    load_class_index,
    resolve_mids,
    sample,
    scan_boxes,
)

WASTE = "/m/0bjyj5"
CAR = "/m/0k4j"
BARREL = "/m/02zn6n"

BBOX_COLUMNS = [
    "ImageID", "Source", "LabelName", "Confidence",
    "XMin", "XMax", "YMin", "YMax",
    "IsOccluded", "IsTruncated", "IsGroupOf", "IsDepiction", "IsInside",
]


def _bbox_csv(rows: list[dict], tmp_path):
    path = tmp_path / "bbox.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BBOX_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "0") for c in BBOX_COLUMNS})
    return path


def _row(image_id, label, **kwargs):
    return {
        "ImageID": image_id, "LabelName": label,
        "XMin": "0.1", "XMax": "0.5", "YMin": "0.2", "YMax": "0.8", **kwargs,
    }


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #


def test_class_index_reads_the_descriptions_csv(tmp_path):
    path = tmp_path / "classes.csv"
    path.write_text(f"{WASTE},Waste container\n{CAR},Car\n", encoding="utf-8")
    assert load_class_index(path) == {"Waste container": WASTE, "Car": CAR}


def test_an_unknown_class_name_stops_the_build():
    # Silently dropping it is how a 2500-image hard-negative corpus quietly
    # becomes 900 and nobody notices until the false-positive rate does not move.
    with pytest.raises(OpenImagesError, match="not Open Images boxable classes"):
        resolve_mids(["Car", "Postbox"], {"Car": CAR})


def test_the_error_names_where_the_missing_ones_come_from():
    with pytest.raises(OpenImagesError, match="Commons harvest"):
        resolve_mids(["Postbox"], {"Car": CAR})


def test_known_names_resolve():
    assert resolve_mids(["Car"], {"Car": CAR, "Barrel": BARREL}) == {"Car": CAR}


# --------------------------------------------------------------------------- #
# The exclusion – the one that must not fail
# --------------------------------------------------------------------------- #


def test_an_image_with_a_bin_is_never_a_negative(tmp_path):
    # It also holds a car, so without the exclusion it would land in the street
    # corpus and teach the validator that a bin is not a bin.
    path = _bbox_csv([_row("img1", WASTE), _row("img1", CAR), _row("img2", CAR)], tmp_path)
    scan = scan_boxes(path, WASTE, {CAR}, {BARREL})
    street, _ = scan.negatives()
    assert "img1" not in street
    assert street == {"img2"}


def test_a_group_of_box_still_excludes_its_image(tmp_path):
    # A group-of box is useless as a detection target but it is proof the frame
    # contains bins, so the frame must stay out of the negatives.
    path = _bbox_csv([_row("img1", WASTE, IsGroupOf="1"), _row("img1", CAR)], tmp_path)
    scan = scan_boxes(path, WASTE, {CAR}, set())
    assert scan.positives["img1"] == []
    assert scan.negatives()[0] == set()


def test_a_group_of_box_is_not_a_training_target(tmp_path):
    path = _bbox_csv([_row("img1", WASTE, IsGroupOf="1"), _row("img1", WASTE)], tmp_path)
    scan = scan_boxes(path, WASTE, set(), set())
    assert len(scan.positives["img1"]) == 1
    assert not scan.positives["img1"][0].is_group_of


def test_group_of_boxes_can_be_kept_when_asked(tmp_path):
    path = _bbox_csv([_row("img1", WASTE, IsGroupOf="1")], tmp_path)
    scan = scan_boxes(path, WASTE, set(), set(), drop_group_of=False)
    assert len(scan.positives["img1"]) == 1


def test_hard_negatives_are_separated_from_street_scenes(tmp_path):
    path = _bbox_csv([_row("img1", CAR), _row("img2", BARREL)], tmp_path)
    scan = scan_boxes(path, WASTE, {CAR}, {BARREL})
    street, hard = scan.negatives()
    assert street == {"img1"}
    assert hard == {"img2"}


def test_a_degenerate_box_is_dropped(tmp_path):
    path = _bbox_csv([_row("img1", WASTE, XMin="0.5", XMax="0.5")], tmp_path)
    scan = scan_boxes(path, WASTE, set(), set())
    assert scan.positives["img1"] == []


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #


def test_box_converts_to_yolo_centre_form():
    box = Box(x_min=0.2, x_max=0.6, y_min=0.1, y_max=0.5)
    cx, cy, w, h = box.to_yolo()
    assert (cx, cy, w, h) == pytest.approx((0.4, 0.3, 0.4, 0.4))


def test_a_full_frame_box_round_trips():
    cx, cy, w, h = Box(0.0, 1.0, 0.0, 1.0).to_yolo()
    assert (cx, cy, w, h) == pytest.approx((0.5, 0.5, 1.0, 1.0))


# --------------------------------------------------------------------------- #
# Sampling and URLs
# --------------------------------------------------------------------------- #


def test_sampling_is_deterministic():
    ids = {f"img{i}" for i in range(500)}
    assert sample(ids, 50, seed=42) == sample(ids, 50, seed=42)


def test_sampling_a_different_seed_gives_a_different_corpus():
    ids = {f"img{i}" for i in range(500)}
    assert sample(ids, 50, seed=42) != sample(ids, 50, seed=43)


def test_sampling_more_than_exists_returns_everything():
    assert len(sample({"a", "b"}, 10, seed=1)) == 2


def test_image_urls_point_at_the_mirror():
    url = image_url("https://open-images-dataset.s3.amazonaws.com", "train", "abc123")
    assert url == "https://open-images-dataset.s3.amazonaws.com/train/abc123.jpg"


def test_an_unknown_split_is_refused():
    with pytest.raises(OpenImagesError, match="unknown split"):
        image_url("https://example.invalid", "holdout", "abc")


# --------------------------------------------------------------------------- #
# The config this reads
# --------------------------------------------------------------------------- #


def test_configured_classes_are_disjoint():
    # A class in both the street and hard lists would be counted twice and
    # double its share of the corpus.
    from sbr.config import load_config

    config = load_config("open_images")
    street = set(config["negatives"]["street_classes"])
    hard = set(config["negatives"]["hard_classes"])
    assert street.isdisjoint(hard)


def test_the_positive_class_is_never_a_negative_class():
    from sbr.config import load_config

    config = load_config("open_images")
    positive = config["positives"]["class"]
    assert positive not in config["negatives"]["street_classes"]
    assert positive not in config["negatives"]["hard_classes"]


def test_the_negative_ratio_is_roughly_thirty_to_one():
    # docs/04 § 1: "Roughly 30:1 negative to positive. That ratio is the point."
    # The legacy seed is 370 frames; call the positive pool ~500 with the Open
    # Images bins folded in.
    from sbr.config import load_config

    config = load_config("open_images")
    negatives = config["negatives"]["count"] + config["negatives"]["hard_negative_count"]
    assert 20 <= negatives / 500 <= 45, negatives


def test_classes_unavailable_here_are_named_not_forgotten():
    from sbr.config import load_config

    config = load_config("open_images")
    unavailable = config["negatives"]["unavailable_here"]
    assert any("postbox" in u for u in unavailable)


def test_the_scan_reads_a_streamed_csv_the_same_way(tmp_path):
    rows = [_row("img1", WASTE), _row("img2", CAR)]
    path = _bbox_csv(rows, tmp_path)
    text = path.read_text(encoding="utf-8")
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert len(parsed) == 2
    assert scan_boxes(path, WASTE, {CAR}, set()).rows == 2
