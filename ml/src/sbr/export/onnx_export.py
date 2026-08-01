"""Export a trained detector to ONNX int8, and refuse to ship it if it is unfit.

The four gates in :func:`check_gates` are the reason this project can be free.
A model that fails any of them does not reach the CDN – the build fails instead.
See ``docs/04-ml-pipeline.md`` § 4 and ``docs/05-cost-model.md`` § 3.

NMS is deliberately *excluded* from the graph: it runs in TypeScript on the
the service in Python. Keeping it out of the graph keeps the export portable
across runtimes and costs ~30 lines of postprocess either way.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Hard ship gates. Changing these is a product decision, not a tuning decision.
#:
#: Inference is server-side, so model *size* no longer matters much – but
#: concurrency is the cost ceiling (docs/05-cost-model.md § 3), which makes
#: per-frame latency the budget that actually binds.
MAX_MEDIAN_LATENCY_MS = {"validator": 50.0, "identifier": 25.0}
MAX_MAP_DROP = 0.02                     # int8 may cost at most 2 mAP points
EXPORT_IMGSZ = {"validator": 448, "identifier": 320}
OPSET = 17


@dataclass
class ExportReport:
    """Everything the service and CI need to know about a model artefact."""

    role: str                      # "validator" | "identifier"
    version: int
    onnx_path: str
    size_bytes: int
    imgsz: int
    classes: list[str]
    map50_fp32: float | None = None
    map50_int8: float | None = None
    median_latency_ms: float | None = None
    quantised: bool = False

    @property
    def map_drop(self) -> float | None:
        if self.map50_fp32 is None or self.map50_int8 is None:
            return None
        return self.map50_fp32 - self.map50_int8


def check_gates(report: ExportReport) -> list[str]:
    """Return the list of failed gates. Empty means the artefact may ship.

    Model size is deliberately *not* gated: inference is server-side, so the
    artefact ships once to one machine. Latency is gated instead, because
    concurrency is what actually costs money.
    """
    failures: list[str] = []

    budget = MAX_MEDIAN_LATENCY_MS.get(report.role)
    if budget is None:
        failures.append(f"unknown model role {report.role!r}")
    elif report.median_latency_ms is not None and report.median_latency_ms > budget:
        failures.append(
            f"median latency {report.median_latency_ms:.0f} ms exceeds the "
            f"{budget:.0f} ms budget for the {report.role}"
        )

    drop = report.map_drop
    if drop is not None and drop > MAX_MAP_DROP:
        failures.append(f"int8 quantisation cost {drop:.3f} mAP (max {MAX_MAP_DROP})")

    if not report.quantised:
        failures.append("artefact is not quantised – it will not meet the latency budget")

    return failures


def export_onnx(weights: Path, out_dir: Path, imgsz: int) -> Path:
    """Export ``best.pt`` to ONNX. Returns the fp32 ONNX path."""
    from ultralytics import YOLO  # imported lazily – the web CI does not have it

    out_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(weights))
    exported = model.export(
        format="onnx",
        imgsz=imgsz,
        opset=OPSET,
        simplify=True,
        dynamic=False,
        nms=False,          # postprocess runs on device
        half=False,
    )
    exported = Path(exported)
    target = out_dir / "model-fp32.onnx"
    target.write_bytes(exported.read_bytes())
    logger.info("exported fp32 ONNX: %.2f MB", target.stat().st_size / 1e6)
    return target


def quantise(fp32_path: Path, calibration_dir: Path, out_path: Path, imgsz: int) -> Path:
    """Static int8 quantisation, calibrated on real images.

    Static, not dynamic: dynamic quantisation is measurably worse on
    convolutional detectors because the activation ranges vary enormously
    between the backbone and the head.
    """
    import numpy as np
    from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
    from PIL import Image

    images = sorted(
        p for p in calibration_dir.rglob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )[:200]
    if not images:
        raise FileNotFoundError(f"no calibration images in {calibration_dir}")

    class _Reader(CalibrationDataReader):
        def __init__(self) -> None:
            self._iter = iter(images)

        def get_next(self) -> dict | None:
            path = next(self._iter, None)
            if path is None:
                return None
            with Image.open(path) as image:
                image = image.convert("RGB").resize((imgsz, imgsz), Image.BILINEAR)
                array = np.asarray(image, dtype=np.float32).transpose(2, 0, 1) / 255.0
            return {"images": array[None, ...]}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    quantize_static(
        model_input=str(fp32_path),
        model_output=str(out_path),
        calibration_data_reader=_Reader(),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
    )
    logger.info(
        "quantised: %.2f MB -> %.2f MB",
        fp32_path.stat().st_size / 1e6,
        out_path.stat().st_size / 1e6,
    )
    return out_path


def write_sidecar(report: ExportReport, out_dir: Path) -> Path:
    """Write the JSON sidecar the inference service reads.

    Nothing about the model is hard-coded in the service – class names, input
    shape and normalisation all come from here, so a model swap needs no code
    change.
    """
    sidecar = out_dir / f"{report.role}-v{report.version}.json"
    payload = asdict(report) | {
        "normalisation": {"scale": 1 / 255.0, "mean": [0, 0, 0], "std": [1, 1, 1]},
        "input_name": "images",
        "layout": "NCHW",
        "nms": {"in_graph": False, "iou": 0.45, "score": 0.35},
    }
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return sidecar


def main() -> None:
    from sbr.taxonomy import load_taxonomy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=["validator", "identifier"], required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--map50-fp32", type=float, default=None)
    parser.add_argument("--map50-int8", type=float, default=None)
    parser.add_argument("--latency-ms", type=float, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    imgsz = EXPORT_IMGSZ[args.role]
    fp32 = export_onnx(args.weights, args.out, imgsz=imgsz)
    int8 = quantise(
        fp32, args.calibration, args.out / f"{args.role}-v{args.version}.onnx", imgsz=imgsz
    )

    classes = ["bin"] if args.role == "validator" else load_taxonomy().detector_classes
    report = ExportReport(
        role=args.role,
        version=args.version,
        onnx_path=str(int8),
        size_bytes=int8.stat().st_size,
        imgsz=imgsz,
        classes=classes,
        map50_fp32=args.map50_fp32,
        map50_int8=args.map50_int8,
        median_latency_ms=args.latency_ms,
        quantised=True,
    )
    write_sidecar(report, args.out)

    failures = check_gates(report)
    if failures:
        for failure in failures:
            logger.error("SHIP GATE FAILED: %s", failure)
        raise SystemExit(1)

    logger.info("all ship gates passed: %s", int8)


if __name__ == "__main__":
    main()
