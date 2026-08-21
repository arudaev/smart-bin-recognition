#!/usr/bin/env python3
"""Model B – the IDENTIFIER. "What kind of bin is it?" (Kaggle GPU kernel)

A **classifier** over crops, not a detector. The validator has already localised
the object and the crop is filled by it, so re-detecting would spend the 25 ms
budget re-deriving a box that is already known. Classification also makes
``unknown`` principled: a max-softmax below the configured threshold, rather
than a box score below a confidence floor.

Its classes are physical form factors in taxonomy file order – **that order is
the ONNX class index** and reordering it silently invalidates every deployed
model.

It trains only on **adjudicated** crops. A crop whose form factor was inferred
from a legacy stream label is not a label, and ``build_classification_tree``
stops rather than inventing one. Until the human pass has run, this kernel is
expected to fail early and say why.
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
ROLE = "identifier"


def log(message: str) -> None:
    print(f"[sbr] {message}", flush=True)


def unpack_bundle() -> None:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError(
            "bundle sentinel was not replaced – run via scripts/dispatch.py, "
            "do not push this file directly"
        )
    PROJECT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(PROJECT_BUNDLE_B64))) as archive:
        archive.extractall(PROJECT)
    sys.path.insert(0, str(PROJECT / "ml" / "src"))
    log(f"unpacked bundle to {PROJECT}")


def install_dependencies() -> None:
    """Install what the kernel needs without letting pip decide about torch.

    ``--no-deps`` is hygiene rather than a fix, and it is worth being exact
    about which: ``pip install ultralytics`` *does* resolve its own torch, and
    that was the first suspect for the 2026-08-16 failure. It was wrong. A rung
    that installs nothing at all (``smoke_gpu``) found the image already ships
    torch 2.10.0+cu128 against a P100 at sm_60, so **the mismatch arrives with
    the image**. See ``sbr.utils.gpu``.

    Keeping pip away from torch is still right - a resolver that swapped it
    would add a second, harder-to-see cause on top of the first - and it is
    faster. Everything else ultralytics needs is already in the Kaggle image;
    ``ultralytics-thop`` is the one that is not, so it is named.
    """
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "--no-deps",
         "ultralytics>=8.3.0", "ultralytics-thop"]
    )
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q",
         "onnx>=1.16.0", "onnxruntime>=1.18.0", "huggingface_hub>=1.2.0", "pyyaml"]
    )
    log("dependencies installed (torch left exactly as the image shipped it)")


def seed_everything(seed: int) -> None:
    import random

    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    log(f"seeded torch / numpy / random / cuda with {seed}")


def unknown_rate(model, tree: pathlib.Path, threshold: float, imgsz: int) -> dict:
    """How often the identifier declines to answer, and how often it is right to.

    ``unknown`` is a designed product state and the entry point to the
    improvement loop, so its rate is a headline number rather than a footnote:
    an identifier that never says unknown is not being honest, and one that
    always does is not useful.
    """
    test = tree / "test"
    if not test.exists():
        return {}

    total = confident = correct_when_confident = 0
    for class_dir in sorted(p for p in test.iterdir() if p.is_dir()):
        for image in sorted(class_dir.glob("*.jpg")):
            result = model.predict(str(image), imgsz=imgsz, verbose=False)[0]
            probabilities = result.probs
            total += 1
            if probabilities.top1conf.item() >= threshold:
                confident += 1
                if result.names[probabilities.top1] == class_dir.name:
                    correct_when_confident += 1

    summary = {
        "crops": total,
        "threshold": threshold,
        "answered": confident,
        "unknown_rate": round(1 - confident / total, 4) if total else None,
        "accuracy_when_answering": round(correct_when_confident / confident, 4) if confident else None,
    }
    log(f"unknown behaviour: {json.dumps(summary)}")
    return summary


def main() -> None:
    unpack_bundle()
    install_dependencies()

    from sbr.config import load_config
    from sbr.dataset.prepare import build_classification_tree
    from sbr.export.onnx_export import (
        ExportReport,
        Gates,
        calibration_frames,
        check_gates,
        evaluate_int8,
        export_onnx,
        quantise,
        write_sidecar,
    )
    from sbr.utils.gpu import require_usable_gpu
    from sbr.utils.hub import (
        configure_hf_runtime,
        download_dataset,
        require_hf_token,
        resolve_revision,
        upload_artifacts,
    )

    configure_hf_runtime()
    # Before a GPU hour, not after.
    if os.environ.get("SBR_SKIP_UPLOAD") != "1":
        require_hf_token("upload the trained artefacts")
    config = load_config(CONFIG_NAME, PROJECT / "ml" / "configs")
    log(f"config: {json.dumps(config, indent=2)}")
    seed_everything(config["project"]["seed"])

    # --- the GPU, BEFORE the pull ------------------------------------------- #
    # See sbr.utils.gpu, and train_validator for why this is here rather than
    # beside model.train(): refusing after the data is downloaded costs most of
    # what the failed run cost.
    accelerator = require_usable_gpu("train the identifier")

    # --- data -------------------------------------------------------------- #
    # The revision the run ACTUALLY used, not the config's literal. P10's first
    # report wrote `"revision": "main"` beside a composition that matched the pin
    # exactly - the data was right and the record of it was not, and a report
    # that names its pin as "main" is one nobody can reproduce from.
    revision = resolve_revision(
        config["data"]["repo_id"], config["data"]["revision"], strict=True
    )
    pool = download_dataset(
        config["data"]["repo_id"],
        revision=revision,
        local_dir=WORKING / "pool",
        strict=True,
    )
    tree = WORKING / "crops"
    # Raises SystemExit when nothing has been adjudicated, which is the expected
    # state until the human pass has run.
    build_classification_tree(pool, tree, config)
    composition = json.loads((tree / "classification.json").read_text(encoding="utf-8"))
    log(f"composition: {json.dumps(composition)}")

    present = list(composition["classes_present"])
    if composition["classes_absent"]:
        log(
            "TRAINING ON FEWER CLASSES THAN THE TAXONOMY DEFINES. No data for: "
            f"{composition['classes_absent']}. The results doc must name these."
        )

    # --- train ------------------------------------------------------------- #
    from ultralytics import YOLO

    model = YOLO(f"{config['model']['arch']}.pt")
    results = model.train(
        data=str(tree),
        imgsz=config["data"]["imgsz"],
        epochs=config["training"]["epochs"],
        batch=config["training"]["batch"],
        optimizer=config["training"]["optimizer"],
        lr0=config["training"]["lr0"],
        lrf=config["training"]["lrf"],
        momentum=config["training"]["momentum"],
        weight_decay=config["training"]["weight_decay"],
        warmup_epochs=config["training"]["warmup_epochs"],
        patience=config["training"]["patience"],
        workers=config["training"]["workers"],
        cos_lr=config["training"]["cos_lr"],
        seed=config["project"]["seed"],
        project=str(WORKING / "runs"),
        name=config["run_name"],
        exist_ok=True,
        device=accelerator.device,
        **config["augment"],
    )
    best = pathlib.Path(model.trainer.save_dir) / "weights" / "best.pt"
    log(f"training done: {best} (final fitness {getattr(results, 'fitness', None)})")

    # --- evaluate ----------------------------------------------------------- #
    metrics = model.val(data=str(tree), imgsz=config["data"]["imgsz"], split="test")
    top1 = float(metrics.top1)

    history = {
        "role": ROLE,
        "version": int(MODEL_VERSION),
        "dataset": {
            "repo_id": config["data"]["repo_id"],
            "revision": revision,
            "composition": composition,
        },
        "test": {"top1": top1, "top5": float(metrics.top5)},
        "unknown": unknown_rate(
            model, tree, config["inference"]["unknown_threshold"], config["data"]["imgsz"]
        ),
        "classes_trained": present,
        "classes_without_data": composition["classes_absent"],
        "config": config,
    }
    history_path = WORKING / config["logging"]["history_file"]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    log(f"test top-1 = {top1:.4f}")

    # --- export ------------------------------------------------------------- #
    artifacts = WORKING / "artifacts"
    fp32 = export_onnx(
        best, artifacts, imgsz=config["export"]["imgsz"], opset=config["export"]["opset"], role=ROLE
    )
    # A classification tree carries no label files, so the positive/background
    # split a detection calibration reports is not a thing here - every crop is
    # a bin. `stratified` still matters: it samples across the class
    # directories rather than taking whichever class sorts first.
    calibration = calibration_frames(
        tree,
        "val",
        config["export"]["calibration_images"],
        strategy="stratified",
        seed=config["project"]["seed"],
    )
    log(f"calibration set: {json.dumps(calibration.as_dict())}")
    int8 = quantise(
        fp32,
        calibration,
        artifacts / f"{ROLE}-v{MODEL_VERSION}.onnx",
        imgsz=config["export"]["imgsz"],
    )

    # Gate 3 is fp32-vs-int8, so int8 has to be scored on the SAME split the
    # fp32 number came from - which only this machine still has.
    top1_int8 = evaluate_int8(
        int8, role=ROLE, data=tree, imgsz=config["data"]["imgsz"], split="test"
    )
    history["test"]["top1_int8"] = top1_int8
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    gates = Gates.from_config(ROLE, config)
    report = ExportReport(
        role=ROLE,
        version=int(MODEL_VERSION),
        onnx_path=int8.name,
        size_bytes=int8.stat().st_size,
        imgsz=config["export"]["imgsz"],
        # The model's OWN class order, read back from the trained model.
        #
        # This is not the taxonomy's file order and must not be assumed to be:
        # Ultralytics builds a classification dataset from the directory names,
        # so the output index is alphabetical over the classes that actually had
        # crops. The sidecar is what the service reads, so the sidecar carries
        # the truth - which is also why a class gaining data later cannot
        # silently remap a deployed model, as long as this is read and not
        # guessed. The form-factor IDS remain canonical and permanent; only
        # their position in this particular head is incidental.
        classes=[model.names[index] for index in sorted(model.names)],
        quantised=True,
        top1_fp32=top1,
        top1_int8=top1_int8,
        median_latency_ms=None,  # measured on the 2-vCPU bench, not here
        # docs/04 7's target. There is no held-out city to measure it on, so it
        # reports UNMEASURABLE rather than being quietly omitted - which is the
        # whole point of carrying it (docs/04 5, docs/07 phase 2).
        targets_measured={"min_formfactor_acc_heldout_city": None},
    )
    sidecar = write_sidecar(report, artifacts, gates)
    check_gates(report, gates).log()

    # --- upload ------------------------------------------------------------- #
    if os.environ.get("SBR_SKIP_UPLOAD") != "1":
        upload_artifacts(
            repo_id=config["hub"]["model_repo"],
            files={
                f"v{MODEL_VERSION}/best.pt": best,
                f"v{MODEL_VERSION}/{int8.name}": int8,
                f"v{MODEL_VERSION}/{sidecar.name}": sidecar,
                f"v{MODEL_VERSION}/history.json": history_path,
            },
            commit_message=f"{ROLE} v{MODEL_VERSION}: test top1={top1:.4f}",
            private=config["hub"]["private"],
        )

    log(
        f"exported {int8.name}. Latency is unmeasured by design - run "
        f"`python ml/scripts/gate.py --role {ROLE} --version {MODEL_VERSION}` to decide shipping."
    )


if __name__ == "__main__":
    main()
