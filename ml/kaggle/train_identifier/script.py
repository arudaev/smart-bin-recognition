#!/usr/bin/env python3
"""Smart Bin Recognition – form-factor IDENTIFIER training (Kaggle GPU kernel).

Self-contained. `scripts/dispatch.py` injects a base64 zip of `src/` + `configs/`
in place of the sentinel below, pushes this file as a kernel, and walks away.
On Kaggle the script unpacks the bundle, pulls the pinned dataset from HF,
trains, exports ONNX int8, checks the ship gates, and uploads everything back.

The laptop's only jobs are `push` and, later, `output`.
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
import os  # noqa: E402
import pathlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import zipfile  # noqa: E402

WORKING = pathlib.Path("/kaggle/working")
PROJECT = WORKING / "project"


def log(message: str) -> None:
    print(f"[sbr] {message}", flush=True)


# ---------------------------------------------------------------------------
# 1. Unpack the injected project bundle
# ---------------------------------------------------------------------------
def unpack_bundle() -> None:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError(
            "bundle sentinel was not replaced – run via scripts/dispatch.py, "
            "do not push this file directly"
        )
    PROJECT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(PROJECT_BUNDLE_B64))) as zf:
        zf.extractall(PROJECT)
    sys.path.insert(0, str(PROJECT / "src"))
    log(f"unpacked bundle to {PROJECT}")


# ---------------------------------------------------------------------------
# 2. Dependencies
# ---------------------------------------------------------------------------
def install_dependencies() -> None:
    packages = [
        "ultralytics>=8.3.0",
        "onnx>=1.16.0",
        "onnxruntime>=1.18.0",
        "huggingface_hub>=0.24.0",
        "pyyaml",
    ]
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *packages])
    log("dependencies installed")


# ---------------------------------------------------------------------------
# 3. Train
# ---------------------------------------------------------------------------
def main() -> None:
    unpack_bundle()
    install_dependencies()

    from sbr.config import load_config
    from sbr.dataset.prepare import build_yolo_tree
    from sbr.export.onnx_export import ExportReport, check_gates, export_onnx, quantise, write_sidecar
    from sbr.taxonomy import load_taxonomy
    from sbr.utils.hub import configure_hf_runtime, download_dataset, upload_artifacts

    configure_hf_runtime()
    config = load_config(CONFIG_NAME, PROJECT / "configs")
    log(f"config: {json.dumps(config, indent=2)}")

    seed = config["project"]["seed"]
    import random

    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    # --- data ---------------------------------------------------------------
    pool = download_dataset(
        config["data"]["repo_id"],
        revision=config["data"]["revision"],
        local_dir=WORKING / "pool",
    )
    data_yaml = build_yolo_tree(pool, WORKING / "dataset", config)

    # --- train --------------------------------------------------------------
    from ultralytics import YOLO

    classes = load_taxonomy().detector_classes
    log(f"{len(classes)} form-factor classes: {classes}")

    model = YOLO(f"{config['model']['arch']}.pt")
    train_args = {
        "data": str(data_yaml),
        "imgsz": config["data"]["imgsz"],
        "epochs": config["training"]["epochs"],
        "batch": config["training"]["batch"],
        "optimizer": config["training"]["optimizer"],
        "lr0": config["training"]["lr0"],
        "lrf": config["training"]["lrf"],
        "momentum": config["training"]["momentum"],
        "weight_decay": config["training"]["weight_decay"],
        "warmup_epochs": config["training"]["warmup_epochs"],
        "patience": config["training"]["patience"],
        "workers": config["training"]["workers"],
        "cos_lr": config["training"]["cos_lr"],
        "seed": seed,
        "project": str(WORKING / "runs"),
        "name": config["run_name"],
        "exist_ok": True,
        "device": 0 if torch.cuda.is_available() else "cpu",
        **config["augment"],
    }
    results = model.train(**train_args)
    best = pathlib.Path(model.trainer.save_dir) / "weights" / "best.pt"
    log(f"training done: {best}")

    # --- evaluate -----------------------------------------------------------
    metrics = model.val(data=str(data_yaml), imgsz=config["data"]["imgsz"], split="test")
    map50_fp32 = float(metrics.box.map50)
    history = {
        "map50": map50_fp32,
        "map50_95": float(metrics.box.map),
        "precision": float(metrics.box.mp),
        "recall": float(metrics.box.mr),
        "per_class_ap50": {
            name: float(metrics.box.ap50[i]) for i, name in enumerate(classes)
            if i < len(metrics.box.ap50)
        },
        "config": config,
    }
    history_path = WORKING / config["logging"]["history_file"]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    log(f"test mAP@0.5 = {map50_fp32:.4f}")

    # --- export -------------------------------------------------------------
    artifacts = WORKING / "artifacts"
    fp32 = export_onnx(best, artifacts, imgsz=config["export"]["imgsz"])
    int8 = quantise(
        fp32,
        WORKING / "dataset" / "images" / "val",
        artifacts / f"detector-v{MODEL_VERSION}.onnx",
        imgsz=config["export"]["imgsz"],
    )

    report = ExportReport(
        version=int(MODEL_VERSION),
        onnx_path=int8.name,
        size_bytes=int8.stat().st_size,
        imgsz=config["export"]["imgsz"],
        classes=classes,
        map50_fp32=map50_fp32,
        map50_int8=None,   # measured by the web-side benchmark job
        median_latency_ms=None,
        quantised=True,
    )
    sidecar = write_sidecar(report, artifacts)

    failures = check_gates(report)
    for failure in failures:
        log(f"SHIP GATE FAILED: {failure}")

    # --- upload -------------------------------------------------------------
    # Uploaded even on gate failure: the artefact is evidence for the next
    # iteration. Promotion into web/public/models/ is a separate, gated step.
    if os.environ.get("SBR_SKIP_UPLOAD") != "1":
        upload_artifacts(
            repo_id=config["hub"]["model_repo"],
            files={
                f"v{MODEL_VERSION}/best.pt": best,
                f"v{MODEL_VERSION}/{int8.name}": int8,
                f"v{MODEL_VERSION}/{sidecar.name}": sidecar,
                f"v{MODEL_VERSION}/history.json": history_path,
            },
            commit_message=f"detector v{MODEL_VERSION}: mAP50={map50_fp32:.4f}",
            private=config["hub"]["private"],
        )

    if failures:
        raise SystemExit(1)
    log("all ship gates passed")


if __name__ == "__main__":
    main()
