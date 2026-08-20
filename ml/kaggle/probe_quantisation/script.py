#!/usr/bin/env python3
"""docs/12 P9 – why int8 destroys the validator. (Kaggle, CPU, no GPU)

The first completed validator scores **mAP@0.5 = 0.7524 in fp32 and 0.025 in
int8**, so ``may_ship`` is false and nothing can be deployed. This kernel finds
out which part of the quantisation does that, and whether any configuration
keeps the model inside the 0.02 budget. No training: ``v1/best.pt`` already
exists, and every row here is an export of it.

**The partitioning is the part that makes the answer usable.** Calibration draws
from ``train`` and **no candidate is ever selected on ``test``** - every variant
is scored on ``val`` and the winner is chosen there. Selecting on ``test`` and
then reporting that same number as ship-gate evidence would make the gate a
number that was tuned against, which is not a gate.

``test`` is scored three times and each one is named: the historical baseline
(which must use ``test``, because 0.025 was measured there and reproducing it is
the point), and then the locked winner and the fp32 control. An earlier version
of this docstring said "touched exactly once", which was simply false.

**Three drops, not one.** The 0.7524 came from PyTorch on a GPU and the 0.025
from onnxruntime on a CPU, so precision is not the only thing that changed
between them. The fp32 ONNX control separates them - but it must never become
the denominator, or a lossy fp32 export would lower the reference and let a bad
int8 graph appear to pass:

    export drop        = PyTorch fp32  -  ONNX fp32
    quantisation drop  = ONNX fp32     -  ONNX int8
    total served drop  = PyTorch fp32  -  ONNX int8    <- the only one that gates

**Nothing is uploaded.** This is a diagnostic. Promotion is a separate, gated
step and lives in gate.py.
"""

# ---------------------------------------------------------------------------
# 0. Bundle – injected by dispatch.py
# ---------------------------------------------------------------------------
PROJECT_BUNDLE_B64 = "__SBR_PROJECT_BUNDLE_B64__"
CONFIG_NAME = "__SBR_CONFIG_NAME__"
MODEL_VERSION = "__SBR_MODEL_VERSION__"

import base64  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import zipfile  # noqa: E402

WORKING = pathlib.Path("/kaggle/working")
PROJECT = WORKING / "project"
ROLE = "validator"
NAME = "p9-quantisation"

#: The pool and the tree go OUTSIDE /kaggle/working on purpose. Everything under
#: working is kernel output, and the pinned pool is 37 913 files - which is why
#: `kaggle kernels output` on a training run tries to download all of them. Here
#: the output is one JSON and a handful of ONNX files.
SCRATCH = pathlib.Path("/tmp/sbr")

#: The frozen reference. Measured on the test split by the 2026-08-18 training
#: run, PyTorch fp32 on a T4, and recorded in v1/history.json. Every drop this
#: kernel reports is against THIS number, never against one it recomputed.
PYTORCH_FP32_TEST_MAP50 = 0.7524389678079388

#: The tie-break itself lives in `sbr.export.selection` rather than here,
#: because a rule written inside a kernel is a rule nothing can import and
#: therefore a rule nothing tests - and this one decides whether an artefact
#: reaches the ship gate at all.


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
    """Pin ultralytics to the version that produced v1, so the baseline can be
    reproduced rather than approximated.

    ``best.pt`` records ``8.4.121``. Everything in this repo is lower-bounded
    rather than pinned, so a newer ultralytics is a live confound on the one
    measurement this whole probe is anchored to. ``--no-deps`` keeps pip away
    from torch for the usual reason (see ``sbr.utils.gpu``); this kernel has no
    GPU and does not care which torch it gets, but a resolver that swapped it
    would still change the export.
    """
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "--no-deps",
         "ultralytics==8.4.121", "ultralytics-thop"]
    )
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q",
         "onnx>=1.16.0", "onnxruntime>=1.18.0", "onnxconverter-common>=1.14.0",
         "huggingface_hub>=1.2.0", "pyyaml"]
    )
    log("dependencies installed (ultralytics pinned to v1's 8.4.121)")


def toolchain() -> dict:
    """Every version that can move a number here, recorded with the numbers."""
    versions = {}
    for module in ("ultralytics", "onnx", "onnxruntime", "torch", "numpy"):
        try:
            versions[module] = __import__(module).__version__
        except Exception as error:  # noqa: BLE001 - an absent module is a fact
            versions[module] = f"unavailable ({type(error).__name__})"
    return versions


def sha256_of(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    unpack_bundle()
    install_dependencies()

    from huggingface_hub import hf_hub_download

    from sbr.bench import bench, hardware
    from sbr.config import load_config
    from sbr.export.onnx_export import (
        DEFAULT_HEAD_PREFIX,
        QuantSettings,
        calibration_frames,
        convert_fp16,
        export_onnx,
        quant_boundary,
        quantisation_error,
        quantise,
        score_onnx,
    )
    from sbr.export.selection import Candidate, choose_winner
    from sbr.utils.hub import configure_hf_runtime, download_dataset, load_hf_token

    configure_hf_runtime()
    config = load_config(CONFIG_NAME, PROJECT / "ml" / "configs")
    imgsz, export_imgsz = config["data"]["imgsz"], config["export"]["imgsz"]
    calibration_images = config["export"]["calibration_images"]
    seed = config["project"]["seed"]
    repo = config["hub"]["model_repo"]
    token = load_hf_token()

    machine = hardware()
    log(f"measuring on: {machine.label}")
    versions = toolchain()
    log(f"toolchain: {json.dumps(versions)}")

    artifacts = WORKING / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    # --- the weights, and the artefact that failed -------------------------- #
    weights = pathlib.Path(hf_hub_download(repo, f"v{MODEL_VERSION}/best.pt", token=token))
    shipped = pathlib.Path(
        hf_hub_download(repo, f"v{MODEL_VERSION}/{ROLE}-v{MODEL_VERSION}.onnx", token=token)
    )
    shipped_sha = sha256_of(shipped)
    log(f"v{MODEL_VERSION} int8 as shipped: {shipped.name}, sha256 {shipped_sha[:16]}")

    # --- the data ----------------------------------------------------------- #
    from sbr.dataset.expected import check_composition, expectation_for
    from sbr.dataset.prepare import build_yolo_tree

    pool = download_dataset(
        config["data"]["repo_id"],
        revision=config["data"]["revision"],
        local_dir=SCRATCH / "pool",
        strict=True,
    )
    tree = SCRATCH / "dataset"
    data_yaml = build_yolo_tree(pool, tree, config)
    composition = json.loads((tree / "composition.json").read_text(encoding="utf-8"))
    expectation = expectation_for(config["data"]["repo_id"])
    if expectation is not None:
        check_composition(composition, expectation)
        log(f"composition matches the contract for {expectation.revision[:12]}")

    rows: list[dict] = []
    #: sha256 -> the complete ordered calibration manifest.
    calibration_sets: dict[str, dict] = {}

    def run(
        variant: str,
        note: str,
        *,
        settings=None,
        calibration=None,
        split: str,
        build,
    ) -> dict:
        """Build one graph, score it, time it, and record what produced it.

        Either ``metric`` or ``error`` - never both, and never a number that was
        not measured. A graph that will not load is a valid diagnostic result and
        the fp16 row is the one most likely to be one.
        """
        out = artifacts / f"{variant}.onnx"
        row: dict = {
            "variant": variant,
            "note": note,
            "split": split,
            "settings": settings.as_dict() if settings is not None else None,
            # The hash, not the list: the complete ordered manifest for every set
            # is written once under `calibration_sets` and referenced from here.
            "calibration_sha256": calibration.sha256 if calibration is not None else None,
            "calibration": calibration.as_dict() if calibration is not None else None,
        }
        if calibration is not None:
            calibration_sets.setdefault(calibration.sha256, calibration.manifest())
        started = time.perf_counter()
        try:
            build(out)
        except Exception as error:  # noqa: BLE001 - a build failure is a result
            row["error"] = f"build: {type(error).__name__}: {error}"
            log(f"{variant}: BUILD FAILED - {row['error']}")
            rows.append(row)
            return row

        row["sha256"] = sha256_of(out)
        row["size_bytes"] = out.stat().st_size
        row["boundary"] = quant_boundary(out, DEFAULT_HEAD_PREFIX)
        row["build_seconds"] = round(time.perf_counter() - started, 1)

        value, error = score_onnx(out, role=ROLE, data=data_yaml, imgsz=imgsz, split=split)
        if error is None:
            row["metric"] = value
        else:
            row["error"] = f"score: {error}"

        try:
            row["latency"] = bench(out, {"imgsz": export_imgsz, "input_name": "images"})
        except Exception as error:  # noqa: BLE001 - a graph the CPU EP will not run
            row["latency_error"] = f"{type(error).__name__}: {error}"

        log(
            f"{variant:28} {split:5} "
            + (f"map50 {row['metric']:.4f}" if "metric" in row else f"ERROR {row.get('error')}")
            + (f"  p50 {row['latency']['median_latency_ms']:.1f} ms" if "latency" in row else "")
        )
        rows.append(row)
        return row

    # --- the fp32 ONNX, exported once and shared by every row --------------- #
    fp32 = export_onnx(
        weights, artifacts, imgsz=export_imgsz, opset=config["export"]["opset"], role=ROLE
    )

    # ---------------------------------------------------------------------- #
    # Gate 0 - reproduce the failure before trying to remedy it
    # ---------------------------------------------------------------------- #
    # The historical calibration list: `val`'s first 200 by filename. This is the
    # ONE place `val` is used for calibration and the one place the historical
    # sample is wanted, because reproducing what happened is the point of it.
    historical = calibration_frames(
        tree, "val", calibration_images, strategy="first_lexicographic", seed=seed
    )
    log(f"historical calibration set: {json.dumps(historical.as_dict())}")

    baseline = run(
        "00-historical-baseline",
        "v1 settings and v1's own calibration list, scored on test to reproduce 0.025",
        settings=QuantSettings(),
        calibration=historical,
        split="test",
        build=lambda out: quantise(fp32, historical, out, imgsz=export_imgsz),
    )
    baseline["reproduces_shipped_sha"] = baseline.get("sha256") == shipped_sha
    baseline["shipped_sha256"] = shipped_sha
    if not baseline["reproduces_shipped_sha"]:
        log(
            "TOOLCHAIN CONFOUND: the re-quantised graph is not byte-identical to "
            "the one on the Hub. Dependencies here are lower-bounded rather than "
            "pinned and the Hub holds no fp32 ONNX, so this is recorded rather "
            "than treated as a failure - what must reproduce is the METRIC."
        )

    reproduced = baseline.get("metric")
    if reproduced is None or abs(reproduced - 0.025) > 0.05:
        raise SystemExit(
            f"the historical baseline did not reproduce: got {reproduced}, expected "
            "about 0.025. Every remedy below would be measured against a baseline "
            "that is not the one being explained, so this stops here. Resolve the "
            f"toolchain confound first - versions were {json.dumps(versions)}"
        )
    log(f"baseline reproduces at {reproduced:.4f}; proceeding to the variants")

    # Which TENSOR loses the signal, from onnxruntime's own QDQ debugger. Nine
    # variants can show that something helps without ever saying what was wrong;
    # this runs the float and quantised graphs over the same frames and ranks
    # activations by quantisation error, so the write-up can name the layer.
    baseline["tensor_error"] = quantisation_error(
        fp32, artifacts / "00-historical-baseline.onnx", historical, export_imgsz
    )
    log(f"worst tensors: {json.dumps(baseline['tensor_error'], indent=2)}")

    # ---------------------------------------------------------------------- #
    # The controls, on val - what the graph is worth before quantisation
    # ---------------------------------------------------------------------- #
    run(
        "01-fp32-onnx-control",
        "CONTROL: the fp32 ONNX graph, unquantised. Separates export loss from "
        "quantisation loss - it is NOT the gate's denominator",
        split="val",
        build=lambda out: out.write_bytes(fp32.read_bytes()),
    )
    run(
        "02-fp16-informational",
        "INFORMATIONAL ONLY: the CPU execution provider does not broadly support "
        "fp16 ops, so this cannot be a shipping option however it scores",
        split="val",
        build=lambda out: convert_fp16(fp32, out),
    )

    # ---------------------------------------------------------------------- #
    # The reference, and then one variable at a time - all on val
    # ---------------------------------------------------------------------- #
    reference = calibration_frames(
        tree, "train", calibration_images, strategy="stratified", seed=seed
    )
    log(f"reference calibration set R: {json.dumps(reference.as_dict())}")
    enriched = calibration_frames(
        tree, "train", calibration_images, strategy="positive_enriched", seed=seed
    )

    variants = [
        ("10-reference-u8s8", "R: v1 settings, calibrated stratified from train",
         QuantSettings(), reference),
        # Axis one: the numeric format. onnxruntime names S8S8 the normal CPU
        # choice and a large U8S8 loss an x86 saturation symptom.
        ("11-s8s8", "S8S8 - onnxruntime's normal CPU choice",
         QuantSettings(activation_type="s8"), reference),
        ("12-u8s8-reduce-range", "U8S8 with reduce_range - the documented saturation remedy",
         QuantSettings(reduce_range=True), reference),
        ("13-u8u8", "U8U8 - the other documented saturation remedy",
         QuantSettings(weight_type="u8"), reference),
        ("14-per-tensor", "per-tensor weights instead of per-channel",
         QuantSettings(per_channel=False), reference),
        ("15-head-fp32", "the detection head left in fp32 - wide-range box regression",
         QuantSettings(exclude_head=True), reference),
        ("16-preprocessed", "onnxruntime's quant_pre_process before quantising",
         QuantSettings(preprocess=True), reference),
        # Axis two: the calibration set.
        ("20-positive-enriched", "half the calibration frames hold a bin",
         QuantSettings(), enriched),
        ("21-letterboxed", "calibration letterboxed, as model.val() and the service do",
         QuantSettings(calibration_fit="letterbox"), reference),
    ]
    for variant, note, settings, calibration in variants:
        run(
            variant, note,
            settings=settings, calibration=calibration, split="val",
            build=lambda out, s=settings, c=calibration: quantise(
                fp32, c, out, imgsz=export_imgsz, settings=s
            ),
        )

    # ---------------------------------------------------------------------- #
    # The winner, by the rule docs/12 P9 fixed in advance
    # ---------------------------------------------------------------------- #
    # The eligibility reference is the PYTORCH fp32 score on val, measured here
    # from best.pt. Using the fp32 ONNX score instead - which an earlier version
    # did, while calling it "PyTorch-equivalent" - lets a lossy export lower the
    # bar its own candidates are judged against. That is the same failure the
    # three-drop accounting exists to prevent, one split further up.
    from ultralytics import YOLO

    pytorch_val = float(
        YOLO(str(weights)).val(
            data=str(data_yaml), imgsz=imgsz, split="val", verbose=False
        ).box.map50
    )
    fp32_val, fp32_val_error = score_onnx(
        fp32, role=ROLE, data=data_yaml, imgsz=imgsz, split="val"
    )
    log(
        f"val references: PyTorch fp32 {pytorch_val:.4f} (the one eligibility reads) · "
        f"fp32 ONNX {fp32_val} ({fp32_val_error or 'ok'}), which separates export loss "
        "from quantisation loss and is NOT the reference"
    )

    def candidates_from(rows_in: list[dict]) -> list:
        """Reduce the measured rows to what the selection rule reads."""
        out = []
        for row in rows_in:
            if row["split"] != "val" or row.get("metric") is None or row["settings"] is None:
                continue
            out.append(
                Candidate(
                    variant=row["variant"],
                    map50=row["metric"],
                    latency_ms=row.get("latency", {}).get("median_latency_ms"),
                    departures=len(QuantSettings(**row["settings"]).departures),
                    # fp16 is reported and cannot be chosen: the CPU execution
                    # provider does not broadly support fp16 ops, so it measures
                    # a configuration this service cannot serve.
                    shippable=row["variant"] != "02-fp16-informational",
                )
            )
        return out

    # --- the combined run, when the two axes disagree ---------------------- #
    # docs/12 P9 promises this and an earlier version of the kernel omitted it,
    # which could have concluded "post-training quantisation cannot recover the
    # model" when two remedies are jointly necessary and neither suffices alone.
    format_rows = [r for r in rows if r["variant"].startswith("1") and r.get("metric") is not None]
    calibration_rows = [r for r in rows if r["variant"].startswith("2")
                        and r.get("metric") is not None and r["settings"] is not None]

    best_format = max(format_rows, key=lambda r: r["metric"], default=None)
    best_calibration = max(calibration_rows, key=lambda r: r["metric"], default=None)

    if (
        best_format is not None
        and best_calibration is not None
        and best_format["variant"] != "10-reference-u8s8"
    ):
        # The format winner's settings, applied to the calibration winner's set
        # (and its fit, which is a calibration property that lives in settings).
        format_settings = QuantSettings(**best_format["settings"])
        calibration_settings = QuantSettings(**best_calibration["settings"])
        combined_settings = QuantSettings(
            **(
                format_settings.as_dict()
                | {"calibration_fit": calibration_settings.calibration_fit}
            )
        )
        combined_calibration = (
            enriched if best_calibration["variant"] == "20-positive-enriched" else reference
        )
        log(
            f"the two axes disagree - {best_format['variant']} on format, "
            f"{best_calibration['variant']} on calibration - so they are combined"
        )
        run(
            "30-combined",
            f"the format from {best_format['variant']} with the calibration from "
            f"{best_calibration['variant']} - docs/12 P9's combined confirmation",
            settings=combined_settings,
            calibration=combined_calibration,
            split="val",
            build=lambda out, s=combined_settings, c=combined_calibration: quantise(
                fp32, c, out, imgsz=export_imgsz, settings=s
            ),
        )
    else:
        log("the reference already leads its axis - no combined run is called for")

    # --- the winner, by the rule in sbr.export.selection -------------------- #
    max_drop = config["export"]["gates"]["max_accuracy_drop"]
    candidates = candidates_from(rows)
    if pytorch_val is None:
        raise SystemExit(
            "the PyTorch fp32 val score could not be measured, so eligibility has "
            "no reference and no winner can be chosen. Nothing is confirmed on test."
        )
    chosen = choose_winner(candidates, reference_map50=pytorch_val, max_drop=max_drop)

    winner = next((row for row in rows if chosen and row["variant"] == chosen.variant), None)
    if winner is None:
        log(
            f"NO VARIANT IS ELIGIBLE against PyTorch fp32 val {pytorch_val:.4f} at a "
            f"budget of {max_drop}. There is nothing to confirm, so the test split "
            "stays untouched - which is the point of holding it back."
        )
    else:
        log(f"winner by the pre-registered rule: {winner['variant']}")
        # The same bytes, not a re-quantisation: re-running the export would
        # introduce a second graph and the confirmation would no longer be of
        # the thing that was selected.
        confirmation = run(
            f"90-confirm-{winner['variant']}",
            "THE LOCKED WINNER, the same bytes, scored once on test. This is the "
            "only ship-gate number in this file",
            settings=QuantSettings(**winner["settings"]),
            split="test",
            build=lambda out, w=winner: out.write_bytes((artifacts / f"{w['variant']}.onnx").read_bytes()),
        )
        confirmation["calibration"] = winner["calibration"]
        confirmation["calibration_sha256"] = winner["calibration_sha256"]
        confirmation["tensor_error"] = quantisation_error(
            fp32, artifacts / f"{winner['variant']}.onnx", reference, export_imgsz
        )
        control = run(
            "91-confirm-fp32-control",
            "the fp32 ONNX control on test, so the three drops can be separated",
            split="test",
            build=lambda out: out.write_bytes(fp32.read_bytes()),
        )
        if confirmation.get("metric") is not None and control.get("metric") is not None:
            log(
                f"export drop {PYTORCH_FP32_TEST_MAP50 - control['metric']:.4f} · "
                f"quantisation drop {control['metric'] - confirmation['metric']:.4f} · "
                f"TOTAL SERVED DROP {PYTORCH_FP32_TEST_MAP50 - confirmation['metric']:.4f} "
                f"against a budget of {max_drop}"
            )

    # ---------------------------------------------------------------------- #
    # The record
    # ---------------------------------------------------------------------- #
    report = {
        "probe": "P9",
        "role": ROLE,
        "source_version": int(MODEL_VERSION),
        "hardware": machine.as_dict(),
        "toolchain": versions,
        "dataset": {
            "repo_id": config["data"]["repo_id"],
            "revision": config["data"]["revision"],
            "composition": composition,
        },
        "reference": {
            "pytorch_fp32_test_map50": PYTORCH_FP32_TEST_MAP50,
            # Measured here, and the one eligibility actually reads.
            "pytorch_fp32_val_map50": pytorch_val,
            "fp32_onnx_val_map50": fp32_val,
            "fp32_onnx_val_error": fp32_val_error,
            "shipped_int8_sha256": shipped_sha,
            "max_accuracy_drop": config["export"]["gates"]["max_accuracy_drop"],
        },
        "partitioning": {
            "calibration": "train (except 00-historical-baseline, which reproduces v1's val list)",
            "selection": "val - no candidate is ever selected on test",
            "test_evaluations": [
                "00-historical-baseline (reproduces the published 0.025, which was measured on test)",
                "90-confirm-<winner> (the locked winner)",
                "91-confirm-fp32-control (so the three drops can be separated)",
            ],
        },
        "winner": winner["variant"] if winner else None,
        "calibration_sets": calibration_sets,
        "rows": rows,
    }
    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"wrote {out}")
    log(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
