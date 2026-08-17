#!/usr/bin/env python3
"""Model A – the VALIDATOR. "Is there a bin, and where?" (Kaggle GPU kernel)

Self-contained. ``scripts/dispatch.py`` injects a base64 zip of ``src/`` and
``configs/`` in place of the sentinel below, pushes this file as a kernel, and
walks away. On Kaggle it unpacks the bundle, pulls the **pinned** dataset from
HF, trains, evaluates, exports ONNX int8, and uploads everything back.

One class, ``bin``, class-agnostic on purpose: it must fire on a bin type it has
never seen, because that is exactly the case the improvement loop depends on
detecting. Most of its training data is not bins at all.

**This kernel does not decide whether the model ships.** It cannot: the latency
budget is stated on service CPU and this machine has a GPU and somebody else's
CPU. It exports with latency unmeasured – a distinct verdict from passing – and
``ml/scripts/gate.py`` decides once the 2-vCPU bench has spoken.
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
ROLE = "validator"


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
    # These carry no torch dependency, so they may resolve normally.
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q",
         "onnx>=1.16.0", "onnxruntime>=1.18.0", "huggingface_hub>=1.2.0", "pyyaml"]
    )
    log("dependencies installed (torch left exactly as the image shipped it)")


def seed_everything(seed: int) -> None:
    """Seed every source of randomness a run touches. Non-negotiable."""
    import random

    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    log(f"seeded torch / numpy / random / cuda with {seed}")


def recall_by_bins_per_frame(model, data_yaml, tree, config) -> dict:
    """Detection recall bucketed by how many bins are in the frame.

    docs/04 § 5 commits to this so that a model which only works on one big
    centred bin cannot hide behind an aggregate. The legacy archive has no frame
    with four or more bins, so a `4+` bucket appears only once the Open Images
    and Commons subsets are in the pool - and its absence is itself a result.
    """
    import yaml

    buckets: dict[str, dict[str, int]] = {}
    labels_dir = tree / "labels" / "test"
    images_dir = tree / "images" / "test"
    if not labels_dir.exists():
        return {}

    for label in sorted(labels_dir.glob("*.txt")):
        truth = [line for line in label.read_text().splitlines() if line.strip()]
        if not truth:
            continue
        image = next((p for p in images_dir.glob(f"{label.stem}.*")), None)
        if image is None:
            continue

        key = "4+" if len(truth) >= 4 else str(len(truth))
        bucket = buckets.setdefault(key, {"frames": 0, "truth_boxes": 0, "detected": 0})
        bucket["frames"] += 1
        bucket["truth_boxes"] += len(truth)

        result = model.predict(
            str(image), imgsz=config["data"]["imgsz"], conf=0.25, iou=0.45, verbose=False
        )[0]
        # Box-count recall, not IoU matching: the question here is whether a
        # crowded frame loses bins, and the aggregate mAP already covers quality.
        bucket["detected"] += min(len(result.boxes), len(truth))

    for bucket in buckets.values():
        bucket["recall"] = round(bucket["detected"] / bucket["truth_boxes"], 4) if bucket["truth_boxes"] else None

    log(f"recall by bins-per-frame: {json.dumps(buckets)}")
    del yaml
    return buckets


def precision_on_negatives(model, tree, config) -> dict:
    """How often the validator fires on an image with no bin in it.

    The predecessor hallucinated a glass container on a slide of black text on
    white. This is the number that says whether that is fixed.
    """
    labels_dir = tree / "labels" / "test"
    images_dir = tree / "images" / "test"
    if not labels_dir.exists():
        return {}

    negatives = [
        label for label in sorted(labels_dir.glob("*.txt"))
        if not label.read_text().strip()
    ]
    if not negatives:
        log("no background images in the test split - precision on negatives unmeasured")
        return {}

    false_positive_frames = 0
    for label in negatives:
        image = next((p for p in images_dir.glob(f"{label.stem}.*")), None)
        if image is None:
            continue
        result = model.predict(
            str(image), imgsz=config["data"]["imgsz"], conf=0.25, iou=0.45, verbose=False
        )[0]
        if len(result.boxes):
            false_positive_frames += 1

    summary = {
        "negative_frames": len(negatives),
        "frames_with_a_false_positive": false_positive_frames,
        "frame_level_specificity": round(1 - false_positive_frames / len(negatives), 4),
    }
    log(f"negatives: {json.dumps(summary)}")
    return summary


def main() -> None:
    unpack_bundle()
    install_dependencies()

    from sbr.config import load_config
    from sbr.dataset.expected import check_composition, expectation_for
    from sbr.dataset.prepare import build_yolo_tree
    from sbr.export.onnx_export import (
        ExportReport,
        Gates,
        check_gates,
        evaluate_int8,
        export_onnx,
        quantise,
        write_sidecar,
    )
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

    # --- data -------------------------------------------------------------- #
    # strict=True: an unpinned revision stops the run. A number measured against
    # a moving target cannot be reproduced, and that is the one failure this
    # repo exists not to repeat.
    pool = download_dataset(
        config["data"]["repo_id"],
        revision=config["data"]["revision"],
        local_dir=WORKING / "pool",
        strict=True,
    )
    tree = WORKING / "dataset"
    data_yaml = build_yolo_tree(pool, tree, config)
    composition = json.loads((tree / "composition.json").read_text(encoding="utf-8"))
    log(f"composition: {json.dumps(composition)}")

    # BEFORE THE GPU HOUR, not after it. A pin says which data; it does not say
    # what is in it. The 2026-08-16 run got this far, reported background_images:
    # 0 over a pool that is 92 % background, and trained anyway - the number was
    # right there in the log and nothing was watching it. This is what watches.
    expectation = expectation_for(config["data"]["repo_id"])
    if expectation is None:
        log(f"no composition contract for {config['data']['repo_id']} - proceeding unchecked")
    else:
        resolved = resolve_revision(config["data"]["repo_id"], config["data"]["revision"], strict=True)
        if resolved != expectation.revision:
            raise SystemExit(
                f"this run resolved {resolved[:12]} but sbr.dataset.expected describes "
                f"{expectation.revision[:12]}. Pinning new data is a deliberate act: update "
                "the contract in the same commit as the pin, with the reason in the message."
            )
        check_composition(composition, expectation)
        log(
            f"composition matches the contract for {expectation.revision[:12]}: "
            f"{expectation.total_frames} frames = {expectation.background_frames} background "
            f"+ {expectation.positive_frames} positive. Negative ratio "
            f"{json.dumps(expectation.ratios())}"
        )

    # --- train ------------------------------------------------------------- #
    from ultralytics import YOLO

    from sbr.utils.gpu import require_usable_gpu

    # BEFORE Ultralytics, not inside it. `torch.cuda.is_available()` answers
    # "is there a device", not "was this torch compiled for it", and the gap
    # between those two questions is what produced a run with no weights and no
    # log on 2026-08-16.
    accelerator = require_usable_gpu("train the validator")

    classes = composition["classes"]
    if classes != ["bin"]:
        raise SystemExit(
            f"the validator is class-agnostic and must train on exactly ['bin']; got {classes}"
        )

    model = YOLO(f"{config['model']['arch']}.pt")
    results = model.train(
        data=str(data_yaml),
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
    metrics = model.val(data=str(data_yaml), imgsz=config["data"]["imgsz"], split="test")
    map50 = float(metrics.box.map50)

    history = {
        "role": ROLE,
        "version": int(MODEL_VERSION),
        "dataset": {
            "repo_id": config["data"]["repo_id"],
            "revision": config["data"]["revision"],
            "composition": composition,
        },
        "test": {
            "map50": map50,
            "map50_95": float(metrics.box.map),
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr),
        },
        "recall_by_bins_per_frame": recall_by_bins_per_frame(model, data_yaml, tree, config),
        "precision_on_negatives": precision_on_negatives(model, tree, config),
        "config": config,
    }

    # The split that actually predicts launch behaviour, when there is one.
    if (tree / "images" / "holdout_region").exists() and any(
        (tree / "images" / "holdout_region").iterdir()
    ):
        holdout = model.val(
            data=str(data_yaml), imgsz=config["data"]["imgsz"], split="holdout_region"
        )
        history["holdout_region"] = {
            "map50": float(holdout.box.map50),
            "recall": float(holdout.box.mr),
            "precision": float(holdout.box.mp),
        }
        log(f"held-out region mAP50 = {history['holdout_region']['map50']:.4f}")
    else:
        log("no held-out region in this dataset - the generalisation number is NOT available")

    history_path = WORKING / config["logging"]["history_file"]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    log(f"test mAP@0.5 = {map50:.4f}")

    # --- export ------------------------------------------------------------- #
    artifacts = WORKING / "artifacts"
    fp32 = export_onnx(
        best, artifacts, imgsz=config["export"]["imgsz"], opset=config["export"]["opset"], role=ROLE
    )
    int8 = quantise(
        fp32,
        tree / "images" / "val",
        artifacts / f"{ROLE}-v{MODEL_VERSION}.onnx",
        imgsz=config["export"]["imgsz"],
        calibration_images=config["export"]["calibration_images"],
    )

    # Gate 3 is fp32-vs-int8, so int8 has to be scored on the SAME split the
    # fp32 number came from - which only this machine still has.
    map50_int8 = evaluate_int8(
        int8, role=ROLE, data=data_yaml, imgsz=config["data"]["imgsz"], split="test"
    )
    history["test"]["map50_int8"] = map50_int8
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    gates = Gates.from_config(ROLE, config)
    report = ExportReport(
        role=ROLE,
        version=int(MODEL_VERSION),
        onnx_path=int8.name,
        size_bytes=int8.stat().st_size,
        imgsz=config["export"]["imgsz"],
        classes=classes,
        quantised=True,
        map50_fp32=map50,
        map50_int8=map50_int8,
        # Latency alone is left to ml/scripts/gate.py, on the CPU the budget is
        # actually stated for. This machine has a GPU and somebody else's CPU.
        median_latency_ms=None,
        # docs/04 7's targets. Reported, never gating - and `None` where no
        # measurement exists, which is the honest state of the held-out-city
        # target until a second region_id lands (docs/04 5).
        targets_measured={
            "min_recall_heldout_city": history.get("holdout_region", {}).get("recall"),
            "min_precision_on_negatives": history["precision_on_negatives"].get(
                "frame_level_specificity"
            ),
        },
    )
    sidecar = write_sidecar(report, artifacts, gates)
    check_gates(report, gates).log()

    # --- upload ------------------------------------------------------------- #
    # Uploaded even when a gate fails: the artefact is evidence for the next
    # iteration. Promotion is a separate, gated step and lives in gate.py.
    if os.environ.get("SBR_SKIP_UPLOAD") != "1":
        upload_artifacts(
            repo_id=config["hub"]["model_repo"],
            files={
                f"v{MODEL_VERSION}/best.pt": best,
                f"v{MODEL_VERSION}/{int8.name}": int8,
                f"v{MODEL_VERSION}/{sidecar.name}": sidecar,
                f"v{MODEL_VERSION}/history.json": history_path,
            },
            commit_message=f"{ROLE} v{MODEL_VERSION}: test mAP50={map50:.4f}",
            private=config["hub"]["private"],
        )

    log(
        f"exported {int8.name}. Latency is unmeasured by design - run "
        f"`python ml/scripts/gate.py --role {ROLE} --version {MODEL_VERSION}` to decide shipping."
    )


if __name__ == "__main__":
    main()
