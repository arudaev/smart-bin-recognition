#!/usr/bin/env python3
"""Benchmark and honestly evaluate the predecessor's model on CPU.

UNVERIFIED - written against an incomplete copy of the legacy archive, so its
assumptions about layout must be re-checked before its output is trusted.

The measurements now recorded in docs/08-legacy-audit.md section 7 were NOT
produced by this script; they were produced ad hoc against the complete archive.
Reconcile this script with that method before using it, and prefer the recorded
figures over anything it prints today.

    python ml/scripts/benchmark_legacy.py --archive-dir cv_garbage

Why this exists: the predecessor's README claims mAP@0.5 = 95.2 %. Even if that
reproduces, it measures memorisation of one week of photographs in one town.
Reproducing it independently is what keeps this project honest about what it
actually inherited - and it is the phase-2 test of whether detection really does
generalise better than identification (docs/01-architecture.md section 3).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import time
from collections import Counter, defaultdict

from ultralytics import YOLO

LEGACY_NAMES = {0: "Biomull", 1: "Glas", 2: "Papier", 3: "Restmull"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def resolve_pairs(root: pathlib.Path) -> dict[str, tuple[pathlib.Path, str]]:
    """Map label filename -> (image path, split).

    Labels and images live in different trees, linked by a hash suffix.
    ``_pairs.json`` records the split; its image names are mojibake, so the
    image itself is located by hash rather than by name.
    """
    pairs_file = root / "_pairs.json"
    if not pairs_file.exists():
        pairs_file = root.parent / "_pairs.json"
    pairs = json.loads(pairs_file.read_text(encoding="utf-8"))

    by_hash: dict[str, pathlib.Path] = {}
    for person_dir in (root / "labeled").iterdir():
        if person_dir.is_dir():
            for path in person_dir.iterdir():
                if path.suffix.lower() in IMAGE_SUFFIXES:
                    by_hash.setdefault(path.stem.split("_")[-1].lower(), path)

    resolved: dict[str, tuple[pathlib.Path, str]] = {}
    for label_rel, image_rel, split in pairs:
        key = pathlib.Path(image_rel).stem.split("_")[-1].lower()
        if key in by_hash:
            resolved[pathlib.Path(label_rel).name] = (by_hash[key], split)

    print(f"pairs: {len(pairs)}  resolved: {len(resolved)}")
    return resolved


def benchmark_latency(model: YOLO, samples: list[pathlib.Path]) -> None:
    for imgsz in (448, 640, 960):
        model.predict(samples[0], imgsz=imgsz, verbose=False, device="cpu")  # warm-up
        times = []
        for path in samples:
            start = time.perf_counter()
            model.predict(path, imgsz=imgsz, verbose=False, device="cpu")
            times.append((time.perf_counter() - start) * 1000)
        median = statistics.median(times)
        p90 = sorted(times)[int(len(times) * 0.9)]
        print(f"imgsz {imgsz:4d}: median {median:7.1f} ms  p90 {p90:7.1f} ms  ({1000 / median:.2f} fps)")


def evaluate(model: YOLO, root: pathlib.Path, resolved: dict) -> None:
    val = [(name, path) for name, (path, split) in resolved.items() if split == "val"]
    print(f"\nevaluating {len(val)} val images @ conf=0.25, imgsz=960")

    tp = fn = fp = 0
    detected_any = 0
    confusion: dict[int, Counter] = defaultdict(Counter)

    for label_name, image_path in val:
        label = next(root.glob(f"YOLO_Dataset/labels/*/{label_name}"), None)
        if label is None:
            continue
        truth = [int(line.split()[0]) for line in label.read_text().splitlines() if line.strip()]
        result = model.predict(image_path, imgsz=960, conf=0.25, iou=0.45,
                               verbose=False, device="cpu")[0]
        predicted = [int(box.cls[0]) for box in result.boxes]
        if predicted:
            detected_any += 1

        truth_counts, pred_counts = Counter(truth), Counter(predicted)
        for cls in set(truth_counts) | set(pred_counts):
            matched = min(truth_counts[cls], pred_counts[cls])
            tp += matched
            fn += max(0, truth_counts[cls] - pred_counts[cls])
            fp += max(0, pred_counts[cls] - truth_counts[cls])

        if len(truth) == 1 and predicted:
            confusion[truth[0]][predicted[0]] += 1

    print("\nbox-level (class-aware, count-matched):")
    print(f"  TP {tp}  FP {fp}  FN {fn}")
    print(f"  precision {tp / (tp + fp + 1e-9):.3f}  recall {tp / (tp + fn + 1e-9):.3f}")
    print(f"  images with >=1 detection: {detected_any}/{len(val)} = {detected_any / len(val):.1%}")

    print("\nconfusion (single-bin images, truth -> top prediction):")
    print("            " + "".join(f"{LEGACY_NAMES[c]:>10s}" for c in range(4)))
    for truth_cls in range(4):
        row = "".join(f"{confusion[truth_cls][p]:>10d}" for p in range(4))
        print(f"  {LEGACY_NAMES[truth_cls]:10s}{row}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=pathlib.Path, default=pathlib.Path("cv_garbage"))
    parser.add_argument("--weights", type=str, default="models/waste_detector_best.pt")
    args = parser.parse_args()

    root = args.archive_dir.resolve()
    resolved = resolve_pairs(root)
    model = YOLO(str(root / args.weights))

    samples = [path for path, _ in list(resolved.values())[:12]]
    benchmark_latency(model, samples)
    evaluate(model, root, resolved)


if __name__ == "__main__":
    main()
