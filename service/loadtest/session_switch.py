#!/usr/bin/env python3
"""Is the missing time SESSION SWITCHING, or is it the second model?

    # A container of its own, so nothing is serving while this measures.
    docker run --rm --cpus 2 \
      -v "$PWD/artifacts:/artefacts:ro" -v "$PWD/service/loadtest:/lt:ro" \
      sbr-detect python /lt/session_switch.py --artefacts /artefacts/loadtest-artefacts

docs/12 probe P8b, step 2. [P4](docs/research/probes/P4-multi-bin-cost-curve.md)
found a frame costing 15-40 ms more than its two graphs, measured inside a loop
that does nothing but run one session and then the other - no JPEG decode, no
letterbox, no NMS. The standing hypothesis is that alternating between two
onnxruntime sessions is itself expensive, because each has its own intra-op
thread pool and each pool spins while idle: two models on two cores means four
threads competing for two.

**That hypothesis and "two graphs cost more than one" predict the same thing**
from the composite measurement alone, and they call for completely different
responses - one is a configuration change, the other is a graph merge. So this
separates them with a variable P4 did not vary: the number of SESSIONS, holding
the number of graphs fixed.

    A  one session, called twice          - two runs, one pool
    B  two sessions of the SAME graph     - two runs, two pools, identical work
    C  validator then identifier          - two runs, two pools, different work

A is the floor. **B minus A is the cost of switching**, because the arithmetic is
identical and only the session count changed. C minus B is what the second model
actually costs. If B is close to A, switching is innocent and the merge is not
worth scoping.

Each is measured under both threading configurations, so the answer arrives with
its own remedy attached rather than needing a second run to find one.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

ITERATIONS = 40
WARMUP = 10


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def open_session(onnx: Path, threads: int, *, spinning: bool, shared_pool: bool) -> Any:
    """The service's own session settings, imported rather than reimplemented.

    A bench that opened its sessions differently from the service would answer a
    question about the bench.
    """
    import sys

    sys.path.insert(0, "/app/service")
    try:
        from artefacts import open_session as service_session
    except ImportError:  # running outside the image
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from artefacts import open_session as service_session

    return service_session(onnx, threads, spinning=spinning, shared_pool=shared_pool)


def time_it(call: Any) -> dict[str, float]:
    import numpy as np  # noqa: F401 - imported for the same reason the caller needs it

    for _ in range(WARMUP):
        call()
    timings = []
    for _ in range(ITERATIONS):
        started = time.perf_counter()
        call()
        timings.append((time.perf_counter() - started) * 1000.0)
    ordered = sorted(timings)
    return {
        "p50_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 2),
        "mean_ms": round(statistics.fmean(ordered), 2),
        "min_ms": round(ordered[0], 2),
    }


def measure(artefacts: Path, *, spinning: bool, shared_pool: bool, threads: int) -> dict[str, Any]:
    import numpy as np

    validator_sidecar = load(artefacts / "validator-v1.json")
    identifier_sidecar = load(artefacts / "identifier-v1.json")
    validator_onnx = artefacts / Path(str(validator_sidecar["onnx_path"])).name
    identifier_onnx = artefacts / Path(str(identifier_sidecar["onnx_path"])).name

    kwargs = {"spinning": spinning, "shared_pool": shared_pool}
    validator_a = open_session(validator_onnx, threads, **kwargs)
    validator_b = open_session(validator_onnx, threads, **kwargs)
    identifier = open_session(identifier_onnx, threads, **kwargs)

    v_size = int(validator_sidecar["imgsz"])
    i_size = int(identifier_sidecar["imgsz"])
    v_name = str(validator_sidecar.get("input_name", "images"))
    i_name = str(identifier_sidecar.get("input_name", "images"))

    frame = np.random.default_rng(0).random((1, 3, v_size, v_size), dtype=np.float32)
    crop = np.random.default_rng(1).random((1, 3, i_size, i_size), dtype=np.float32)

    def one_session_twice() -> None:
        validator_a.run(None, {v_name: frame})
        validator_a.run(None, {v_name: frame})

    def two_sessions_same_graph() -> None:
        validator_a.run(None, {v_name: frame})
        validator_b.run(None, {v_name: frame})

    def two_sessions_two_graphs() -> None:
        validator_a.run(None, {v_name: frame})
        identifier.run(None, {i_name: crop})

    a = time_it(one_session_twice)
    b = time_it(two_sessions_same_graph)
    c = time_it(two_sessions_two_graphs)

    results: dict[str, Any] = {
        "A_one_session_twice": a,
        "B_two_sessions_same_graph": b,
        "C_validator_then_identifier": c,
        # B - A holds the graph and the arithmetic fixed and changes only the
        # session count, so it is the cost of switching and nothing else.
        "switch_cost_ms": round(b["p50_ms"] - a["p50_ms"], 2),
        "second_model_cost_ms": round(c["p50_ms"] - b["p50_ms"], 2),
    }
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--artefacts", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    import platform

    import onnxruntime as ort

    payload: dict[str, Any] = {
        "probe": "P8b",
        "question": "is the unaccounted time session switching, or the second model?",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "machine": f"{platform.machine()} / {platform.system()}",
        "onnxruntime": ort.__version__,
        "intra_op_threads": args.threads,
        "iterations": ITERATIONS,
        "warmup": WARMUP,
        "representative": False,
        "configurations": {},
    }

    for name, spinning, shared_pool in (
        ("default", True, False),
        ("no_spinning", False, False),
        ("shared_pool", True, True),
    ):
        print(f"=== {name} ===", flush=True)
        result = measure(
            args.artefacts, spinning=spinning, shared_pool=shared_pool, threads=args.threads
        )
        payload["configurations"][name] = result
        print(
            f"  A {result['A_one_session_twice']['p50_ms']:>7.2f}   "
            f"B {result['B_two_sessions_same_graph']['p50_ms']:>7.2f}   "
            f"C {result['C_validator_then_identifier']['p50_ms']:>7.2f}   "
            f"switching {result['switch_cost_ms']:+.2f} ms",
            flush=True,
        )

    print(json.dumps(payload, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
