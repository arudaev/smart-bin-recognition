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
import pathlib

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


def test_an_image_that_is_both_is_a_hard_negative_only(tmp_path):
    # A photograph with a car AND a barrel joined both sets, was sampled twice
    # and fetched twice: 17 499 records over 17 474 files. Hard wins, because
    # hard negatives are the scarce ones that buy the false-positive rate.
    path = _bbox_csv([_row("img1", CAR), _row("img1", BARREL)], tmp_path)
    street, hard = scan_boxes(path, WASTE, {CAR}, {BARREL}).negatives()
    assert hard == {"img1"}
    assert street == set()
    assert street.isdisjoint(hard)


def test_the_negative_sets_are_always_disjoint(tmp_path):
    rows = [_row("a", CAR), _row("b", BARREL), _row("c", CAR), _row("c", BARREL)]
    street, hard = scan_boxes(_bbox_csv(rows, tmp_path), WASTE, {CAR}, {BARREL}).negatives()
    assert street.isdisjoint(hard)
    assert len(street) + len(hard) == 3          # a, b, c - counted once each


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


# --------------------------------------------------------------------------- #
# The harvest, and the shape it writes
# --------------------------------------------------------------------------- #


HARVEST_CONFIG = {
    "source": {
        "name": "open-images-v7",
        "licence": "CC-BY-2.0",
        "image_base": "https://example.invalid",
    },
    "image": {"max_edge": 64, "jpeg_quality": 80, "min_edge": 8},
}


def _jpeg(size=(96, 96)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (90, 90, 90)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def harvested(tmp_path):
    """One positive and two negatives, fetched from nothing."""
    from sbr.dataset.open_images import Candidate, harvest

    candidates = [
        Candidate("train", "aaa111", (Box(0.2, 0.6, 0.2, 0.6),), "positive"),
        Candidate("train", "bbb222", (), "street"),
        Candidate("validation", "ccc333", (), "hard"),
    ]
    out = tmp_path / "negatives"
    manifest = harvest(candidates, out, HARVEST_CONFIG, fetch=lambda url: _jpeg(), workers=2)
    return out, manifest


def test_the_harvest_declares_its_layout(harvested):
    from sbr.dataset.pool import SHARDED, layout_of

    _, manifest = harvested
    assert layout_of(manifest) == SHARDED


def test_every_harvested_frame_lands_in_its_shard(harvested):
    from sbr.dataset.pool import image_path, label_path, shard

    out, manifest = harvested
    assert manifest["images"] == 3
    for record in manifest["records"]:
        stem = pathlib.Path(record["file"]).stem
        assert image_path(out, record["file"], "sharded").exists()
        assert label_path(out, stem, "sharded").exists()
        # And nowhere else: a flat write would be silently unreadable later.
        assert not (out / "images" / record["file"]).exists()
        assert shard(stem) in {p.name for p in (out / "images").iterdir()}


def test_a_negative_still_gets_an_empty_label_in_its_shard(harvested):
    from sbr.dataset.pool import label_path

    out, _ = harvested
    # An empty file is a background image; a missing one is an unlabelled image
    # that ultralytics drops, which would silently delete the negative corpus.
    assert label_path(out, "bbb222", "sharded").read_text(encoding="utf-8") == ""
    assert label_path(out, "aaa111", "sharded").read_text(encoding="utf-8").startswith("0 ")


def test_the_harvest_never_crowds_a_directory(harvested):
    from sbr.dataset.pool import oversized_directories

    out, _ = harvested
    # The cap that rejected the first push, checked at a scale a test can reach.
    assert oversized_directories(out, cap=2) == {}


def test_a_duplicate_candidate_is_never_written_twice(tmp_path):
    # The last line of defence: whatever the caller hands over, one frame is one
    # record, so the manifest stays a faithful index of what is on disk.
    from sbr.dataset.open_images import Candidate, harvest

    candidates = [
        Candidate("train", "dup001", (), "street"),
        Candidate("train", "dup001", (), "hard"),
        Candidate("train", "other1", (), "street"),
    ]
    manifest = harvest(candidates, tmp_path / "neg", HARVEST_CONFIG,
                       fetch=lambda url: _jpeg(), workers=2)
    assert manifest["images"] == 2
    assert len(manifest["records"]) == 2
    assert len({r["file"] for r in manifest["records"]}) == 2
