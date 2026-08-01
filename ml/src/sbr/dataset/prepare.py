"""Build YOLO-format splits from the pooled dataset.

The only interesting thing here is the splitting, and it is interesting because
the predecessor got it wrong in a way that made its headline number meaningless:
a random 20 % split of 466 photos taken in one city in one week measures
memorisation, not generalisation.

Two rules fix that:

1. **Group-aware.** Photos are grouped by capture cluster (same physical bin,
   same session). A group lands entirely in one split. Without this, the model
   sees a bin in training and is tested on the next frame of the same bin.
2. **Region holdout.** Whole cities are excluded from train and val, giving the
   held-out-city number that actually predicts launch behaviour.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from sbr.taxonomy import load_taxonomy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Record:
    """One labelled image in the pool."""

    file: str
    region_id: str
    capture_cluster: str
    boxes: int

    @classmethod
    def from_manifest(cls, entry: dict) -> Record:
        # Until sightings carry a real cluster id, fall back to grouping by the
        # original capture filename stem, which for the legacy set corresponds
        # to one photo session of one bin.
        cluster = entry.get("capture_cluster") or Path(
            entry.get("original_file", entry["file"])
        ).stem.rsplit("_", 1)[0]
        return cls(
            file=entry["file"],
            region_id=entry.get("region_id", "unknown"),
            capture_cluster=cluster,
            boxes=entry.get("boxes", 0),
        )


def _bucket(key: str, buckets: int = 1000) -> int:
    """Stable hash bucket – deterministic across machines and Python versions."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % buckets


def assign_splits(
    records: Iterable[Record],
    train: float = 0.70,
    val: float = 0.15,
    holdout_regions: Iterable[str] = (),
) -> dict[str, str]:
    """Map each file to ``train`` | ``val`` | ``test`` | ``holdout_region``.

    Assignment is by capture cluster, so every photo of one bin shares a split.
    """
    holdout = set(holdout_regions)
    by_cluster: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        by_cluster[record.capture_cluster].append(record)

    assignment: dict[str, str] = {}
    train_cut = int(train * 1000)
    val_cut = int((train + val) * 1000)

    for cluster, group in by_cluster.items():
        if any(r.region_id in holdout for r in group):
            split = "holdout_region"
        else:
            bucket = _bucket(cluster)
            split = "train" if bucket < train_cut else "val" if bucket < val_cut else "test"
        for record in group:
            assignment[record.file] = split

    counts: dict[str, int] = defaultdict(int)
    for split in assignment.values():
        counts[split] += 1
    logger.info("split assignment: %s", dict(counts))
    return assignment


def build_yolo_tree(pool_dir: Path, out_dir: Path, config: dict) -> Path:
    """Materialise a YOLO dataset directory and its ``data.yaml``."""
    manifest = json.loads((pool_dir / "manifest.json").read_text(encoding="utf-8"))
    records = [Record.from_manifest(entry) for entry in manifest["records"]]

    split_cfg = config.get("data", {}).get("split", {})
    assignment = assign_splits(
        records,
        train=split_cfg.get("train", 0.70),
        val=split_cfg.get("val", 0.15),
        holdout_regions=config.get("data", {}).get("holdout_regions", ()),
    )

    for split in ("train", "val", "test", "holdout_region"):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    for record in records:
        split = assignment[record.file]
        stem = Path(record.file).stem
        shutil.copy2(pool_dir / "images" / record.file, out_dir / "images" / split / record.file)
        label = pool_dir / "labels" / f"{stem}.txt"
        if label.exists():
            shutil.copy2(label, out_dir / "labels" / split / f"{stem}.txt")

    classes = load_taxonomy().detector_classes
    data_yaml = {
        "path": str(out_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": len(classes),
        "names": {index: name for index, name in enumerate(classes)},
    }
    data_path = out_dir / "data.yaml"
    data_path.write_text(yaml.safe_dump(data_yaml, sort_keys=False), encoding="utf-8")

    logger.info("wrote %s with %d classes", data_path, len(classes))
    return data_path
