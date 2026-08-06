#!/usr/bin/env python3
"""Decide whether an artefact may ship, on evidence measured where it will run.

The Kaggle kernel cannot answer this. It has a GPU and somebody else's CPU, so
it exports, evaluates accuracy, and uploads with latency **unmeasured** – which
is a distinct verdict from passing (``sbr.export.onnx_export.GateResult``).

This script closes that gap: it asks the 2-vCPU bench Space for p50/p95, writes
the answer and the hardware it came from into the sidecar, re-runs the gates,
and exits non-zero if any of them failed or is still unmeasured.

    python ml/scripts/gate.py --role validator  --version 1
    python ml/scripts/gate.py --role identifier --version 1 --publish

``--publish`` writes the updated sidecar back to the model repo, because the
inference service reads the sidecar and should never see an artefact whose
verdict is missing. It is opt-in: by default this only writes locally.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.config import load_config  # noqa: E402
from sbr.export.onnx_export import (  # noqa: E402
    Gates,
    check_gates,
    load_sidecar,
    sidecar_path,
    write_sidecar,
)

logger = logging.getLogger("gate")

DEFAULT_BENCH_URL = "https://arudaev-sbr-bench.hf.space"
BENCH_TIMEOUT_S = 600


def fetch_bench(
    bench_url: str, role: str, version: int, repo: str, revision: str, iterations: int
) -> dict:
    """Ask the bench Space to time the artefact. Returns its JSON verbatim."""
    query = urllib.parse.urlencode(
        {
            "role": role,
            "version": version,
            "repo": repo,
            "revision": revision,
            "iterations": iterations,
        }
    )
    url = f"{bench_url.rstrip('/')}/bench?{query}"
    logger.info("measuring: %s", url)
    try:
        with urllib.request.urlopen(url, timeout=BENCH_TIMEOUT_S) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:  # noqa: PERF203 – the message matters
        raise SystemExit(f"bench returned {error.code}: {error.read().decode()[:400]}") from None
    except urllib.error.URLError as error:
        raise SystemExit(
            f"could not reach the bench at {bench_url}: {error.reason}. "
            "A free Space sleeps when idle – open it once in a browser and retry."
        ) from None


def download_sidecar(repo: str, revision: str, role: str, version: int, out_dir: Path) -> Path:
    """Pull the sidecar the training kernel uploaded."""
    from huggingface_hub import hf_hub_download

    from sbr.utils.hub import configure_hf_runtime, load_hf_token

    configure_hf_runtime()
    local = hf_hub_download(
        repo_id=repo,
        filename=f"v{version}/{role}-v{version}.json",
        revision=revision,
        token=load_hf_token(),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = sidecar_path(out_dir, role, version)
    target.write_bytes(Path(local).read_bytes())
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", choices=["validator", "identifier"], required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--repo", default=None, help="model repo (defaults to the config's hub.model_repo)")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--bench-url", default=DEFAULT_BENCH_URL)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--sidecar", type=Path, default=None, help="skip the download and use this one")
    parser.add_argument("--publish", action="store_true", help="write the verdict back to the model repo")
    parser.add_argument(
        "--allow-unrepresentative-hardware",
        action="store_true",
        help="accept a measurement taken somewhere other than the Space. Records "
             "that it was, because the budget says 'service CPU' and a laptop is not one.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = load_config(args.role)
    repo = args.repo or config["hub"]["model_repo"]
    gates = Gates.from_config(args.role, config)

    # --- the artefact's own account of itself ------------------------------- #
    if args.sidecar:
        local_sidecar = args.sidecar
    else:
        local_sidecar = download_sidecar(repo, args.revision, args.role, args.version, args.artifacts)
    report = load_sidecar(local_sidecar)
    logger.info(
        "%s v%d: %s, imgsz %d, %d classes, int8=%s",
        report.role, report.version, Path(report.onnx_path).name,
        report.imgsz, len(report.classes), report.quantised,
    )

    # --- the measurement ---------------------------------------------------- #
    measurement = fetch_bench(
        args.bench_url, args.role, args.version, repo, args.revision, args.iterations
    )
    hardware = measurement["hardware"]

    if not hardware.get("space") and not args.allow_unrepresentative_hardware:
        raise SystemExit(
            f"the bench answered from {hardware['label']!r}, which is not the service.\n"
            "The budget is stated on service CPU; measuring elsewhere produces a "
            "number that cannot be compared to it. Pass "
            "--allow-unrepresentative-hardware if you know why you want that."
        )

    report.median_latency_ms = measurement["median_latency_ms"]
    report.p95_latency_ms = measurement["p95_latency_ms"]
    report.latency_hardware = hardware["label"]

    logger.info(
        "p50 %.1f ms, p95 %.1f ms on %s (budget %.0f ms)",
        report.median_latency_ms, report.p95_latency_ms,
        report.latency_hardware, gates.max_median_latency_ms,
    )

    # --- the verdict -------------------------------------------------------- #
    updated = write_sidecar(report, local_sidecar.parent, gates)
    result = check_gates(report, gates)
    result.log()

    if args.publish and result.may_ship:
        from sbr.utils.hub import upload_artifacts

        upload_artifacts(
            repo_id=repo,
            files={f"v{args.version}/{updated.name}": updated},
            commit_message=(
                f"{args.role} v{args.version}: p50 {report.median_latency_ms:.1f} ms "
                f"on {hardware['label']}"
            ),
            private=config["hub"]["private"],
        )
    elif args.publish:
        logger.warning("not publishing: the artefact did not pass its gates")

    if not result.may_ship:
        raise SystemExit(1)
    logger.info("all ship gates passed – %s v%d may ship", args.role, args.version)


if __name__ == "__main__":
    main()
