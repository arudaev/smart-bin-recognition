"""Measure each graph's latency on the host this runs on. Started by gce-run.sh.

``SBR_SERVICE_HOST`` is set by the caller, so :func:`sbr.bench.hardware` reports
``representative: true`` and ``gate.py`` will decide a gate on the result. That
is a deliberate act rather than a side effect: it asserts that this box counts
as the service, which is a judgement about what the budget means and was taken
by the maintainer on 2026-08-21.

Latency depends on **architecture and input shape, not on learned weights**
(docs/12's opening claim, and the reason P4 and P5 could run before any model
existed). So the validator's collapsed int8 graph is a perfectly good subject
here: it has the shape the shipping graph would have.
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
OUT = pathlib.Path("/out/latency.json")


#: How many independent measurements per role.
#:
#: **One is not enough, and this project has the evidence.** Two runs of this
#: very script on freshly created, identically specified VMs measured the
#: validator at 18.0 ms and then 14.6 ms - a 20 % spread on the same machine
#: type, the same image and the same graph. A single figure would have been
#: quoted as *the* number. The spread is reported, and the gate is decided on
#: the SLOWEST repeat, which is the conservative direction.
REPEATS = 5


def main() -> None:
    token = os.environ.get("HF_TOKEN") or None
    results: dict = {"hardware": hardware().as_dict(), "repeats": REPEATS, "roles": {}}
    print(json.dumps(results["hardware"], indent=2), flush=True)

    for role in ("validator", "identifier"):
        try:
            sidecar_path = hf_hub_download(REPO, f"v1/{role}-v1.json", token=token)
            sidecar = json.loads(pathlib.Path(sidecar_path).read_text(encoding="utf-8"))
            onnx = hf_hub_download(REPO, f"v1/{sidecar['onnx_path']}", token=token)

            runs = [bench(pathlib.Path(onnx), sidecar) for _ in range(REPEATS)]
            p50s = [r["median_latency_ms"] for r in runs]
            p95s = [r["p95_latency_ms"] for r in runs]
            results["roles"][role] = {
                **runs[-1],
                "repeats": runs,
                "median_latency_ms_runs": p50s,
                "p95_latency_ms_runs": p95s,
                # The gate reads these. Slowest repeat, deliberately.
                "median_latency_ms": max(p50s),
                "p95_latency_ms": max(p95s),
                "median_latency_ms_best": min(p50s),
                "reported": "the SLOWEST of the repeats, not the mean and not the best",
            }
            print(
                f"{role}: p50 runs {[round(p, 1) for p in p50s]} -> "
                f"reporting {max(p50s):.1f} ms  (p95 {max(p95s):.1f} ms)",
                flush=True,
            )
        except Exception as error:  # noqa: BLE001 - an absent role is a fact
            results["roles"][role] = {"error": f"{type(error).__name__}: {error}"}
            print(f"{role}: {type(error).__name__}: {error}", flush=True)

    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
