#!/usr/bin/env python3
"""Push a prepared pool to the Hub as a dataset subset, and print its revision.

    python ml/scripts/push_dataset.py --pool data/legacy/pool --subset legacy
    python ml/scripts/push_dataset.py --pool data/legacy/pool --subset legacy --crops

The dataset repo holds one directory per subset – ``legacy/``, ``open_images/``,
``negatives/`` – each self-contained, with its own manifest and its own
provenance. Keeping them apart is what lets a subset's contribution be measured,
and rolled back if machine-sourced data turns out to hurt.

The sha this prints is the point. It goes into ``PINS`` in
``ml/src/sbr/utils/hub.py``, and every number measured afterwards names it.
Training kernels resolve revisions strictly, so an unpinned repo stops the run
rather than quietly training against whatever ``main`` points at today.

Private by default. Publishing photographs is not something to do as a side
effect of a build step; pass ``--public`` when that is the intention.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.utils.hub import delete_subsets, preflight_layout, upload_dataset  # noqa: E402

logger = logging.getLogger("push-dataset")

CARD = """---
license: other
task_categories:
  - object-detection
  - image-classification
tags:
  - waste
  - recycling
  - smart-bin-recognition
---

# {repo}

Training data for **Smart Bin Recognition** – a validator ("is there a bin?")
and an identifier ("which bin?"). The design lives in `docs/04-ml-pipeline.md`
in the project repo, which is private; the manifests here carry per-image
provenance and are the authoritative record of what this dataset contains.

**Every image carries provenance**: source, source URL, licence, region,
capture date, annotator where known, label origin (`human` / `machine` /
`legacy` / `open-images`) and adjudication status. Licences differ per subset and
are recorded per image; there is no single licence for the whole repo, which is
why the header says `other`.

## Subsets

{subsets}

## How to read this

Each subset directory is a self-contained pool:

```
<subset>/
├── manifest.json   provenance for every frame, and every crop
├── images/         full frames
├── labels/         YOLO labels; an EMPTY file means a deliberate background image
└── crops/          identifier candidates (present only where relevant)
```

Large subsets interpose a **shard** level – `images/ab/<id>.jpg`, the two hex
characters being `sha256(stem)` – because the Hub rejects a push where any
directory holds more than 10 000 files, and the negative corpus alone is
~17 500. `manifest.json` says which: `"layout": "sharded"`, and a manifest
without the key is flat. `legacy/` is flat and stays that way.

`sbr.dataset.prepare.build_yolo_tree` assembles them into a training tree,
grouping frames by capture cluster so that two photographs of the same bin can
never straddle a split.

## What this data is not

The legacy subset is **one city in one week**, 370 usable frames, and not one
frame of it holds four or more bins — every multi-bin frame here comes from
Open Images. Numbers measured on `legacy` alone are in-distribution numbers.

**There is no geographic holdout.** Every Open Images frame carries
`region_id: "unknown"`, because the source does not record where a photograph
was taken, so no split in this dataset answers "does it work in another city".
See `docs/11-phase2-results.md` in the project repo for what was measured, on
which split, and on what hardware.
"""

SUBSET_TEMPLATE = """### `{subset}`

| | |
|---|---|
| frames | {images} |
| boxes | {boxes} |
| crops | {crops} |
| crops pending adjudication | {pending} |
| bins per frame | {bins_per_frame} |
| licence | {licence} |
| region | {region} |
| label origin | {origin} |
"""


def summarise(pool: Path, subset: str) -> str:
    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    records = manifest.get("records", [])
    crops = manifest.get("crop_records", [])
    return SUBSET_TEMPLATE.format(
        subset=subset,
        images=len(records),
        boxes=sum(r.get("boxes", 0) for r in records),
        crops=len(crops),
        pending=sum(1 for c in crops if c.get("adjudication") == "pending"),
        bins_per_frame=dict(sorted(Counter(r.get("boxes", 0) for r in records).items())),
        licence=", ".join(sorted({r.get("licence", "?") for r in records})) or "?",
        region=", ".join(sorted({r.get("region_id", "?") for r in records})) or "?",
        origin=", ".join(sorted({r.get("label_origin", "?") for r in records})) or "?",
    )


def stage(pool: Path, subset: str, staging: Path, include_crops: bool) -> Path:
    """Lay the pool out under ``<subset>/`` so several can share one repo."""
    import shutil

    target = staging / subset
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pool / "manifest.json", target / "manifest.json")
    for directory in ("images", "labels", "crops"):
        source = pool / directory
        if not source.exists():
            continue
        if directory == "crops" and not include_crops:
            continue
        shutil.copytree(source, target / directory, dirs_exist_ok=True)

    files = sum(1 for _ in target.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
    logger.info("staged %s: %d files, %.0f MB", subset, files, size / 1e6)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--subset", required=True, help="legacy | open_images | negatives | ...")
    parser.add_argument("--repo", default="arudaev/smart-bin-detect")
    parser.add_argument("--crops", action="store_true", help="include crops/ (identifier repo)")
    parser.add_argument("--public", action="store_true", help="publish, rather than keeping it private")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="delete the subset on the Hub first, so a retry does not land on a half-written tree",
    )
    parser.add_argument("--message", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not (args.pool / "manifest.json").exists():
        raise SystemExit(f"no manifest at {args.pool} - run the import first")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        stage(args.pool, args.subset, staging, include_crops=args.crops)
        (staging / "README.md").write_text(
            CARD.format(repo=args.repo, subsets=summarise(args.pool, args.subset)),
            encoding="utf-8",
        )

        if args.dry_run:
            for path in sorted(staging.rglob("*"))[:12]:
                print("  ", path.relative_to(staging))
            # The check the real push would fail on, run for free.
            preflight_layout(staging)
            if args.replace:
                print(f"--replace would delete {args.subset}/ on the Hub first")
            print("dry run - nothing uploaded")
            return

        if args.replace:
            delete_subsets(args.repo, [args.subset])

        sha = upload_dataset(
            repo_id=args.repo,
            local_dir=staging,
            commit_message=args.message or f"{args.subset}: {args.pool.name}",
            private=not args.public,
        )

    print()
    print(f"pushed {args.subset} to {args.repo} ({'public' if args.public else 'private'})")
    print(f"revision: {sha}")
    print()
    print("Record it, or the training kernels will refuse to run:")
    print("  ml/src/sbr/utils/hub.py")
    print(f'      PINS["{args.repo}"] = "{sha}"')


if __name__ == "__main__":
    main()
