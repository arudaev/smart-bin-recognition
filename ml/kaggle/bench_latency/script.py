#!/usr/bin/env python3
"""Measure ship-gate latency on a free CPU kernel. (Kaggle, no GPU)

The budgets are stated on service CPU. The plan was a free Hugging Face Space at
cpu-basic, 2 vCPU; that is no longer possible – creating a Docker Space returns
``402 Payment Required`` because Gradio and Docker Spaces on free cpu-basic now
require a PRO subscription.

So this measures on a Kaggle CPU kernel with onnxruntime pinned to two threads:
x86, free, and reproducible through the same dispatch path as everything else.
It is a **proxy** for the service container, it is labelled as one in every
number it emits, and ``ml/scripts/gate.py`` will not accept it as the deciding
measurement without being told to.

It pulls the int8 artefact and its sidecar from the model repo, times the graph,
and pushes ``bench-v<version>.json`` back beside them, so the measurement lives
with the artefact it describes.
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

#: Both roles are measured in one run: they share a machine, so measuring them
#: together is the only way the two numbers are comparable to each other.
ROLES = ("validator", "identifier")


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
            "onnxruntime==1.29.0", "huggingface_hub>=1.2.0", "pyyaml", "numpy",
        ]
    )
    log("dependencies installed")


def main() -> None:
    unpack_bundle()
    install_dependencies()

    from huggingface_hub import hf_hub_download

    from sbr.bench import bench, hardware
    from sbr.config import load_config
    from sbr.export.onnx_export import ExportReport, Gates, check_gates
    from sbr.utils.hub import configure_hf_runtime, load_hf_token, require_hf_token, upload_artifacts

    configure_hf_runtime()
    if os.environ.get("SBR_SKIP_UPLOAD") != "1":
        require_hf_token("push the latency measurement")

    machine = hardware()
    log(f"measuring on: {machine.label}")
    if not machine.representative:
        log(
            "NOTE: this is a proxy for the service container, not the service. "
            "gate.py will require --allow-unrepresentative-hardware to decide on it."
        )

    results: dict[str, dict] = {}
    for role in ROLES:
        config = load_config(role, PROJECT / "ml" / "configs")
        repo = config["hub"]["model_repo"]
        token = load_hf_token()
        try:
            sidecar_path = hf_hub_download(
                repo, f"v{MODEL_VERSION}/{role}-v{MODEL_VERSION}.json", token=token
            )
        except Exception as error:  # noqa: BLE001 - an unbuilt model is a reportable state
            log(f"{role}: no artefact yet ({type(error).__name__}) - skipping")
            continue

        sidecar = json.loads(pathlib.Path(sidecar_path).read_text(encoding="utf-8"))
        onnx_path = hf_hub_download(
            repo, f"v{MODEL_VERSION}/{pathlib.Path(sidecar['onnx_path']).name}", token=token
        )

        measurement = bench(pathlib.Path(onnx_path), sidecar)
        results[role] = measurement

        gates = Gates.from_config(role, config)
        fields = set(ExportReport.__dataclass_fields__)
        report = ExportReport(**{k: v for k, v in sidecar.items() if k in fields})
        report.median_latency_ms = measurement["median_latency_ms"]
        report.p95_latency_ms = measurement["p95_latency_ms"]
        report.latency_hardware = measurement["hardware"]["label"]
        verdict = check_gates(report, gates)

        log(
            f"{role}: p50 {measurement['median_latency_ms']:.1f} ms, "
            f"p95 {measurement['p95_latency_ms']:.1f} ms, "
            f"budget {gates.max_median_latency_ms:.0f} ms -> "
            f"{'WITHIN' if measurement['median_latency_ms'] <= gates.max_median_latency_ms else 'OVER'}"
        )
        for failure in verdict.failures:
            log(f"  gate failure: {failure}")

    if not results:
        raise SystemExit(
            f"no artefacts at v{MODEL_VERSION} to measure - train something first"
        )

    out = WORKING / f"bench-v{MODEL_VERSION}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    log(json.dumps(results, indent=2))

    if os.environ.get("SBR_SKIP_UPLOAD") == "1":
        return
    for role in results:
        config = load_config(role, PROJECT / "ml" / "configs")
        upload_artifacts(
            repo_id=config["hub"]["model_repo"],
            files={f"v{MODEL_VERSION}/bench-v{MODEL_VERSION}.json": out},
            commit_message=(
                f"latency v{MODEL_VERSION} on {machine.where}: "
                + ", ".join(f"{r} p50 {m['median_latency_ms']:.1f} ms" for r, m in results.items())
            ),
            private=config["hub"]["private"],
        )
        break


if __name__ == "__main__":
    main()
