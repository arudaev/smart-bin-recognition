"""P13 arm C: the validator in both formats, on ONE host, arms alternated.

Started by ``gce-fp32.sh``. Not useful alone.

**Why paired, and why on one instance.** Commit ``8fe1450`` established that two
freshly created, identically specified VMs reproduce this project's p50 to
0.05 ms but move p95 by up to 3.9 ms. So comparing a new fp32 number against
P12's int8 number would be measuring the instance as much as the format. Both
arms run here, in one session, alternating cycle by cycle, so any drift over the
session lands on both rather than on whichever went second.

**Why the local ratio is not enough, and this run had to happen.** P13 arm A
measured the ratio on the development workstation and got **0.59** - fp32
*faster* than int8. That box is a Snapdragon X Elite: ARM64, no AVX-512 VNNI.
Cascade Lake has VNNI, which accelerates int8 convolution and does nothing at
all for fp32. A ratio cancels host noise; it does not cancel an instruction set.
The number this file produces is the one that counts.

``SBR_SERVICE_HOST`` is set by the caller, so ``sbr.bench.hardware()`` reports
``representative: true``. That is a deliberate assertion that this box counts as
the service, and it is what lets a gate be decided on the result.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, "/app/ml/src")

from huggingface_hub import hf_hub_download  # noqa: E402
from sbr.bench import bench, hardware  # noqa: E402

REPO = "arudaev/smart-bin-detect"
OUT = pathlib.Path("/out/latency-paired.json")

#: Where gce-fp32.sh put the fp32 validator it shipped from the working tree.
FP32_DIR = pathlib.Path(os.environ.get("FP32_DIR", "/tmp/sbr/fp32"))

#: Five cycles, each one int8 followed by one fp32. Same reasoning as
#: gce-latency.py: one measurement is not a measurement on this project's own
#: evidence.
CYCLES = int(os.environ.get("CYCLES", "5"))


def _paired_summary(p50s: list[float], p95s: list[float]) -> dict:
    return {
        # The gate reads these. Slowest repeat, deliberately.
        "median_latency_ms": max(p50s),
        "p95_latency_ms": max(p95s),
        "median_latency_ms_runs": p50s,
        "p95_latency_ms_runs": p95s,
        "median_latency_ms_best": min(p50s),
        "spread_ms": round(max(p50s) - min(p50s), 3),
        "reported": "the SLOWEST of the repeats, not the mean and not the best",
    }


def main() -> None:
    token = os.environ.get("HF_TOKEN") or None
    hw = hardware().as_dict()
    print(json.dumps(hw, indent=2), flush=True)

    # int8: the published graph, which is what P12 measured.
    int8_sidecar = json.loads(
        pathlib.Path(hf_hub_download(REPO, "v1/validator-v1.json", token=token)).read_text(encoding="utf-8")
    )
    int8_onnx = pathlib.Path(hf_hub_download(REPO, f"v1/{int8_sidecar['onnx_path']}", token=token))

    # fp32: shipped from the working tree, never published. Measuring a format
    # is not a reason to put an ungated graph in the model repo.
    fp32_sidecar = json.loads((FP32_DIR / "validator-v1.json").read_text(encoding="utf-8"))
    fp32_onnx = FP32_DIR / fp32_sidecar["onnx_path"]

    if not int8_sidecar.get("quantised"):
        raise SystemExit("the published validator says quantised: false - the arms would be identical")
    if fp32_sidecar.get("quantised"):
        raise SystemExit("the shipped fp32 sidecar says quantised: true - wrong graph")

    print(f"int8 {int8_onnx} ({int8_onnx.stat().st_size / 1e6:.1f} MB)", flush=True)
    print(f"fp32 {fp32_onnx} ({fp32_onnx.stat().st_size / 1e6:.1f} MB)", flush=True)

    int8_runs: list[dict] = []
    fp32_runs: list[dict] = []
    for cycle in range(CYCLES):
        print(f"cycle {cycle + 1}/{CYCLES}", flush=True)
        int8_runs.append(bench(int8_onnx, int8_sidecar))
        fp32_runs.append(bench(fp32_onnx, fp32_sidecar))

    int8_p50 = [r["median_latency_ms"] for r in int8_runs]
    fp32_p50 = [r["median_latency_ms"] for r in fp32_runs]

    # The per-cycle ratio, which is what alternating the arms buys: each term is
    # taken under the same conditions as its partner.
    ratios = sorted(f / i for f, i in zip(fp32_p50, int8_p50))
    paired_median = ratios[len(ratios) // 2]

    results = {
        "probe": "P13",
        "arm": "C - paired, on the service host",
        "hardware": hw,
        "representative": hw.get("representative"),
        "cycles": CYCLES,
        "arms_alternated": True,
        "role": "validator",
        "imgsz": int8_sidecar.get("imgsz"),
        "formats": {
            "int8": {
                **_paired_summary(int8_p50, [r["p95_latency_ms"] for r in int8_runs]),
                "source": f"{REPO}:v1/validator-v1.onnx",
                "bytes": int8_onnx.stat().st_size,
                "quantised": True,
                "repeats": int8_runs,
            },
            "fp32": {
                **_paired_summary(fp32_p50, [r["p95_latency_ms"] for r in fp32_runs]),
                "source": "artifacts/local/validator-v1.onnx, shipped from the working tree",
                "bytes": fp32_onnx.stat().st_size,
                "quantised": False,
                "repeats": fp32_runs,
            },
        },
        "ratio": {
            "paired_median": round(paired_median, 4),
            "per_cycle": [round(f / i, 4) for f, i in zip(fp32_p50, int8_p50)],
            "definition": "fp32_p50 / int8_p50, per cycle, median of those",
        },
        "budget_ms": 50.0,
        "fp32_clears_latency_gate": bool(max(fp32_p50) <= 50.0),
        "int8_clears_latency_gate": bool(max(int8_p50) <= 50.0),
    }

    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("", flush=True)
    print(f"int8 p50 runs {[round(p, 1) for p in int8_p50]} -> reporting {max(int8_p50):.2f} ms", flush=True)
    print(f"fp32 p50 runs {[round(p, 1) for p in fp32_p50]} -> reporting {max(fp32_p50):.2f} ms", flush=True)
    print(f"RATIO {paired_median:.4f}   fp32 clears 50 ms: {results['fp32_clears_latency_gate']}", flush=True)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
