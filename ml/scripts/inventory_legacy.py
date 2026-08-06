#!/usr/bin/env python3
"""Measure the legacy archive and check it against the recorded layout.

    python ml/scripts/inventory_legacy.py --archive-dir data/legacy/_archive/cv_garbage
    python ml/scripts/inventory_legacy.py --archive-dir ... --json out.json
    python ml/scripts/inventory_legacy.py --archive-dir ... --emit-expectations

Exits non-zero when the archive does not match ``ml/configs/legacy_archive.yaml``.
That is the point: the last two times this dataset was described, the
description did not match the artefact, and nothing complained.

``--emit-expectations`` prints a config block from what is actually there. Use it
when the archive legitimately changes, and put the reason in the commit message.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.dataset.archive import (  # noqa: E402
    annotator_counts,
    describe,
    inventory,
    resolve_pairs,
    verify,
)


def emit_expectations(found) -> str:
    import yaml

    block = {
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
    return yaml.safe_dump(block, sort_keys=False, allow_unicode=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None, help="write the full inventory here")
    parser.add_argument("--emit-expectations", action="store_true")
    parser.add_argument("--show-orphans", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # The class names carry umlauts and they are correct. A console that cannot
    # print them must not turn them into question marks in the middle of an
    # integrity report – that is how the earlier confusion about this archive
    # got started.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    found = inventory(args.archive_dir)
    pairs, _ = resolve_pairs(found.root)

    print(describe(found))
    print()
    print(f"annotators          : {annotator_counts(pairs)}")
    legacy_split: dict[str, int] = {}
    for pair in pairs:
        legacy_split[pair.legacy_split] = legacy_split.get(pair.legacy_split, 0) + 1
    print(f"legacy split        : {legacy_split}")

    if args.show_orphans:
        print("\norphan labels (no image):")
        for name in found.orphan_labels:
            print("   ", name)

    if found.name_class_disagreements:
        print(f"\nname/box disagreements ({len(found.name_class_disagreements)}):")
        for line in found.name_class_disagreements[:20]:
            print("   ", line)

    if args.emit_expectations:
        print("\n--- ml/configs/legacy_archive.yaml ---")
        print(emit_expectations(found))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(found.summary(), indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")

    problems = verify(found)
    if problems:
        print(f"\nARCHIVE DOES NOT MATCH THE RECORDED LAYOUT ({len(problems)} problems):")
        for problem in problems:
            print("   ", problem)
        raise SystemExit(1)
    print("\narchive matches the recorded layout")


if __name__ == "__main__":
    main()
