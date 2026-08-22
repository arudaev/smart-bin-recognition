#!/usr/bin/env python3
"""P13 arm A: what does leaving the validator in fp32 cost, as a ratio?

    python ml/scripts/probe_fp32_latency.py --out docs/research/probes/data/P13-fp32-viability.json

**Why a ratio and not two numbers.** ``docs/12`` P8 established that this
project cannot hold an *absolute* latency figure still on a development
workstation: the identical baseline measured 7 concurrent scanners at 22:30 and
4 at 23:48 on the same laptop. A ratio taken back-to-back, in one session, on one
box, with one onnxruntime, is a far more robust quantity than either of its
terms - the host noise that moves the numerator moves the denominator with it.

So this script reports ``R = fp32_p50 / int8_p50`` and labels every absolute
figure it prints ``representative: false``. The absolutes are here for the record
and must never be quoted as service latency.

**The two graphs.** fp32 is ``artifacts/local/validator-v1.onnx`` - a local
export, byte-identical to ``model-fp32.onnx``. int8 is ``v1/validator-v1.onnx``
from the model repo, which is the graph P12 actually measured. Both are the
validator at 448.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.bench import bench, hardware  # noqa: E402

logger = logging.getLogger("probe_fp32")

MODEL_REPO = "arudaev/smart-bin-detect"

#: The gate the projection is against. Validator budget, docs/07.
LATENCY_BUDGET_MS = 50.0

#: P12's canonical run - the validator's share of the frame on representative
#: hardware. Read from the file rather than restated: a projection over a
#: baseline should name the file the baseline came from.
P12_LATENCY = REPO_ROOT / "docs/research/probes/data/P12-gce-latency.json"

#: P12 measured the whole frame at this cost at one bin per frame, and derived
#: this ceiling from it (docs/05 section 3). Neither lives in the latency file -
#: they are the load test's frame accounting - so both are named here with their
#: source rather than silently inlined.
P12_FRAME_MS = 49.0
P12_SCANNERS_1BIN = 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=10)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from huggingface_hub import hf_hub_download

    fp32_onnx = REPO_ROOT / "artifacts/local/validator-v1.onnx"
    fp32_side = json.loads((REPO_ROOT / "artifacts/local/validator-v1.json").read_text(encoding="utf-8"))
    if not fp32_onnx.exists():
        raise SystemExit(f"no fp32 validator at {fp32_onnx}")
    if fp32_side.get("quantised"):
        raise SystemExit("the 'fp32' sidecar says quantised: true - refusing to measure the wrong graph")

    logger.info("downloading the int8 validator from %s", MODEL_REPO)
    int8_onnx = Path(hf_hub_download(MODEL_REPO, "v1/validator-v1.onnx"))
    int8_side = json.loads(Path(hf_hub_download(MODEL_REPO, "v1/validator-v1.json")).read_text(encoding="utf-8"))
    if not int8_side.get("quantised"):
        raise SystemExit("the published validator sidecar says quantised: false - the arms would be identical")

    logger.info("fp32  %s (%.1f MB)", fp32_onnx.name, fp32_onnx.stat().st_size / 1e6)
    logger.info("int8  %s (%.1f MB)", int8_onnx.name, int8_onnx.stat().st_size / 1e6)

    # ALTERNATE THE ARMS. Running five fp32 then five int8 lets any drift over
    # the session - thermal, or another process arriving - land entirely on one
    # arm and be read as a difference between formats.
    fp32_runs: list[dict[str, Any]] = []
    int8_runs: list[dict[str, Any]] = []
    for i in range(args.repeats):
        logger.info("cycle %d/%d", i + 1, args.repeats)
        fp32_runs.append(bench(fp32_onnx, fp32_side, iterations=args.iterations, warmup=args.warmup))
        int8_runs.append(bench(int8_onnx, int8_side, iterations=args.iterations, warmup=args.warmup))

    def summarise(runs: list[dict[str, Any]]) -> dict[str, Any]:
        med = [float(r["median_latency_ms"]) for r in runs]
        return {
            "median_latency_ms": round(max(med), 3),
            "median_latency_ms_runs": med,
            "median_latency_ms_best": round(min(med), 3),
            "median_latency_ms_mean": round(statistics.mean(med), 3),
            "spread_ms": round(max(med) - min(med), 3),
            "p95_latency_ms": round(max(float(r["p95_latency_ms"]) for r in runs), 3),
            "iterations": args.iterations,
            "warmup": args.warmup,
            "imgsz": runs[0]["imgsz"],
            "reported": "the SLOWEST of the repeats, not the mean and not the best",
        }

    fp32 = summarise(fp32_runs)
    int8 = summarise(int8_runs)

    # The ratio, taken every way, so a reader can see it is not an artefact of
    # which repeat got picked.
    r_worst = fp32["median_latency_ms"] / int8["median_latency_ms"]
    r_mean = fp32["median_latency_ms_mean"] / int8["median_latency_ms_mean"]
    r_paired = statistics.median(
        [f / i for f, i in zip(fp32["median_latency_ms_runs"], int8["median_latency_ms_runs"], strict=True)]
    )

    p12 = json.loads(P12_LATENCY.read_text(encoding="utf-8"))
    v_p12 = float(p12["roles"]["validator"]["median_latency_ms"])

    # THE PROJECTION. Stated as arithmetic in the file so nobody has to trust a
    # sentence about it. fp32 makes the validator's share of the frame more
    # expensive and leaves the rest of the frame alone.
    projected_validator = v_p12 * r_paired
    projected_frame = P12_FRAME_MS + v_p12 * (r_paired - 1.0)
    projected_scanners = P12_SCANNERS_1BIN * (P12_FRAME_MS / projected_frame)

    # The pre-registered spend threshold, recomputed rather than restated.
    r_threshold = LATENCY_BUDGET_MS / v_p12

    report = {
        "probe": "P13",
        "question": "is an fp32 validator ship profile viable?",
        "arm": "A - free local triage",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pre_registered": "docs/research/probes/P13-fp32-validator-viability.md at 09c6b93",
        "hardware": hardware().as_dict(),
        "representative": False,
        "why_not_representative": (
            "a development workstation running the tooling. docs/12 P8 showed this "
            "class of host cannot hold an absolute latency figure still. The RATIO is "
            "the result; the absolutes are recorded and must not be quoted as service latency"
        ),
        "architecture": {
            "machine": platform.machine(),
            "system": platform.system(),
            "service_architecture": "x86-64, Intel Cascade Lake (AVX-512 VNNI)",
            "same_architecture_as_service": platform.machine().lower() in {"x86_64", "amd64"},
        },
        "ratio_transferability": (
            "READ THIS BEFORE USING THE RATIO. A ratio cancels host NOISE - thermal "
            "drift, another process arriving - because the noise moves both arms "
            "together. It does NOT cancel a systematic per-FORMAT difference between "
            "hosts, and instruction-set support for int8 is exactly that. Cascade Lake "
            "has AVX-512 VNNI, which accelerates int8 convolution and does nothing for "
            "fp32; this box has no VNNI at all. So a ratio measured here is not "
            "transferable to the service host, and the projection built on it below is "
            "an ORDER-OF-MAGNITUDE sanity check for deciding whether to spend money - "
            "never an answer"
        ),
        "arms_alternated": True,
        "graphs": {
            "fp32": {
                "path": str(fp32_onnx.relative_to(REPO_ROOT)).replace("\\", "/"),
                "bytes": fp32_onnx.stat().st_size,
                "quantised": False,
            },
            "int8": {
                "path": f"{MODEL_REPO}:v1/validator-v1.onnx",
                "bytes": int8_onnx.stat().st_size,
                "quantised": True,
            },
        },
        "results": {"fp32": fp32, "int8": int8},
        "ratio": {
            "paired_median": round(r_paired, 4),
            "worst_over_worst": round(r_worst, 4),
            "mean_over_mean": round(r_mean, 4),
            "reported": "paired_median - the median of the per-cycle ratios, which is what alternating the arms buys",
        },
        "projection": {
            "is_a_projection": True,
            "baseline": "docs/research/probes/data/P12-gce-latency.json (canonical run 2)",
            "p12_validator_p50_ms": v_p12,
            "p12_frame_ms": P12_FRAME_MS,
            "p12_scanners_at_1_bin": P12_SCANNERS_1BIN,
            "projected_fp32_validator_p50_ms": round(projected_validator, 2),
            "projected_frame_ms": round(projected_frame, 2),
            "projected_scanners_at_1_bin": round(projected_scanners, 2),
            "latency_budget_ms": LATENCY_BUDGET_MS,
            "projected_clears_latency_gate": bool(projected_validator <= LATENCY_BUDGET_MS),
        },
        "decision": {
            "rule": "spend the GCE run only if R < 50 / 18.252 = 2.74 (pre-registered)",
            "r_threshold": round(r_threshold, 4),
            "r_measured": round(r_paired, 4),
            "spend": bool(r_paired < r_threshold),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    logger.info("")
    logger.info("fp32 p50   %.3f ms  (runs %s)", fp32["median_latency_ms"], fp32["median_latency_ms_runs"])
    logger.info("int8 p50   %.3f ms  (runs %s)", int8["median_latency_ms"], int8["median_latency_ms_runs"])
    logger.info("RATIO      %.4f  (threshold %.4f)", r_paired, r_threshold)
    logger.info(
        "projected  validator %.1f ms, frame %.1f ms, %.2f scanners at 1 bin",
        projected_validator,
        projected_frame,
        projected_scanners,
    )
    logger.info("SPEND      %s", report["decision"]["spend"])
    logger.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
