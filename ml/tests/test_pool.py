"""Tests for the pool layout: the shard function, and the Hub's file cap.

The shard function is the kind of thing that looks untestable and is not. Two
properties matter and both are cheap to check: it must be the same on every
machine and in every process, and it must actually spread 17 500 files thinly
enough that no directory reaches the cap that caused this module to exist.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from sbr.dataset.pool import (
    FLAT,
    MAX_FILES_PER_DIR,
    SHARD_BUCKETS,
    SHARDED,
    crop_path,
    image_path,
    label_path,
    layout_of,
    oversized_directories,
    shard,
)

# The negatives corpus as ml/configs/open_images.yaml asks for it.
NEGATIVES = 15_000 + 2_500


def test_the_shard_is_stable_across_processes():
    # Pinned values, not self-consistency: hash() would pass a self-consistency
    # check and still scatter the pool differently on every run, which would
    # make a pushed pool unreadable by the next kernel.
    assert shard("7783533bc5a3df37") == "90"
    assert shard("b9a1d1f0e9435d17") == "87"


def test_an_image_and_its_label_share_a_shard():
    pool = Path("pool")
    image = image_path(pool, "0bjyj5.jpg", SHARDED)
    label = label_path(pool, "0bjyj5", SHARDED)
    assert image.parent.name == label.parent.name


def test_the_negative_corpus_fits_under_the_cap():
    counts = Counter(shard(f"{i:016x}") for i in range(NEGATIVES))
    assert len(counts) == SHARD_BUCKETS
    assert max(counts.values()) < MAX_FILES_PER_DIR


def test_a_manifest_without_a_layout_is_flat():
    # Load-bearing: the pinned legacy revision predates the key, and a resolver
    # that assumed shards would invalidate the one pin this project has.
    assert layout_of({}) == FLAT
    assert layout_of({"images": 370}) == FLAT


def test_a_declared_layout_is_honoured():
    assert layout_of({"layout": SHARDED}) == SHARDED


def test_an_unknown_layout_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match="layout"):
        layout_of({"layout": "webdataset"})


def test_flat_resolution_is_the_plain_join():
    pool = Path("pool")
    assert image_path(pool, "a.jpg", FLAT) == pool / "images" / "a.jpg"
    assert label_path(pool, "a", FLAT) == pool / "labels" / "a.txt"
    assert crop_path(pool, "a-0.jpg", FLAT) == pool / "crops" / "a-0.jpg"


def test_sharded_resolution_inserts_exactly_one_level():
    pool = Path("pool")
    resolved = image_path(pool, "a.jpg", SHARDED)
    assert resolved.relative_to(pool).parts == ("images", shard("a"), "a.jpg")


def test_an_oversized_directory_is_found_and_counted(tmp_path):
    crowded = tmp_path / "labels"
    crowded.mkdir()
    for i in range(5):
        (crowded / f"{i}.txt").write_text("", encoding="utf-8")

    assert oversized_directories(tmp_path, cap=10) == {}
    assert oversized_directories(tmp_path, cap=4) == {crowded: 5}


def test_a_subdirectory_does_not_count_towards_its_parent(tmp_path):
    # The whole point of sharding: 10 files in 10 shards is not 10 in one.
    for i in range(10):
        bucket = tmp_path / "images" / f"{i:02x}"
        bucket.mkdir(parents=True)
        (bucket / f"{i}.jpg").write_bytes(b"")
    assert oversized_directories(tmp_path, cap=2) == {}
