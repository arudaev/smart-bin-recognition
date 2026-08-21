#!/usr/bin/env python3
"""Probes P4 and P5: the latency half of the phase-2 gate, without a model.

``docs/12-validation-protocol.md`` states the unlock this kernel exists to use:
ONNX inference cost depends on **architecture and input shape, not on learned
weights**. An untrained ``yolo11n`` at 448 and an untrained ``yolo11s-cls`` at
320, exported and quantised, cost the same per frame as trained ones. So both
probes run today, before a single GPU hour is spent, and if the architecture
misses budget that is far better learned now.

**P4 – multi-bin cost curve.** What a frame costs at 0, 1, 3 and 6 bins, and
whether pushing the crops through one ONNX call beats pushing them through *n*.
docs/05 § 3 budgets 65 ms/frame = validator + **one** crop while the PRD calls a
bank of six a normal input; at six the frame is 40 + 6x25 = 190 ms and the
concurrency ceiling falls from ~10 to ~3.5. The cost model and the product spec
currently describe different products, and this is the measurement that settles
which one is real.

**P5 – validator architecture.** Whether RF-DETR-nano or D-FINE-N fits 50 ms at
448 on two pinned vCPUs. Research note 01 § 3 reports DETR backbones generalising
better from small data, which is our regime, but the published comparisons are on
GPU. Latency first: only a candidate that fits the budget makes accuracy a
question worth a GPU hour.

**What this kernel deliberately does not claim.** The weights are untrained and
the int8 calibration is synthetic. Both are fine for latency and worthless for
accuracy, and every number emitted here says so. The artefacts it writes carry
``may_ship: false`` and the inference service will refuse them, which is the
correct behaviour and is asserted rather than assumed.
"""

# ---------------------------------------------------------------------------
# 0. Bundle – injected by dispatch.py
# ---------------------------------------------------------------------------
PROJECT_BUNDLE_B64 = "__SBR_PROJECT_BUNDLE_B64__"
CONFIG_NAME = "__SBR_CONFIG_NAME__"
MODEL_VERSION = "__SBR_MODEL_VERSION__"

import base64  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import zipfile  # noqa: E402

WORKING = pathlib.Path("/kaggle/working")
PROJECT = WORKING / "project"

#: The scene complexities docs/12 P4 names. 0 is the empty frame – the validator
#: alone – and it is what separates "the detector costs X" from "a frame costs X".
CROP_COUNTS = (0, 1, 3, 6)

#: Fewer iterations than the ship-gate bench: this grid runs 4 x 2 composites plus
#: the P5 candidates, and each composite already runs several forward passes.
ITERATIONS = 30
WARMUP = 8

#: Synthetic calibration images for static int8 quantisation. Noise gives wider
#: activation ranges than photographs would, which changes what the quantised
#: graph *predicts* and not what it *costs* - the op sequence is identical. This
#: kernel measures cost, so this is sound; it would be nonsense for accuracy.
CALIBRATION_IMAGES = 64


def log(message: str) -> None:
    print(f"[sbr] {message}", flush=True)


def unpack_bundle() -> None:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError(
            "bundle sentinel was not replaced - run via scripts/dispatch.py, "
            "do not push this file directly"
        )
    PROJECT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(PROJECT_BUNDLE_B64))) as archive:
        archive.extractall(PROJECT)
    sys.path.insert(0, str(PROJECT / "ml" / "src"))
    log(f"unpacked bundle to {PROJECT}")


def install_dependencies() -> None:
    subprocess.check_call(
        [
            sys.executable, "-m", "pip", "install", "-q",
            "ultralytics>=8.3.0", "onnx>=1.16.0", "onnxruntime==1.29.0",
            "pyyaml", "numpy", "pillow",
        ]
    )
    log("core dependencies installed")


def write_calibration(directory: pathlib.Path, imgsz: int, count: int) -> pathlib.Path:
    """Synthetic calibration images. See CALIBRATION_IMAGES for why this is sound."""
    import numpy as np
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    for index in range(count):
        pixels = rng.integers(0, 256, (imgsz, imgsz, 3), dtype=np.uint8)
        Image.fromarray(pixels).save(directory / f"calib_{index:04d}.jpg", quality=85)
    return directory


def build_artefact(role: str, arch: str, imgsz: int, out_dir: pathlib.Path) -> tuple[pathlib.Path, dict]:
    """Export an architecture to int8 ONNX, and write its sidecar.

    The checkpoint is a stock COCO one, **untrained on this project's data**. It
    is here for its architecture and nothing else: what a forward pass costs is
    decided by the op graph and the input shape, and a weight value cannot change
    how many multiply-accumulates happen.

    The sidecar goes through ``write_sidecar`` rather than being hand-assembled,
    so this exercises the same contract the service reads. It will say
    ``may_ship: false`` - accuracy is unmeasured because there is nothing to
    measure - and that is the point rather than a shortcoming.
    """
    from ultralytics import YOLO

    from sbr.export.onnx_export import ExportReport, export_onnx, quantise, sidecar_path, write_sidecar

    # One directory per role: export_onnx writes a fixed `model-fp32.onnx`, and
    # two roles sharing a directory would have the second silently overwrite the
    # first's intermediate.
    role_dir = out_dir / role
    role_dir.mkdir(parents=True, exist_ok=True)

    # Let ultralytics resolve and download the checkpoint, then ask it where it
    # put it. Guessing the path works until the cache location changes.
    weights = pathlib.Path(YOLO(arch).ckpt_path)
    log(f"{role}: {arch} at {imgsz} (COCO weights - architecture is what latency depends on)")

    fp32 = export_onnx(weights, role_dir, imgsz=imgsz, opset=17, role=role)
    calibration = write_calibration(role_dir / "calib", imgsz, CALIBRATION_IMAGES)
    int8 = quantise(
        fp32,
        calibration,
        role_dir / f"{role}-probe.onnx",
        imgsz=imgsz,
        calibration_images=CALIBRATION_IMAGES,
    )

    report = ExportReport(
        role=role,
        version=int(MODEL_VERSION),
        onnx_path=str(int8),
        size_bytes=int8.stat().st_size,
        imgsz=imgsz,
        classes=["bin"] if role == "validator" else [],
        quantised=True,
    )
    write_sidecar(report, role_dir)
    sidecar = json.loads(sidecar_path(role_dir, role, int(MODEL_VERSION)).read_text(encoding="utf-8"))
    log(
        f"{role}: int8 {int8.stat().st_size / 1e6:.2f} MB, "
        f"dynamic_batch={sidecar['dynamic_batch']}, may_ship={sidecar['gate_result']['may_ship']}"
    )
    return int8, sidecar


# --------------------------------------------------------------------------- #
# P4
# --------------------------------------------------------------------------- #


def probe_p4(out_dir: pathlib.Path) -> dict:
    from sbr.bench import Graph, bench_frame, open_session

    validator_path, validator_sidecar = build_artefact("validator", "yolo11n.pt", 448, out_dir)
    identifier_path, identifier_sidecar = build_artefact("identifier", "yolo11s-cls.pt", 320, out_dir)

    validator = Graph(open_session(validator_path), validator_sidecar)
    identifier = Graph(open_session(identifier_path), identifier_sidecar)

    # The graphs on their own, which is what the ship gate budgets.
    from sbr.bench import measure

    solo = {
        "validator": measure(validator.session, validator_sidecar, ITERATIONS, WARMUP),
        "identifier": measure(identifier.session, identifier_sidecar, ITERATIONS, WARMUP),
    }
    log(
        f"solo: validator p50 {solo['validator']['median_latency_ms']:.1f} ms @448, "
        f"identifier p50 {solo['identifier']['median_latency_ms']:.1f} ms @320"
    )

    # The identifier alone, at each batch size. This is what lets a frame's cost
    # be decomposed rather than merely stated: the 2026-08-16 run found a one-crop
    # frame costing 65.7 ms against 44.0 ms of graph time, and "where did 22 ms
    # go" is not answerable from the composite alone.
    identifier_batches = {
        str(n): measure(identifier.session, identifier_sidecar, ITERATIONS, WARMUP, batch=n)
        for n in CROP_COUNTS
        if n > 0
    }
    for n, m in identifier_batches.items():
        log(f"identifier alone at batch {n}: p50 {m['median_latency_ms']:.1f} ms")

    curve = []
    for crops in CROP_COUNTS:
        modes = [False] if crops == 0 else [True, False]
        for batched in modes:
            result = bench_frame(
                validator, identifier, crops,
                batched=batched, iterations=ITERATIONS, warmup=WARMUP,
            )
            curve.append(result)
            log(
                f"frame: {crops} crop(s), batched={batched} -> "
                f"p50 {result['median_latency_ms']:.1f} ms, p95 {result['p95_latency_ms']:.1f} ms"
            )

    return {
        "solo": solo,
        "identifier_batches": identifier_batches,
        "curve": curve,
        "validator_sidecar": validator_sidecar,
        "identifier_sidecar": identifier_sidecar,
    }


# --------------------------------------------------------------------------- #
# P5
# --------------------------------------------------------------------------- #


def probe_p5(out_dir: pathlib.Path) -> dict:
    """Time the DETR-family candidates at 448 on the same pinned threads.

    Each candidate is attempted independently. A candidate that cannot be
    installed or exported is reported as **not evaluated, and why** - which is a
    different outcome from "did not fit the budget" and must not be collapsed
    into it, because docs/12's decision rule for P5 turns on whether a candidate
    fits and an unevaluated candidate has not answered that.
    """
    results: dict[str, dict] = {}

    for name, builder in (("rf-detr-nano", _export_rfdetr), ("d-fine-nano", _export_dfine)):
        try:
            results[name] = builder(out_dir)
            log(f"{name}: p50 {results[name]['median_latency_ms']:.1f} ms @448")
        except Exception as error:  # noqa: BLE001 - "not evaluated" is a reportable outcome
            log(f"{name}: NOT EVALUATED ({type(error).__name__}: {error})")
            results[name] = {
                "evaluated": False,
                "reason": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc(limit=3),
            }

    return results


def _time_session(onnx_path: pathlib.Path, imgsz: int, input_name: str) -> dict:
    from sbr.bench import measure, open_session

    session = open_session(onnx_path)
    sidecar = {"imgsz": imgsz, "input_name": input_name}
    return {"evaluated": True, **measure(session, sidecar, ITERATIONS, WARMUP)}


def _export_rfdetr(out_dir: pathlib.Path) -> dict:
    # `simplify` and `opset_version` were rejected as unexpected keywords on the
    # 2026-08-16 run. The export defaults are fine for a latency measurement, so
    # nothing is passed that is not needed.
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "rfdetr", "onnxscript"])
    from rfdetr import RFDETRNano

    target = out_dir / "rfdetr"
    RFDETRNano(resolution=448).export(output_dir=str(target))
    onnx = next(target.rglob("*.onnx"))

    import onnxruntime as ort

    name = ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"]).get_inputs()[0].name
    return _time_session(onnx, 448, name)


def _export_dfine(out_dir: pathlib.Path) -> dict:
    """D-FINE via transformers, which is where it actually ships.

    ``onnxscript`` is an explicit dependency: torch's exporter now defaults to
    the dynamo path, which needs it, and its absence was what stopped this
    candidate being evaluated on the 2026-08-16 run. ``dynamo=False`` keeps the
    older tracing exporter, which handles this graph without it.
    """
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "transformers>=4.48", "torch", "onnxscript"]
    )
    import torch
    from transformers import DFineForObjectDetection

    model = DFineForObjectDetection.from_pretrained("ustc-community/dfine-nano-coco").eval()
    onnx = out_dir / "dfine-nano.onnx"
    dummy = torch.randn(1, 3, 448, 448)
    with torch.no_grad():
        torch.onnx.export(
            model, (dummy,), str(onnx),
            input_names=["images"], opset_version=17, do_constant_folding=True, dynamo=False,
        )
    return _time_session(onnx, 448, "images")


# --------------------------------------------------------------------------- #


def main() -> None:
    unpack_bundle()
    install_dependencies()

    from sbr.bench import hardware

    machine = hardware()
    log(f"measuring on: {machine.label}")
    if not machine.representative:
        log("NOTE: a proxy for the service container, not the service. Every number says so.")

    out_dir = WORKING / "probe"
    started = time.time()

    payload = {
        "probe": ["P4", "P5"],
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": machine.as_dict(),
        "weights": (
            "UNTRAINED on this project's data - stock COCO checkpoints, used only for their "
            "architecture. Valid for latency, which depends on architecture and input shape; "
            "meaningless for accuracy, which is not measured here."
        ),
        "int8_calibration": "synthetic noise - see CALIBRATION_IMAGES",
        "iterations": ITERATIONS,
        "warmup": WARMUP,
    }

    payload["p4"] = probe_p4(out_dir)
    payload["p5"] = probe_p5(out_dir)
    payload["elapsed_s"] = round(time.time() - started, 1)

    out = WORKING / "probe-latency.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log(json.dumps(payload, indent=2))
    log(f"wrote {out}")


if __name__ == "__main__":
    main()
