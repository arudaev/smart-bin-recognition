"""Tests for the legacy archive contract.

The failure this guards against has already happened twice: code and prose both
asserted a layout nobody had checked against the artefact people download. So
these tests build a miniature archive with the real naming scheme, prove that
:func:`verify` catches each way a copy can be short, and – when the real archive
is available – check that too.

Set ``SBR_ARCHIVE_DIR`` to the extracted ``cv_garbage/`` to include the real one:

    SBR_ARCHIVE_DIR=data/legacy/_archive/cv_garbage python -m pytest
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from sbr.dataset.archive import (
    class_from_export_name,
    decode_export_name,
    inventory,
    join_key,
    load_expectations,
    resolve_pairs,
    verify,
)

# --------------------------------------------------------------------------- #
# A miniature archive, built the way the real one is named
# --------------------------------------------------------------------------- #

#: (task id, escaped class, hash, annotator, split, label lines)
FIXTURE = [
    ("004c3856", "Restm_C3_BCll", "1c64fee5", "Alex", "train", ["3 0.5 0.5 0.4 0.6"]),
    ("01f3bdb3", "Papier", "00d305ba", "Alex", "train", ["2 0.4 0.5 0.3 0.5"]),
    ("0b4c9d86", "Biom_C3_BCll", "47489532", "Fares", "val", ["0 0.5 0.5 0.5 0.5"]),
    # two bins in one frame
    ("10b07159", "Glas", "a404290d", "Fares", "train", ["1 0.3 0.5 0.2 0.4", "1 0.7 0.5 0.2 0.4"]),
]


def _png_bytes() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 120, 120)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """A complete miniature archive that :func:`verify` accepts."""
    root = tmp_path / "cv_garbage"
    for split in ("train", "val"):
        (root / "YOLO_Dataset" / "labels" / split).mkdir(parents=True)
        (root / "YOLO_Dataset" / "images" / split).mkdir(parents=True)
    (root / "raw_images").mkdir(parents=True)

    jpeg = _png_bytes()
    csv_rows = ["original_filename,new_filename,label,timestamp"]
    for task, escaped, digest, annotator, split, lines in FIXTURE:
        (root / "YOLO_Dataset" / "labels" / split / f"{task}-{escaped}_{digest}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        person = root / "labeled" / annotator
        person.mkdir(parents=True, exist_ok=True)
        readable = decode_export_name(escaped)
        (person / f"{readable}_{digest}.jpg").write_bytes(jpeg)
        csv_rows.append(f"IMG_2025_{digest}.jpg,{readable}_{digest}.jpg,{readable},2025-05-14T23:13:58+00:00")

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
    """Expectations matching the fixture, so each test can break exactly one thing."""
    found = inventory(archive)
    return {
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
        }
    }


# --------------------------------------------------------------------------- #
# Naming – the join key is the whole ballgame
# --------------------------------------------------------------------------- #


def test_label_and_image_share_only_the_hash_tail():
    # Nothing else about these two names matches, which is why every earlier
    # attempt to pair them by stem resolved almost nothing.
    assert join_key("004c3856-Restm_C3_BCll_1c64fee5.txt") == "1c64fee5"
    assert join_key("Restmüll_1c64fee5.jpg") == "1c64fee5"


def test_label_studio_byte_escaping_round_trips():
    assert decode_export_name("Restm_C3_BCll") == "Restmüll"
    assert decode_export_name("Biom_C3_BCll") == "Biomüll"
    assert decode_export_name("Papier") == "Papier"


@pytest.mark.parametrize(
    "stem",
    [
        "Papier_00d305ba",   # tail starts with two digits – the byte would be NUL
        "Glas_a404290d",
        "Restmuell_1c64fee5",
        "Papier_8cfea8c7",
    ],
)
def test_a_hash_tail_is_never_mistaken_for_escaped_bytes(stem):
    # Only bytes >= 0x80 are ever escaped. Without that bound the pattern eats
    # the join key and the label pairs with nothing.
    assert decode_export_name(stem) == stem


def test_class_recovered_from_an_export_name():
    assert class_from_export_name("004c3856-Restm_C3_BCll_1c64fee5.txt") == "Restmüll"
    assert class_from_export_name("nonsense.txt") is None


# --------------------------------------------------------------------------- #
# Pairing
# --------------------------------------------------------------------------- #


def test_every_fixture_label_pairs(archive):
    pairs, orphans = resolve_pairs(archive)
    assert len(pairs) == len(FIXTURE)
    assert orphans == []


def test_pairs_carry_the_annotator(archive):
    pairs, _ = resolve_pairs(archive)
    assert {p.annotator for p in pairs} == {"Alex", "Fares"}


def test_a_label_whose_image_is_missing_becomes_an_orphan(archive):
    next((archive / "labeled" / "Alex").glob("*.jpg")).unlink()
    pairs, orphans = resolve_pairs(archive)
    assert len(orphans) == 1
    assert len(pairs) == len(FIXTURE) - 1


def test_boxes_and_bins_per_frame_are_counted(archive):
    found = inventory(archive)
    assert found.boxes == 5
    assert found.bins_per_frame == {1: 3, 2: 1}


# --------------------------------------------------------------------------- #
# verify() – each way a copy can be short
# --------------------------------------------------------------------------- #


def test_a_matching_archive_verifies(archive, expectations):
    assert verify(inventory(archive), expectations) == []


def test_a_short_label_tree_fails(archive, expectations):
    next((archive / "YOLO_Dataset" / "labels" / "train").glob("*.txt")).unlink()
    problems = verify(inventory(archive), expectations)
    assert any("YOLO_Dataset/labels/train" in p for p in problems)


def test_a_missing_image_fails_as_a_pairing_shortfall(archive, expectations):
    next((archive / "labeled" / "Fares").glob("*.jpg")).unlink()
    problems = verify(inventory(archive), expectations)
    assert any("pairable labels" in p for p in problems)
    assert any("orphan labels" in p for p in problems)


def test_a_missing_annotator_directory_fails(archive, expectations):
    import shutil

    shutil.rmtree(archive / "labeled" / "Alex")
    problems = verify(inventory(archive), expectations)
    assert any("labeled/Alex" in p for p in problems)


def test_an_unexpected_annotator_directory_fails(archive, expectations):
    (archive / "labeled" / "Newcomer").mkdir()
    problems = verify(inventory(archive), expectations)
    assert any("unexpected annotator" in p for p in problems)


def test_a_reordered_data_yaml_fails_loudly(archive, expectations):
    # This is the one that would corrupt everything silently: the order in
    # data.yaml is the class index inside every label file.
    (archive / "YOLO_Dataset" / "data.yaml").write_text(
        yaml.safe_dump(
            {"nc": 4, "names": {0: "Glas", 1: "Biomüll", 2: "Papier", 3: "Restmüll"}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    problems = verify(inventory(archive), expectations)
    assert any("class index" in p for p in problems)


def test_a_changed_class_balance_fails(archive, expectations):
    label = next((archive / "YOLO_Dataset" / "labels" / "train").glob("*Papier*.txt"))
    label.write_text("3 0.4 0.5 0.3 0.5\n", encoding="utf-8")
    problems = verify(inventory(archive), expectations)
    assert any("boxes per class" in p for p in problems)


def test_an_empty_archive_is_not_silently_accepted(tmp_path):
    (tmp_path / "YOLO_Dataset").mkdir()
    problems = verify(inventory(tmp_path), {"expected": {"pairable_labels": 370}})
    assert any("pairable labels" in p for p in problems)


def test_pointing_at_the_wrong_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="no YOLO_Dataset"):
        inventory(tmp_path / "not-an-archive")


# --------------------------------------------------------------------------- #
# The recorded expectations, and the real archive when it is available
# --------------------------------------------------------------------------- #


def test_recorded_expectations_describe_the_published_release():
    # Pinned so that a future edit to legacy_archive.yaml which quietly relaxes
    # the contract fails here. 370 is the usable dataset; it is not 466, and no
    # number downstream may assume otherwise.
    recorded = load_expectations()["expected"]
    assert recorded["pairable_labels"] == 370
    assert recorded["orphan_labels"] == 31
    assert recorded["boxes"] == 403
    assert recorded["data_yaml"]["names"] == ["Biomüll", "Glas", "Papier", "Restmüll"]


def test_the_archive_never_contained_a_bank_of_containers():
    # docs/04 § 5 calls this a product risk rather than a data footnote, and the
    # identifier's `container_bank` class depends on it staying visible.
    recorded = load_expectations()["expected"]["bins_per_frame"]
    assert not [count for count in recorded if int(count) >= 4]


def test_training_time_counts_are_recorded_but_not_expected_of_the_release():
    # The evidence that 466 once existed, kept separate from the contract so
    # nobody re-derives "the archive has 466 images" from it.
    recorded = load_expectations()
    assert recorded["at_training_time"]["total"] == 466
    assert recorded["expected"]["pairable_labels"] < 466


@pytest.mark.skipif(not os.environ.get("SBR_ARCHIVE_DIR"), reason="SBR_ARCHIVE_DIR not set")
def test_the_real_archive_matches_the_contract():
    found = inventory(Path(os.environ["SBR_ARCHIVE_DIR"]))
    assert verify(found) == []


@pytest.mark.skipif(not os.environ.get("SBR_ARCHIVE_DIR"), reason="SBR_ARCHIVE_DIR not set")
def test_the_real_archive_reports_what_the_training_run_saw():
    found = inventory(Path(os.environ["SBR_ARCHIVE_DIR"]))
    assert found.cache_results["train"][4] == 372
    assert found.cache_results["val"][4] == 94


def test_inventory_summary_is_json_safe(archive):
    import json

    json.dumps(inventory(archive).summary())


def test_describe_reports_the_class_names_unmangled(archive):
    # The umlauts are correct and stay correct. Consoles that cannot print them
    # are the console's problem, and inventory_legacy.py forces UTF-8 on stdout
    # rather than degrading the data on the way out.
    from sbr.dataset.archive import describe

    text = describe(inventory(archive))
    assert "Restmüll" in text
    assert "Biomüll" in text
