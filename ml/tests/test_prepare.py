"""Tests for splitting and tree building.

The split is where a project lies to itself. Everything here exists to make one
of those lies impossible:

- a group straddling two splits (the predecessor's 0.987)
- the validator being handed the identifier's ten classes
- an unadjudicated crop reaching the identifier's training set
- a held-out city quietly ending up in train
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sbr.dataset.prepare import (
    VALIDATOR_CLASSES,
    Record,
    assign_splits,
    bins_per_frame_buckets,
    build_classification_tree,
    build_yolo_tree,
    resolve_classes,
)
from sbr.taxonomy import load_taxonomy

VALIDATOR_CONFIG = {
    "data": {
        "classes": VALIDATOR_CLASSES,
        "classes_from_taxonomy": False,
        "split": {"train": 0.70, "val": 0.15},
        "holdout_regions": [],
    }
}

IDENTIFIER_CONFIG = {
    "data": {
        "classes_from_taxonomy": True,
        "split": {"train": 0.70, "val": 0.15},
        "holdout_regions": [],
        "require_adjudication": True,
    }
}


def _record(name: str, cluster: str, region: str = "de-by-deggendorf", boxes: int = 1, annotator: str = "Alex"):
    return Record(
        file=name, region_id=region, capture_cluster=cluster,
        boxes=boxes, annotator=annotator, bins_in_frame=boxes,
    )


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #


def test_a_capture_cluster_never_straddles_a_split():
    # The whole point. Two frames of the same bin in one visit must share a fate.
    records = [_record(f"f{i}.jpg", cluster=f"c{i // 5}") for i in range(200)]
    assignment = assign_splits(records)
    by_cluster: dict[str, set[str]] = {}
    for record in records:
        by_cluster.setdefault(record.capture_cluster, set()).add(assignment[record.file])
    assert all(len(splits) == 1 for splits in by_cluster.values())


def test_assignment_is_deterministic():
    records = [_record(f"f{i}.jpg", cluster=f"c{i // 3}") for i in range(60)]
    assert assign_splits(records) == assign_splits(records)


def test_a_held_out_region_never_reaches_train_or_val():
    records = [_record(f"d{i}.jpg", cluster=f"c{i}") for i in range(40)]
    records += [_record(f"p{i}.jpg", cluster=f"p{i}", region="de-by-passau") for i in range(20)]
    assignment = assign_splits(records, holdout_regions=["de-by-passau"])
    for record in records:
        if record.region_id == "de-by-passau":
            assert assignment[record.file] == "holdout_region"
        else:
            assert assignment[record.file] != "holdout_region"


def test_a_named_annotator_is_held_out_whole():
    records = [
        _record(f"{who}{i}.jpg", cluster=f"c{who}{i}", annotator=who)
        for who in ("Alex", "Fares", "Sameer")
        for i in range(30)
    ]
    assignment = assign_splits(records, holdout_annotators=["Sameer"])
    for record in records:
        expected = "holdout_annotator" if record.annotator == "Sameer" else None
        if expected:
            assert assignment[record.file] == expected
        else:
            assert assignment[record.file] != "holdout_annotator"


def test_hashing_three_annotators_is_warned_about_not_silently_accepted(caplog):
    # 369/1/0 is what this actually produces on the real archive. It must not
    # look like a working confound check.
    records = [
        _record(f"{who}{i}.jpg", cluster=f"c{i}", annotator=who)
        for who in ("Alex", "Fares", "Sameer")
        for i in range(30)
    ]
    assign_splits(records, group_by="annotator")
    assert "too few to measure" in caplog.text


def test_an_unknown_grouping_key_is_refused():
    with pytest.raises(ValueError, match="cannot group by"):
        assign_splits([_record("a.jpg", "c0")], group_by="vibes")


def test_a_frame_without_a_cluster_becomes_its_own_group():
    # Never folded into a shared fallback group, which would silently make one
    # giant cluster and put everything in one split.
    first = Record.from_manifest({"file": "a.jpg", "boxes": 1})
    second = Record.from_manifest({"file": "b.jpg", "boxes": 1})
    assert first.capture_cluster != second.capture_cluster


def test_bins_per_frame_buckets_group_four_and_above():
    records = [
        _record("one.jpg", "c0", boxes=1),
        _record("two.jpg", "c0", boxes=2),
        _record("six.jpg", "c0", boxes=6),
    ]
    assignment = dict.fromkeys(("one.jpg", "two.jpg", "six.jpg"), "test")
    buckets = bins_per_frame_buckets(records, assignment, "test")
    assert set(buckets) == {"1", "2", "4+"}
    assert buckets["4+"] == ["six.jpg"]


# --------------------------------------------------------------------------- #
# Class lists – the two roles must never be handed each other's
# --------------------------------------------------------------------------- #


def test_the_validator_gets_exactly_one_class():
    assert resolve_classes(VALIDATOR_CONFIG) == ["bin"]


def test_the_identifier_gets_the_form_factors_in_taxonomy_order():
    assert resolve_classes(IDENTIFIER_CONFIG) == load_taxonomy().detector_classes


def test_a_config_that_declares_neither_is_refused():
    with pytest.raises(ValueError, match="refusing to guess"):
        resolve_classes({"data": {}})


# --------------------------------------------------------------------------- #
# The trees
# --------------------------------------------------------------------------- #


@pytest.fixture
def legacy_pool(archive: Path, expectations: dict, tmp_path: Path) -> Path:
    from sbr.dataset.legacy_import import import_legacy

    pool = tmp_path / "pool"
    import_legacy(archive, pool, config=expectations)
    return pool


def test_validator_tree_declares_one_class_not_ten(legacy_pool, tmp_path):
    data_path = build_yolo_tree(legacy_pool, tmp_path / "yolo", VALIDATOR_CONFIG)
    data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    assert data["nc"] == 1
    assert data["names"] == {0: "bin"}


def test_validator_tree_copies_images_and_labels_together(legacy_pool, tmp_path):
    out = tmp_path / "yolo"
    build_yolo_tree(legacy_pool, out, VALIDATOR_CONFIG)
    for image in out.glob("images/*/*.jpg"):
        label = out / "labels" / image.parent.name / f"{image.stem}.txt"
        assert label.exists(), image


def test_a_frame_with_no_boxes_becomes_a_background_image(legacy_pool, tmp_path):
    # This is how the negative corpus enters the validator's training set.
    manifest = json.loads((legacy_pool / "manifest.json").read_text(encoding="utf-8"))
    manifest["records"].append(
        {
            "file": "street.jpg", "boxes": 0, "bins_in_frame": 0,
            "region_id": "negative", "capture_cluster": "negatives/street",
        }
    )
    (legacy_pool / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (legacy_pool / "images" / "street.jpg").write_bytes(
        (legacy_pool / "images" / manifest["records"][0]["file"]).read_bytes()
    )

    out = tmp_path / "yolo"
    build_yolo_tree(legacy_pool, out, VALIDATOR_CONFIG)
    # Names are qualified by subset, because a filename is only unique inside one.
    label = next(out.glob("labels/*/*street.txt"))
    assert label.read_text(encoding="utf-8") == ""

    composition = json.loads((out / "composition.json").read_text(encoding="utf-8"))
    assert composition["background_images"] == 1


def test_several_subsets_assemble_into_one_tree(legacy_pool, tmp_path):
    # The HF dataset repo is one directory per subset - legacy, open_images,
    # negatives - so a snapshot has no top-level manifest and several below it.
    import shutil

    root = tmp_path / "snapshot"
    shutil.copytree(legacy_pool, root / "legacy")
    shutil.copytree(legacy_pool, root / "open_images")

    out = tmp_path / "yolo"
    build_yolo_tree(root, out, VALIDATOR_CONFIG)
    composition = json.loads((out / "composition.json").read_text(encoding="utf-8"))
    assert set(composition["per_pool"]) == {"legacy", "open_images"}
    assert sum(composition["per_pool"].values()) == 2 * len(
        json.loads((legacy_pool / "manifest.json").read_text(encoding="utf-8"))["records"]
    )


def test_identical_filenames_in_two_subsets_do_not_collide(legacy_pool, tmp_path):
    import shutil

    root = tmp_path / "snapshot"
    shutil.copytree(legacy_pool, root / "legacy")
    shutil.copytree(legacy_pool, root / "open_images")

    out = tmp_path / "yolo"
    build_yolo_tree(root, out, VALIDATOR_CONFIG)
    names = [p.name for p in out.glob("images/*/*.jpg")]
    assert len(names) == len(set(names))


def test_a_snapshot_with_no_manifests_is_refused(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError, match="no pool manifests"):
        build_yolo_tree(tmp_path / "empty", tmp_path / "out", VALIDATOR_CONFIG)


def test_identifier_refuses_a_pool_of_unadjudicated_crops(legacy_pool, tmp_path):
    # The expected state until the human pass runs. It must stop, not train on
    # form factors nobody confirmed.
    with pytest.raises(SystemExit, match="no adjudicated crops"):
        build_classification_tree(legacy_pool, tmp_path / "cls", IDENTIFIER_CONFIG)


def _adjudicate_all(pool: Path, form_factor: str = "wheelie_small") -> None:
    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    for crop in manifest["crop_records"]:
        crop["form_factor"] = form_factor
        crop["adjudication"] = "confirmed"
    (pool / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_identifier_tree_is_split_by_form_factor(legacy_pool, tmp_path):
    _adjudicate_all(legacy_pool)
    out = tmp_path / "cls"
    build_classification_tree(legacy_pool, out, IDENTIFIER_CONFIG)
    assert list(out.glob("*/wheelie_small/*.jpg"))


def test_a_pending_crop_never_reaches_the_identifier(legacy_pool, tmp_path):
    manifest = json.loads((legacy_pool / "manifest.json").read_text(encoding="utf-8"))
    for index, crop in enumerate(manifest["crop_records"]):
        crop["form_factor"] = "wheelie_small"
        crop["adjudication"] = "confirmed" if index else "pending"
    (legacy_pool / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    out = tmp_path / "cls"
    build_classification_tree(legacy_pool, out, IDENTIFIER_CONFIG)
    summary = json.loads((out / "classification.json").read_text(encoding="utf-8"))
    assert summary["skipped_pending_adjudication"] == 1
    assert sum(summary["classes_present"].values()) == len(manifest["crop_records"]) - 1


def test_absent_form_factors_are_named_rather_than_hidden(legacy_pool, tmp_path):
    _adjudicate_all(legacy_pool)
    out = tmp_path / "cls"
    build_classification_tree(legacy_pool, out, IDENTIFIER_CONFIG)
    summary = json.loads((out / "classification.json").read_text(encoding="utf-8"))
    # Nine of the ten have no data at all, and that has to be visible.
    assert "container_bank" in summary["classes_absent"]
    assert len(summary["classes_absent"]) == len(load_taxonomy().detector_classes) - 1


def test_a_crop_shares_its_frames_split(legacy_pool, tmp_path):
    _adjudicate_all(legacy_pool)
    out = tmp_path / "cls"
    build_classification_tree(legacy_pool, out, IDENTIFIER_CONFIG)

    manifest = json.loads((legacy_pool / "manifest.json").read_text(encoding="utf-8"))
    prefix = f"{legacy_pool.name}__"
    frames = [
        Record.from_manifest({**entry, "file": prefix + entry["file"]})
        for entry in manifest["records"]
    ]
    assignment = assign_splits(frames, train=0.70, val=0.15)
    by_crop = {prefix + c["file"]: prefix + c["frame"] for c in manifest["crop_records"]}

    for crop_path in out.glob("*/*/*.jpg"):
        split = crop_path.parent.parent.name
        assert assignment[by_crop[crop_path.name]] == split


# --------------------------------------------------------------------------- #
# Two layouts, one tree
# --------------------------------------------------------------------------- #


def _reshard(pool: Path) -> Path:
    """Rewrite a flat pool into the sharded layout, in place."""
    from sbr.dataset.pool import SHARDED, crop_path, image_path, label_path

    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    for directory, resolve in (
        ("images", lambda name: image_path(pool, name, SHARDED)),
        ("labels", lambda name: label_path(pool, Path(name).stem, SHARDED)),
        ("crops", lambda name: crop_path(pool, name, SHARDED)),
    ):
        source = pool / directory
        if not source.exists():
            continue
        for path in sorted(p for p in source.iterdir() if p.is_file()):
            target = resolve(path.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)

    manifest["layout"] = SHARDED
    (pool / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pool


def test_a_sharded_pool_builds_the_same_tree_as_a_flat_one(legacy_pool, tmp_path):
    flat = build_yolo_tree(legacy_pool, tmp_path / "flat", VALIDATOR_CONFIG)
    flat_names = sorted(p.relative_to(flat.parent).as_posix() for p in flat.parent.rglob("*.jpg"))

    _reshard(legacy_pool)
    sharded = build_yolo_tree(legacy_pool, tmp_path / "sharded", VALIDATOR_CONFIG)
    sharded_names = sorted(
        p.relative_to(sharded.parent).as_posix() for p in sharded.parent.rglob("*.jpg")
    )

    assert sharded_names == flat_names
    assert json.loads((sharded.parent / "composition.json").read_text(encoding="utf-8")) == json.loads(
        (flat.parent / "composition.json").read_text(encoding="utf-8")
    )


def test_a_flat_and_a_sharded_subset_assemble_together(legacy_pool, tmp_path):
    # The state the dataset repo is actually in: `legacy/` was pushed flat and
    # is the one pinned revision this project has, while the harvested subsets
    # are sharded. A resolver that understood only one of them would either
    # invalidate the pin or fail to read the harvest.
    import shutil

    root = tmp_path / "snapshot"
    shutil.copytree(legacy_pool, root / "legacy")
    shutil.copytree(legacy_pool, root / "negatives")
    _reshard(root / "negatives")

    out = tmp_path / "yolo"
    build_yolo_tree(root, out, VALIDATOR_CONFIG)
    composition = json.loads((out / "composition.json").read_text(encoding="utf-8"))
    assert set(composition["per_pool"]) == {"legacy", "negatives"}
    assert composition["per_pool"]["legacy"] == composition["per_pool"]["negatives"]
    for image in out.glob("images/*/*.jpg"):
        assert (out / "labels" / image.parent.name / f"{image.stem}.txt").exists()


def test_the_output_tree_is_flat_even_from_sharded_pools(legacy_pool, tmp_path):
    # It is local scratch that ultralytics reads directly, never pushed, so the
    # Hub's cap does not apply and YOLO's images/train convention does.
    _reshard(legacy_pool)
    out = tmp_path / "yolo"
    build_yolo_tree(legacy_pool, out, VALIDATOR_CONFIG)
    assert list(out.glob("images/train/*.jpg"))
    assert not list(out.glob("images/train/*/*.jpg"))


def test_a_sharded_pool_feeds_the_identifier_too(legacy_pool, tmp_path):
    _adjudicate_all(legacy_pool)
    _reshard(legacy_pool)
    out = build_classification_tree(legacy_pool, tmp_path / "cls", IDENTIFIER_CONFIG)
    summary = json.loads((out / "classification.json").read_text(encoding="utf-8"))
    assert sum(summary["classes_present"].values()) > 0
