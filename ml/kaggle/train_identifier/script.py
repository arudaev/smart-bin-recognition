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
         "onnx>=1.16.0", "onnxruntime==1.29.0", "huggingface_hub>=1.2.0", "pyyaml"]
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
    from sbr.dataset.expected import (
        check_crop_composition,
        crop_counts,
        expectation_for,
    )
    from sbr.dataset.prepare import build_classification_tree
    from sbr.export.onnx_export import (
        ExportReport,
        Gates,
        QuantSettings,
        calibration_frames,
        check_gates,
        evaluate_int8,
        export_onnx,
        quantise,
        write_sidecar,
    )
    from sbr.export.selection import Candidate, choose_winner
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
    # BEFORE THE GPU HOUR. A pin says which crops; it does not say what labels
    # are on them, and the identifier's whole training signal IS those labels.
    # Frame and box totals can hold exactly while every form factor underneath
    # changes - a re-run of the adjudication tool, a partially applied decision
    # file - and this run would train on the difference in silence. So the
    # per-class counts are asserted, not just the arithmetic.
    expectation = expectation_for(config["data"]["repo_id"])
    if expectation is None:
        log(f"no crop contract for {config['data']['repo_id']} - proceeding unchecked")
    elif revision != expectation.revision:
        raise SystemExit(
            f"this run resolved {revision[:12]} but sbr.dataset.expected describes "
            f"{expectation.revision[:12]}. Pinning new crops is a deliberate act: "
            "update the contract in the same commit as the pin, with the reason "
            "in the message."
        )
    else:
        counts = {
            name: crop_counts(json.loads((path / "manifest.json").read_text(encoding="utf-8")))
            for name, path in (
                (p.name, p) for p in sorted(pool.iterdir()) if (p / "manifest.json").exists()
            )
        }
        check_crop_composition(counts, expectation)
        log(f"crop contract holds for {expectation.revision[:12]}: {counts}")

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
    # `val` FIRST, and that is not decoration. docs/12 P11 fixes the
    # partitioning: every export variant is scored on `val`, exactly one is
    # locked, and `test` is touched once. The earlier version of this kernel
    # scored fp32 on `test` and int8 on `test` while calibrating on `val`, so a
    # sweep would have selected on the split it later reported.
    val_metrics = model.val(data=str(tree), imgsz=config["data"]["imgsz"], split="val")
    top1_val = float(val_metrics.top1)
    log(f"PyTorch fp32 on val = {top1_val:.4f} - the reference every variant is judged against")

    history = {
        "role": ROLE,
        "version": int(MODEL_VERSION),
        "dataset": {
            "repo_id": config["data"]["repo_id"],
            "revision": revision,
            "composition": composition,
        },
        "partitioning": {
            "calibration": "train",
            "selection": "val - no candidate is ever selected on test",
            "confirmation": "test, once, and only for a locked winner",
        },
        "val": {"top1": top1_val, "top5": float(val_metrics.top5)},
        "classes_trained": present,
        "classes_without_data": composition["classes_absent"],
        # NOT gates, and labelled here so nothing downstream reads them as one.
        # top-5 over three classes is arithmetic rather than accuracy, and the
        # 0.55 unknown threshold is an uncalibrated guess until docs/12 P2.
        "not_gates": ["val.top5", "test.top5", "unknown"],
        "config": config,
    }
    history_path = WORKING / config["logging"]["history_file"]
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    # --- export ------------------------------------------------------------- #
    artifacts = WORKING / "artifacts"
    fp32 = export_onnx(
        best, artifacts, imgsz=config["export"]["imgsz"], opset=config["export"]["opset"], role=ROLE
    )
    # Calibrate from TRAIN. Calibrating on `val` and then selecting on `val`
    # lets the calibration set see the split it is judged on - the leak P9 and
    # P10 avoided by construction. A classification tree carries no label files,
    # so the positive/background split a detection calibration reports is not a
    # thing here; every crop is a bin. `stratified` still matters, because it
    # samples across the class directories rather than taking whichever class
    # sorts first.
    calibration = calibration_frames(
        tree,
        "train",
        config["export"]["calibration_images"],
        strategy="stratified",
        seed=config["project"]["seed"],
    )
    log(f"calibration set: {json.dumps(calibration.as_dict())}")

    max_drop = float(config["export"]["gates"]["max_accuracy_drop"])
    rows: list[dict] = []

    def score_variant(name: str, note: str, settings) -> dict:
        """Export one configuration and score it on `val`. Never on `test`."""
        path = artifacts / f"{name}.onnx"
        row = {
            "variant": name, "note": note, "split": "val",
            "settings": settings.as_dict() if settings else None,
        }
        try:
            quantise(
                fp32, calibration, path,
                imgsz=config["export"]["imgsz"], settings=settings,
            )
            row["size_bytes"] = path.stat().st_size
            row["top1"] = evaluate_int8(
                path, role=ROLE, data=tree,
                imgsz=config["data"]["imgsz"], split="val",
            )
            row["drop"] = top1_val - row["top1"]
        except Exception as error:  # noqa: BLE001 - a failed variant is a result
            row["error"] = f"{type(error).__name__}: {error}"
        log(f"{name}: " + json.dumps({k: v for k, v in row.items() if k != "settings"}))
        rows.append(row)
        return row

    reference = score_variant(
        "10-reference",
        "the shipped defaults: U8S8, per-channel, minmax, stretched calibration",
        QuantSettings(),
    )

    # docs/12 P11's sweep, ENUMERATED THERE rather than invented here. It runs
    # only if the reference misses. `exclude_head` is deliberately absent: a
    # yolo11s-cls has no DFL detection head, so P9's diagnosis does not transfer
    # and a variant named for a structure this graph lacks would measure the
    # reference under a different label.
    if reference.get("drop") is None or reference["drop"] > max_drop:
        log(
            f"the reference costs {reference.get('drop')} top-1 against a budget "
            f"of {max_drop} - running the pre-registered sweep, on val"
        )
        for name, note, settings in (
            ("11-s8s8", "onnxruntime's named normal CPU choice",
             QuantSettings(activation_type="s8", weight_type="s8")),
            ("12-reduce-range", "its documented remedy for x86 activation saturation",
             QuantSettings(reduce_range=True)),
            ("13-u8u8", "the other documented remedy",
             QuantSettings(activation_type="u8", weight_type="u8")),
            ("14-per-tensor", "per-channel off",
             QuantSettings(per_channel=False)),
            ("15-preprocessed", "quant_pre_process on",
             QuantSettings(preprocess=True)),
            ("16-letterboxed", "calibration fitted the way inference fits",
             QuantSettings(calibration_fit="letterbox")),
        ):
            score_variant(name, note, settings)

    candidates = [
        Candidate(
            variant=row["variant"],
            map50=row["top1"],
            latency_ms=None,  # measured on the 2-vCPU bench, not here
            departures=len(QuantSettings(**row["settings"]).departures),
        )
        for row in rows if row.get("top1") is not None and row["settings"]
    ]
    chosen = choose_winner(candidates, reference_map50=top1_val, max_drop=max_drop)
    history["variants"] = rows
    served = artifacts / f"{ROLE}-v{MODEL_VERSION}.onnx"

    if chosen is None:
        log(
            f"NO VARIANT IS ELIGIBLE against PyTorch fp32 val {top1_val:.4f} at a "
            f"budget of {max_drop}. test is NOT touched and stays unspent, and the "
            "gate does not move. This is docs/12 P11's middle row."
        )
        scored = [r for r in rows if r.get("top1") is not None]
        best_row = min(scored, key=lambda r: r["drop"]) if scored else rows[0]
        # The artefact still gets written, so the sidecar can record WHY it may
        # not ship. An ineligible export is a documented refusal, not a gap.
        int8 = (artifacts / f"{best_row['variant']}.onnx").replace(served)
        # The pair that WAS measured: fp32 and int8 on `val`. Handing None
        # downstream would make check_gates report the accuracy gate as
        # *unmeasured*, which is a different and weaker statement than what
        # happened - it was measured and it missed. `accuracy_split` records
        # that these are `val` numbers so they can never be quoted as `test`.
        top1, top1_int8 = top1_val, best_row.get("top1")
        accuracy_split = "val"
        history["confirmed_on_test"] = False
        history["best_on_val"] = best_row["variant"]
    else:
        log(f"winner by the pre-registered rule: {chosen.variant}")
        int8 = (artifacts / f"{chosen.variant}.onnx").replace(served)
        # The ONLY test evaluation in this file, on the locked bytes.
        test_metrics = model.val(data=str(tree), imgsz=config["data"]["imgsz"], split="test")
        top1 = float(test_metrics.top1)
        top1_int8 = evaluate_int8(
            int8, role=ROLE, data=tree, imgsz=config["data"]["imgsz"], split="test"
        )
        history["test"] = {
            "top1": top1, "top5": float(test_metrics.top5),
            "top1_int8": top1_int8, "drop": top1 - top1_int8,
        }
        accuracy_split = "test"
        history["confirmed_on_test"] = True
        history["best_on_val"] = chosen.variant
        history["unknown"] = unknown_rate(
            model, tree, config["inference"]["unknown_threshold"], config["data"]["imgsz"]
        )
        log(f"test top-1 fp32 {top1:.4f} - int8 {top1_int8:.4f} - drop {top1 - top1_int8:.4f}")

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
        # Which split the pair above came from. `test` only when a winner was
        # locked and confirmed; `val` when nothing was eligible and `test` was
        # deliberately left unspent.
        accuracy_split=accuracy_split,
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
