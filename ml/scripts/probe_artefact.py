#!/usr/bin/env python3
"""Build the ungated artefacts the latency and concurrency probes measure.

    # Recreate what the load test has always run against
    python ml/scripts/probe_artefact.py --out artifacts/loadtest-artefacts

    # docs/12 P8a: the same validator at 384, everything else identical
    python ml/scripts/probe_artefact.py --out artifacts/p8/artefacts-val384 \
        --validator-imgsz 384 --roles validator

**Why this exists.** `artifacts/loadtest-artefacts/` was assembled by hand and
lives only on one laptop. It holds the trick that makes the whole measurement
possible - a stock COCO validator whose sidecar is relabelled to eighty classes
so that `service/pipeline.py`'s decoder will run against it - and without that
relabelling the load test answers HTTP 400 to every frame. A load-bearing trick
nobody can reproduce is a measurement nobody can repeat, and this project's
predecessor died of exactly that.

**Why untrained weights are sound here and nowhere else.** ONNX inference cost
depends on the op graph and the input shape, not on the values in the weights
(docs/12, "the unlock"). So a stock COCO checkpoint costs what a trained one
costs and answers the latency question honestly. It answers **no** accuracy
question at all, which is why every artefact this writes carries
`may_ship: false` and the service refuses it without `SBR_ALLOW_UNGATED=1`.

**Exporting is not training.** `sbr.config.assert_cloud()` forbids local GPU
training and does not apply: nothing here learns anything.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.export.onnx_export import (  # noqa: E402 - after the path insert
    ExportReport,
    export_onnx,
    quantise,
    sidecar_path,
    write_sidecar,
)

logger = logging.getLogger("probe_artefact")

#: The architectures docs/11 reports against, and their shipped input sizes.
ARCHITECTURES = {
    "validator": ("yolo11n.pt", 448),
    "identifier": ("yolo11s-cls.pt", 320),
}

#: Synthetic calibration images for static int8 quantisation. Noise gives wider
#: activation ranges than photographs would, which changes what the quantised
#: graph *predicts* and not what it *costs* - the op sequence is identical. This
#: script measures cost; this would be nonsense for accuracy.
CALIBRATION_IMAGES = 64

#: A stock COCO detector emits 4 + 80 channels. `pipeline.decode_detections`
#: takes the channel count from the sidecar - deliberately, so that a transposed
#: head raises instead of producing plausible boxes in the wrong places - so a
#: sidecar claiming one class over an eighty-class graph makes every frame a 400.
COCO_CLASSES = 80


def write_calibration(directory: Path, imgsz: int, count: int) -> Path:
    import numpy as np
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    for index in range(count):
        pixels = rng.integers(0, 256, (imgsz, imgsz, 3), dtype=np.uint8)
        Image.fromarray(pixels).save(directory / f"calib_{index:04d}.jpg", quality=85)
    return directory


def build(role: str, imgsz: int, out_dir: Path, version: int, keep_intermediates: bool) -> Path:
    """Export one role to int8 ONNX beside a sidecar the service will read."""
    from ultralytics import YOLO

    arch = ARCHITECTURES[role][0]
    work = out_dir / f".build-{role}"
    work.mkdir(parents=True, exist_ok=True)

    # Let ultralytics resolve and download the checkpoint, then ask it where it
    # put it. Guessing the path works until the cache location changes.
    weights = Path(YOLO(arch).ckpt_path)
    logger.info("%s: %s at %d (COCO weights - architecture is what latency depends on)", role, arch, imgsz)

    fp32 = export_onnx(weights, work, imgsz=imgsz, opset=17, role=role)
    calibration = write_calibration(work / "calib", imgsz, CALIBRATION_IMAGES)
    int8 = quantise(
        fp32,
        calibration,
        out_dir / f"{role}-probe.onnx",
        imgsz=imgsz,
        calibration_images=CALIBRATION_IMAGES,
    )

    # The relabelling. `classes` is the ONNX class index and the service reads
    # `4 + len(classes)` to orient the head, so this has to match the graph the
    # weights actually produce - not the taxonomy, which this artefact knows
    # nothing about and was never trained on.
    classes = (
        [f"coco_{index}" for index in range(COCO_CLASSES)]
        if role == "validator"
        else []
    )

    report = ExportReport(
        role=role,
        version=version,
        onnx_path=str(int8),
        size_bytes=int8.stat().st_size,
        imgsz=imgsz,
        classes=classes,
        quantised=True,
    )
    sidecar = write_sidecar(report, out_dir)

    # A note in the artefact itself, because the file outlives the terminal and
    # somebody will eventually find it and wonder what it is.
    payload: dict[str, Any] = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["note_loadtest"] = (
        f"Stock COCO {arch} at {imgsz}, relabelled to match its own output shape so the "
        "pipeline decoder will run. Latency is what is being measured; the labels are "
        "noise. gate_result.may_ship stays false and SBR_ALLOW_UNGATED is required. "
        "Built by ml/scripts/probe_artefact.py."
    )
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not keep_intermediates:
        import shutil

        shutil.rmtree(work, ignore_errors=True)

    assert payload["gate_result"]["may_ship"] is False, "a probe artefact must never be shippable"
    logger.info(
        "%s: %.2f MB, imgsz %d, %d classes, dynamic_batch=%s, may_ship=%s",
        role, int8.stat().st_size / 1e6, imgsz, len(classes),
        payload["dynamic_batch"], payload["gate_result"]["may_ship"],
    )
    return sidecar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--roles", nargs="+", default=list(ARCHITECTURES), choices=list(ARCHITECTURES))
    parser.add_argument("--validator-imgsz", type=int, default=ARCHITECTURES["validator"][1])
    parser.add_argument("--identifier-imgsz", type=int, default=ARCHITECTURES["identifier"][1])
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--keep-intermediates", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.out.mkdir(parents=True, exist_ok=True)

    sizes = {"validator": args.validator_imgsz, "identifier": args.identifier_imgsz}
    for role in args.roles:
        build(role, sizes[role], args.out, args.version, args.keep_intermediates)

    print(f"\nwrote {len(args.roles)} artefact(s) to {args.out}")
    for role in args.roles:
        print(f"  {sidecar_path(args.out, role, args.version).name}")
    print(
        "\nUNGATED by construction. The service will not serve these without "
        "SBR_ALLOW_UNGATED=1, and /health reports gated=false while it does."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
