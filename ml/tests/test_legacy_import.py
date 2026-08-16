"""Tests for the legacy import.

Three things are worth more than the rest here, and each maps to a way the
project has already been burned or could be:

1. **The import refuses a short archive.** Quietly importing 12 images instead
   of 370 would produce a pipeline that runs, trains, and reports a number
   about nothing.
2. **No crop leaves with a form factor.** The legacy labels are streams, and a
   stream does not determine a shape. Inventing one to avoid the human pass is
   the single most tempting shortcut in this phase.
3. **Capture clusters are real.** If every frame is its own cluster, the
   "group-aware" split is a random split, and a random split of one capture
   session is exactly how the predecessor got 0.987.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sbr.dataset.legacy_import import (
    LEGACY_MAP,
    assign_capture_clusters,
    capture_datetime,
    import_legacy,
    normalise_filename,
)
from sbr.taxonomy import load_taxonomy


@pytest.fixture
def pool(archive: Path, expectations: dict, tmp_path: Path) -> dict:
    return import_legacy(archive, tmp_path / "pool", config=expectations)


# --------------------------------------------------------------------------- #
# 1. It does not trust the archive
# --------------------------------------------------------------------------- #


def test_a_short_archive_stops_the_import(archive, expectations, tmp_path):
    next((archive / "labeled" / "Alex").glob("*.jpg")).unlink()
    with pytest.raises(SystemExit, match="does not match"):
        import_legacy(archive, tmp_path / "pool", config=expectations)


def test_drift_can_be_overridden_but_is_recorded(archive, expectations, tmp_path):
    next((archive / "labeled" / "Alex").glob("*.jpg")).unlink()
    manifest = import_legacy(archive, tmp_path / "pool", allow_drift=True, config=expectations)
    assert manifest["drifted"] is True


def test_an_undrifted_import_says_so(pool):
    assert pool["drifted"] is False


# --------------------------------------------------------------------------- #
# 2. It does not invent form factors
# --------------------------------------------------------------------------- #


def test_no_crop_leaves_with_a_form_factor(pool):
    assert pool["crops"] > 0
    assert all(crop["form_factor"] is None for crop in pool["crop_records"])


def test_every_crop_is_pending_adjudication(pool):
    assert pool["crops_pending_adjudication"] == pool["crops"]


def test_glass_is_proposed_not_asserted(pool):
    # The old map called glass "unambiguous" on the strength of a comment. A
    # bottle bank, an underground column and a row of containers are all glass
    # and look nothing alike.
    glass = [c for c in pool["crop_records"] if c["legacy_class"] == "Glas"]
    assert glass
    assert all(c["form_factor"] is None for c in glass)
    assert all(c["adjudication"] == "pending" for c in glass)
    assert all(len(c["form_factor_candidates"]) > 1 for c in glass)


def test_candidates_are_real_form_factors():
    known = set(load_taxonomy().detector_classes)
    for mapping in LEGACY_MAP.values():
        assert set(mapping.candidates) <= known
        assert mapping.proposed in mapping.candidates


def test_every_legacy_class_leaves_the_shape_open():
    # If any legacy class ever had a single candidate it would be a mapping
    # table again, and the human pass would be skippable for that class.
    assert all(len(m.candidates) > 1 for m in LEGACY_MAP.values())


def test_a_stream_is_recorded_but_kept_separate_from_shape(pool):
    crop = pool["crop_records"][0]
    assert crop["deggendorf_stream"]
    assert crop["form_factor"] is None


# --------------------------------------------------------------------------- #
# 3. Capture clusters
# --------------------------------------------------------------------------- #


def test_capture_time_comes_from_exif_not_the_annotation_timestamp(pool):
    # The CSV timestamp in the fixture is July; the EXIF is May and June.
    assert pool["capture_date_sources"] == {"exif": pool["images"]}
    assert all(r["capture_date"].startswith("2025-0") for r in pool["records"])
    assert not any(r["capture_date"].startswith("2025-07") for r in pool["records"])


def test_frames_seconds_apart_share_a_cluster(pool):
    alex = {r["file"]: r["capture_cluster"] for r in pool["records"] if r["annotator"] == "Alex"}
    assert len(set(alex.values())) == 2, alex  # two burst, one an hour later


def test_clusters_are_fewer_than_frames(pool):
    # The property that matters: if these were equal the split would be random.
    assert pool["capture_clusters"] < pool["images"]


def test_a_frame_without_a_capture_time_gets_its_own_cluster():
    records = [
        {"annotator": "Alex", "capture_date": None},
        {"annotator": "Alex", "capture_date": None},
    ]
    assign_capture_clusters(records, gap_seconds=180, region_id="r")
    assert records[0]["capture_cluster"] != records[1]["capture_cluster"]


def test_clusters_never_span_annotators():
    records = [
        {"annotator": "Alex", "capture_date": "2025-05-06T11:59:48"},
        {"annotator": "Fares", "capture_date": "2025-05-06T11:59:50"},
    ]
    assign_capture_clusters(records, gap_seconds=180, region_id="r")
    assert records[0]["capture_cluster"] != records[1]["capture_cluster"]


def test_capture_datetime_falls_back_through_three_sources(tmp_path):
    missing = tmp_path / "nope.jpg"
    assert capture_datetime(missing, "IMG_20250506_115948.jpg")[1] == "filename"
    assert capture_datetime(missing, "IMG_5602.JPG", "2025-07-01T00:00:00")[1] == "annotation_timestamp"
    assert capture_datetime(missing, "IMG_5602.JPG") == (None, "unknown")


# --------------------------------------------------------------------------- #
# Provenance, and the pool layout
# --------------------------------------------------------------------------- #


REQUIRED_PROVENANCE = {
    "source", "source_url", "source_sha256", "licence", "region_id",
    "label_origin", "capture_date", "annotator",
}


def test_every_frame_carries_provenance(pool):
    for record in pool["records"]:
        assert REQUIRED_PROVENANCE <= set(record), sorted(REQUIRED_PROVENANCE - set(record))


def test_every_crop_carries_provenance(pool):
    for crop in pool["crop_records"]:
        assert REQUIRED_PROVENANCE <= set(crop), sorted(REQUIRED_PROVENANCE - set(crop))


def test_label_origin_is_legacy_everywhere(pool):
    assert {r["label_origin"] for r in pool["records"]} == {"legacy"}
    assert {c["label_origin"] for c in pool["crop_records"]} == {"legacy"}


def test_bins_in_frame_is_recorded_for_the_bucketed_eval(pool):
    # docs/04 5 commits to reporting recall bucketed by bins-per-frame, so a
    # model that only works on one big centred bin cannot hide behind a mean.
    assert all("bins_in_frame" in r for r in pool["records"])
    assert pool["bins_per_frame"] == {1: 4, 2: 1}


def test_pool_layout_is_the_one_prepare_reads(archive, expectations, tmp_path):
    out = tmp_path / "pool"
    manifest = import_legacy(archive, out, config=expectations)
    assert (out / "manifest.json").exists()
    for record in manifest["records"]:
        assert (out / "images" / record["file"]).exists()
        assert (out / "labels" / f"{Path(record['file']).stem}.txt").exists()
    for crop in manifest["crop_records"]:
        assert (out / "crops" / crop["file"]).exists()


def test_validator_labels_collapse_every_box_to_one_class(archive, expectations, tmp_path):
    out = tmp_path / "pool"
    import_legacy(archive, out, config=expectations)
    for label in (out / "labels").glob("*.txt"):
        for line in label.read_text(encoding="utf-8").splitlines():
            if line.strip():
                assert line.split()[0] == "0"


def test_filenames_are_ascii(pool):
    for record in pool["records"]:
        record["file"].encode("ascii")
    for crop in pool["crop_records"]:
        crop["file"].encode("ascii")


def test_umlauts_are_transliterated_not_dropped():
    # The predecessor had to rename files by hand because umlauts broke YOLO
    # ingestion. "Restmuell" keeps the word; stripping would give "restmll".
    assert normalise_filename("Restmüll_1c64fee5.JPG") == "restmuell_1c64fee5.jpg"
    assert normalise_filename("Biomüll.jpg") == "biomuell.jpg"


def test_manifest_is_json_round_trippable(pool):
    assert json.loads(json.dumps(pool, ensure_ascii=False))["images"] == pool["images"]


def test_images_are_resized_to_the_configured_edge(archive, expectations, tmp_path):
    from PIL import Image

    out = tmp_path / "pool"
    manifest = import_legacy(archive, out, config=expectations)
    edge = expectations["import"]["max_edge"]
    for record in manifest["records"]:
        with Image.open(out / "images" / record["file"]) as image:
            assert max(image.size) <= edge
