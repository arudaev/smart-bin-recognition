#!/usr/bin/env python3
"""docs/12 P10 – where the residual 0.0252 lives. (Kaggle, CPU, no GPU)

[P9](docs/research/probes/P9-int8-quantisation.md) established that quantising
the detection head is what collapses the validator: excluding ``/model.23/``
takes it from 0.015 to 0.7481 on ``val``. It did **not** establish that nothing
outside the head matters. That graph still carries **619 QDQ nodes** and still
loses **0.0252** against a 0.02 budget, and the residual is unattributed.

This kernel finds out where it lives. No training, no GPU: every row is an
export of the ``v1/best.pt`` that already exists.

**The diagnostic's direction is a trap, and it is written here because it has
already caught someone.** onnxruntime's ``qdq_err`` is **SQNR in decibels** -
``20*log10(||x|| / ||x-y||)`` - so **higher is better** and the damaged tensors
are at the *bottom*. P9's first pass sorted descending, called the result "the
worst tensors", and named the eight best-preserved tensors in the graph as the
suspects. ``quantisation_error`` now returns them ascending under
``lowest_sqnr_db``; do not re-sort them.

**Partitioning, as P9:** calibrate from ``train``, score every variant on
``val``, and touch ``test`` only to confirm a locked winner. No candidate is
ever selected on ``test``.

**Nothing is uploaded.** This is a diagnostic.
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
NAME = "p10-residual"

#: Outside /kaggle/working, which is all kernel output. The pinned pool is
#: 37 913 files and `kaggle kernels output` would fetch every one.
SCRATCH = pathlib.Path("/tmp/sbr")

#: Frozen. PyTorch fp32 on the test split, from the 2026-08-18 training run.
#: Every drop reported here is against this, never a recomputed reference.
PYTORCH_FP32_TEST_MAP50 = 0.7524389678079388

#: What P9 measured for the head-fp32 graph on `val`, as the sanity anchor.
#: If this run does not reproduce it, the two graphs are not the same graph and
#: nothing below means anything.
P9_HEAD_FP32_VAL_MAP50 = 0.7481

#: The standing hypothesis, tested REGARDLESS of what the ranking says. A local
#: smoke test on a stock YOLO11n reported a 1517x weight-scale increase on
#: `model.10.m.0.attn.qkv.conv.weight` - the C2PSA attention block. That is a
#: hint, not evidence, and leaving it untested would make this unfalsifiable.
STANDING_SUSPECT = "/model.10/"

HEAD = "/model.23/"


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
    """ultralytics pinned to the version recorded inside ``best.pt``.

    Everything in this repo is lower-bounded rather than pinned, so a newer
    ultralytics is a live confound on the anchor this probe is measured against.
    """
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "--no-deps",
         "ultralytics==8.4.121", "ultralytics-thop"]
    )
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q",
         "onnx>=1.16.0", "onnxruntime>=1.18.0", "huggingface_hub>=1.2.0", "pyyaml"]
    )
    log("dependencies installed (ultralytics pinned to v1's 8.4.121)")


def toolchain() -> dict:
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


def module_of(tensor: str) -> str | None:
    """``/model.10/m.0/attn/...`` -> ``/model.10/``. None for graph-level nodes."""
    parts = tensor.split("/")
    if len(parts) > 1 and parts[1].startswith("model."):
        return f"/{parts[1]}/"
    return None


def main() -> None:
    unpack_bundle()
    install_dependencies()

    from huggingface_hub import hf_hub_download

    from sbr.bench import bench, hardware
    from sbr.config import load_config
    from sbr.export.onnx_export import (
        QuantSettings,
        calibration_frames,
        export_onnx,
        quant_boundary,
        quantisation_error,
        quantise,
        score_onnx,
    )
    from sbr.export.selection import Candidate, choose_winner
    from sbr.utils.hub import (
        configure_hf_runtime,
        download_dataset,
        load_hf_token,
        resolve_revision,
    )

    configure_hf_runtime()
    config = load_config(CONFIG_NAME, PROJECT / "ml" / "configs")
    imgsz, export_imgsz = config["data"]["imgsz"], config["export"]["imgsz"]
    calibration_images = config["export"]["calibration_images"]
    seed = config["project"]["seed"]
    max_drop = config["export"]["gates"]["max_accuracy_drop"]
    repo = config["hub"]["model_repo"]

    machine = hardware()
    versions = toolchain()
    log(f"measuring on: {machine.label}")
    log(f"toolchain: {json.dumps(versions)}")

    artifacts = WORKING / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    weights = pathlib.Path(
        hf_hub_download(repo, f"v{MODEL_VERSION}/best.pt", token=load_hf_token())
    )

    # --- data ---------------------------------------------------------------- #
    from sbr.dataset.expected import check_composition, expectation_for
    from sbr.dataset.prepare import build_yolo_tree

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
    calibration_sets: dict[str, dict] = {}

    def run(variant: str, note: str, settings, calibration, split: str, build) -> dict:
        out = artifacts / f"{variant}.onnx"
        row: dict = {
            "variant": variant,
            "note": note,
            "split": split,
            "settings": settings.as_dict() if settings is not None else None,
            "calibration_sha256": calibration.sha256 if calibration is not None else None,
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
        row["boundary"] = quant_boundary(out, HEAD)
        row["build_seconds"] = round(time.perf_counter() - started, 1)

        value, error = score_onnx(out, role=ROLE, data=data_yaml, imgsz=imgsz, split=split)
        if error is None:
            row["metric"] = value
        else:
            row["error"] = f"score: {error}"
        try:
            row["latency"] = bench(out, {"imgsz": export_imgsz, "input_name": "images"})
        except Exception as error:  # noqa: BLE001
            row["latency_error"] = f"{type(error).__name__}: {error}"

        log(
            f"{variant:34} {split:5} "
            + (f"map50 {row['metric']:.4f}" if "metric" in row else f"ERROR {row.get('error')}")
            + (f"  p50 {row['latency']['median_latency_ms']:.1f} ms" if "latency" in row else "")
        )
        rows.append(row)
        return row

    fp32 = export_onnx(
        weights, artifacts, imgsz=export_imgsz, opset=config["export"]["opset"], role=ROLE
    )
    reference = calibration_frames(
        tree, "train", calibration_images, strategy="stratified", seed=seed
    )
    log(f"calibration set: {json.dumps(reference.as_dict())}")

    # ---------------------------------------------------------------------- #
    # The anchor: reproduce P9's head-fp32 before attributing its residual
    # ---------------------------------------------------------------------- #
    head_only = QuantSettings(exclude_head=True)
    anchor = run(
        "00-head-fp32-anchor",
        "P9's best configuration, re-measured. Everything below is an attempt to "
        "attribute ITS residual, so it has to reproduce first",
        head_only, reference, "val",
        lambda out: quantise(fp32, reference, out, imgsz=export_imgsz, settings=head_only),
    )
    measured = anchor.get("metric")
    if measured is None or abs(measured - P9_HEAD_FP32_VAL_MAP50) > 0.02:
        raise SystemExit(
            f"the head-fp32 anchor did not reproduce: got {measured}, P9 measured "
            f"{P9_HEAD_FP32_VAL_MAP50}. Every attribution below would be against a "
            f"different graph, so this stops here. Versions: {json.dumps(versions)}"
        )
    log(f"anchor reproduces at {measured:.4f}; attributing its residual")

    # ---------------------------------------------------------------------- #
    # Which tensors the quantisation actually damages, in the ANCHOR graph
    # ---------------------------------------------------------------------- #
    # LOWEST SQNR first. This is the diagnostic P9 never got to run, and whose
    # direction P9 got backwards.
    diagnosis = quantisation_error(
        fp32, artifacts / "00-head-fp32-anchor.onnx", reference, export_imgsz, lowest=25
    )
    anchor["tensor_error"] = diagnosis
    log(f"tensor diagnosis: {json.dumps(diagnosis, indent=2)}")

    ranked_modules: list[str] = []
    for entry in diagnosis.get("lowest_sqnr_db", []):
        module = module_of(entry["tensor"])
        if module and module != HEAD and module not in ranked_modules:
            ranked_modules.append(module)

    # The ranking is a pointer. The standing suspect is tested whether or not it
    # appears, because an untested hypothesis makes the result unfalsifiable.
    candidates_to_sweep = list(dict.fromkeys([*ranked_modules[:3], STANDING_SUSPECT]))
    log(
        f"modules the ranking points at: {ranked_modules[:3] or 'none'} · "
        f"sweeping {candidates_to_sweep} (the standing suspect is included regardless)"
    )

    # ---------------------------------------------------------------------- #
    # One module at a time, on val
    # ---------------------------------------------------------------------- #
    helped: list[tuple[str, float]] = []
    for index, module in enumerate(candidates_to_sweep, start=10):
        label = module.strip("/").replace(".", "")
        settings = QuantSettings(exclude_head=True, exclude_prefixes=(module,))
        row = run(
            f"{index}-head-plus-{label}",
            f"head in fp32 AND {module} in fp32"
            + (" - the standing suspect" if module == STANDING_SUSPECT else ""),
            settings, reference, "val",
            lambda out, s=settings: quantise(
                fp32, reference, out, imgsz=export_imgsz, settings=s
            ),
        )
        if row.get("metric") is not None and row["metric"] > measured:
            helped.append((module, row["metric"]))

    # Two that independently help are worth combining once.
    if len(helped) >= 2:
        best_two = tuple(m for m, _ in sorted(helped, key=lambda kv: -kv[1])[:2])
        combined = QuantSettings(exclude_head=True, exclude_prefixes=best_two)
        run(
            "20-head-plus-combined",
            f"head in fp32 AND {' AND '.join(best_two)} - both helped alone",
            combined, reference, "val",
            lambda out: quantise(fp32, reference, out, imgsz=export_imgsz, settings=combined),
        )
    else:
        log("fewer than two modules helped alone - no combined run is called for")

    # ---------------------------------------------------------------------- #
    # The winner, by the rule in sbr.export.selection
    # ---------------------------------------------------------------------- #
    from ultralytics import YOLO

    pytorch_val = float(
        YOLO(str(weights)).val(
            data=str(data_yaml), imgsz=imgsz, split="val", verbose=False
        ).box.map50
    )
    log(f"PyTorch fp32 on val = {pytorch_val:.4f} (the reference eligibility reads)")

    candidates = [
        Candidate(
            variant=row["variant"],
            map50=row["metric"],
            latency_ms=row.get("latency", {}).get("median_latency_ms"),
            departures=len(QuantSettings(**row["settings"]).departures),
        )
        for row in rows
        if row["split"] == "val" and row.get("metric") is not None and row["settings"]
    ]
    chosen = choose_winner(candidates, reference_map50=pytorch_val, max_drop=max_drop)
    winner = next((r for r in rows if chosen and r["variant"] == chosen.variant), None)

    if winner is None:
        log(
            f"NO VARIANT IS ELIGIBLE against PyTorch fp32 val {pytorch_val:.4f} at a "
            f"budget of {max_drop}. Nothing is confirmed and the test split stays "
            "unspent - which is the point of holding it back."
        )
    else:
        log(f"winner by the pre-registered rule: {winner['variant']}")
        confirmation = run(
            f"90-confirm-{winner['variant']}",
            "THE LOCKED WINNER, the same bytes, scored once on test. The only "
            "ship-gate number in this file",
            QuantSettings(**winner["settings"]), None, "test",
            lambda out, w=winner: out.write_bytes(
                (artifacts / f"{w['variant']}.onnx").read_bytes()
            ),
        )
        confirmation["calibration_sha256"] = winner["calibration_sha256"]
        control = run(
            "91-confirm-fp32-control", "the fp32 ONNX control on test",
            None, None, "test", lambda out: out.write_bytes(fp32.read_bytes()),
        )
        if confirmation.get("metric") is not None and control.get("metric") is not None:
            log(
                f"export drop {PYTORCH_FP32_TEST_MAP50 - control['metric']:.4f} · "
                f"quantisation drop {control['metric'] - confirmation['metric']:.4f} · "
                f"TOTAL SERVED DROP {PYTORCH_FP32_TEST_MAP50 - confirmation['metric']:.4f} "
                f"against a budget of {max_drop}"
            )

    report = {
        "probe": "P10",
        "role": ROLE,
        "source_version": int(MODEL_VERSION),
        "hardware": machine.as_dict(),
        "toolchain": versions,
        "dataset": {
            "repo_id": config["data"]["repo_id"],
            "revision": revision,
            "composition": composition,
        },
        "reference": {
            "pytorch_fp32_test_map50": PYTORCH_FP32_TEST_MAP50,
            "pytorch_fp32_val_map50": pytorch_val,
            "p9_head_fp32_val_map50": P9_HEAD_FP32_VAL_MAP50,
            "anchor_reproduced_at": measured,
            "max_accuracy_drop": max_drop,
        },
        "partitioning": {
            "calibration": "train",
            "selection": "val - no candidate is ever selected on test",
            "test_evaluations": [r["variant"] for r in rows if r["split"] == "test"],
            "test_evaluations_are": "what ran, not what was planned",
        },
        "modules_swept": candidates_to_sweep,
        "modules_the_ranking_pointed_at": ranked_modules[:3],
        "standing_suspect": STANDING_SUSPECT,
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
