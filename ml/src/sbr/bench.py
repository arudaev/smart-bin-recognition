"""Measure inference latency, and name the machine it was measured on.

The budgets in ``ml/configs/*.yaml`` are stated **on service CPU** – validator
≤ 50 ms @ 448, identifier ≤ 25 ms per crop – so a number from a training GPU is
not evidence for them. This module is the measuring instrument, kept apart from
both callers so they cannot drift: the two training kernels were once
byte-identical copies of one script, and that is what that looks like.

**On what "service CPU" means now.** The plan was a free Hugging Face Space on
cpu-basic, 2 vCPU. That is no longer possible: creating a Docker Space returns
``402 Payment Required`` – *"Static Spaces are free for everyone, but hosting
Gradio and Docker Spaces on free cpu-basic requires a PRO subscription."* So the
gate is measured on a **Kaggle CPU kernel with onnxruntime pinned to two
threads**, which is x86, free, and reproducible through the same dispatch path
as everything else.

That is a **proxy**, not the service, and it is labelled as one:
:attr:`Hardware.representative` is false unless the measurement came from a real
deployment target. ``ml/scripts/gate.py`` refuses an unrepresentative
measurement unless explicitly told to accept it, and every number carries the
machine with it into the results doc.
"""

from __future__ import annotations

import os
import platform
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The free tier has two vCPUs. Pinning onnxruntime to them is what makes the
#: number mean "one frame on the free tier" rather than "one frame on however
#: many cores the scheduler happened to give us".
SERVICE_VCPUS = 2

DEFAULT_ITERATIONS = 50
DEFAULT_WARMUP = 10


def cpu_model() -> str:
    """Best-effort CPU name. Linux containers have /proc/cpuinfo; be quiet if not."""
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


@dataclass(frozen=True)
class Hardware:
    """Where a latency number came from. An unattributed one is not evidence."""

    where: str
    cpu: str
    cores: int
    threads: int
    onnxruntime: str
    representative: bool

    @property
    def label(self) -> str:
        caveat = "" if self.representative else " [PROXY, not the service]"
        return (
            f"{self.where}, {self.threads} of {self.cores} vCPU, {self.cpu}, "
            f"onnxruntime {self.onnxruntime}{caveat}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "where": self.where,
            "cpu": self.cpu,
            "cores": self.cores,
            "intra_op_threads": self.threads,
            "onnxruntime": self.onnxruntime,
            "representative": self.representative,
        }


def hardware(threads: int = SERVICE_VCPUS) -> Hardware:
    """Describe the machine this is running on, and whether it is the service.

    A Hugging Face Space is the deployment target and counts as representative.
    A Kaggle kernel is a free x86 stand-in and does not, however similar the
    silicon happens to be - the point of the flag is that nobody has to
    remember which is which when reading the number a year from now.
    """
    import onnxruntime as ort

    if space := os.environ.get("SPACE_ID"):
        where, representative = f"HF Space {space}", True
    elif os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or Path("/kaggle").exists():
        where, representative = "Kaggle CPU kernel", False
    elif service := os.environ.get("SBR_SERVICE_HOST"):
        where, representative = service, True
    else:
        where, representative = f"local {platform.system()}", False

    return Hardware(
        where=where,
        cpu=cpu_model(),
        cores=os.cpu_count() or 0,
        threads=threads,
        onnxruntime=ort.__version__,
        representative=representative,
    )


def open_session(onnx_path: Path, threads: int = SERVICE_VCPUS):
    """An onnxruntime session pinned to the service's core count."""
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])


def measure(
    session,
    sidecar: dict[str, Any],
    iterations: int = DEFAULT_ITERATIONS,
    warmup: int = DEFAULT_WARMUP,
    batch: int = 1,
) -> dict[str, Any]:
    """Time one forward pass, repeatedly.

    The input is synthetic and seeded. int8 QDQ convolution latency does not
    depend on pixel values, so a photograph would buy realism nobody can use and
    give the bench a reason to carry image data it has none.

    Nothing about the model is assumed: input name and size come from the
    sidecar, which is the same contract the inference service will read.

    ``batch`` above 1 needs a graph exported with a dynamic batch axis. It exists
    so a frame's cost can be *decomposed*: measuring the identifier at batch n
    separately from the whole frame is what turns "a six-bin frame costs 154 ms"
    into an account of where those milliseconds went.
    """
    import numpy as np

    imgsz = int(sidecar["imgsz"])
    name = sidecar.get("input_name", "images")
    frame = np.random.default_rng(0).random((batch, 3, imgsz, imgsz), dtype=np.float32)

    for _ in range(warmup):
        session.run(None, {name: frame})

    timings: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        session.run(None, {name: frame})
        timings.append((time.perf_counter() - start) * 1000.0)

    ordered = sorted(timings)
    return {
        "median_latency_ms": round(statistics.median(ordered), 3),
        "p95_latency_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "mean_latency_ms": round(statistics.fmean(ordered), 3),
        "min_latency_ms": round(ordered[0], 3),
        "max_latency_ms": round(ordered[-1], 3),
        "iterations": iterations,
        "warmup": warmup,
        "imgsz": imgsz,
        "batch": batch,
    }


def bench(
    onnx_path: Path,
    sidecar: dict[str, Any],
    threads: int = SERVICE_VCPUS,
    iterations: int = DEFAULT_ITERATIONS,
    warmup: int = DEFAULT_WARMUP,
) -> dict[str, Any]:
    """Measure one artefact and return the result with its hardware attached."""
    session = open_session(onnx_path, threads)
    return {
        **measure(session, sidecar, iterations, warmup),
        "role": sidecar.get("role"),
        "version": sidecar.get("version"),
        "onnx_path": sidecar.get("onnx_path"),
        "hardware": hardware(threads).as_dict(),
    }


# --------------------------------------------------------------------------- #
# The frame, rather than the graph
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Graph:
    """An open session together with the sidecar that describes it.

    Pairing them is the point: every shape this module feeds a session comes
    from the sidecar, so a model swap needs no change here and a mismatch is
    impossible rather than merely unlikely.
    """

    session: Any
    sidecar: dict[str, Any]

    @property
    def imgsz(self) -> int:
        return int(self.sidecar["imgsz"])

    @property
    def input_name(self) -> str:
        return str(self.sidecar.get("input_name", "images"))

    @property
    def dynamic_batch(self) -> bool:
        """Whether this graph accepts a batch of more than one.

        Absent from sidecars written before 2026-08-16, and absence means *no* –
        those were all exported with ``dynamic=False``.
        """
        return bool(self.sidecar.get("dynamic_batch", False))

    def run(self, batch: Any) -> None:
        self.session.run(None, {self.input_name: batch})


def _synthetic(batch: int, imgsz: int, seed: int = 0) -> Any:
    """A seeded NCHW block. int8 QDQ convolution latency does not depend on
    pixel values, so a photograph would buy realism nobody can use."""
    import numpy as np

    return np.random.default_rng(seed).random((batch, 3, imgsz, imgsz), dtype=np.float32)


def bench_frame(
    validator: Graph,
    identifier: Graph | None,
    crops: int,
    *,
    batched: bool = True,
    iterations: int = DEFAULT_ITERATIONS,
    warmup: int = DEFAULT_WARMUP,
) -> dict[str, Any]:
    """Time one whole **frame**: the validator once, then the identifier per crop.

    This is the quantity ``docs/05-cost-model.md`` § 3 actually prices, and it is
    not the quantity :func:`measure` reports. A frame holding six containers – the
    PRD calls that a normal input – costs one validator pass and *six* identifier
    passes, and the concurrency ceiling follows from the total, not from either
    graph alone. Measuring the graphs separately and adding them up would also
    miss what the caller most wants to know, which is whether pushing the crops
    through one call beats pushing them through *n*.

    ``batched=True`` stacks the crops into a single ``(n, 3, imgsz, imgsz)`` call.
    It raises if the graph was exported with a static batch axis, because
    quietly falling back to sequential is how a service ends up three times more
    expensive than its own cost model says.
    """
    frame = _synthetic(1, validator.imgsz)

    batch: Any = None
    single: Any = None
    if identifier is not None and crops > 0:
        if batched:
            if not identifier.dynamic_batch:
                raise ValueError(
                    f"cannot batch {crops} crops: the {identifier.sidecar.get('role')!r} graph was "
                    "exported with a static batch axis. Re-export it with a dynamic batch – see "
                    "sbr.export.onnx_export.batched_role."
                )
            batch = _synthetic(crops, identifier.imgsz, seed=1)
        else:
            single = _synthetic(1, identifier.imgsz, seed=1)

    def once() -> None:
        validator.run(frame)
        if identifier is None or crops == 0:
            return
        if batched:
            identifier.run(batch)
        else:
            for _ in range(crops):
                identifier.run(single)

    for _ in range(warmup):
        once()

    timings: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        once()
        timings.append((time.perf_counter() - start) * 1000.0)

    ordered = sorted(timings)
    return {
        "crops": crops,
        "batched": batched if crops > 0 else None,
        "median_latency_ms": round(statistics.median(ordered), 3),
        "p95_latency_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "mean_latency_ms": round(statistics.fmean(ordered), 3),
        "min_latency_ms": round(ordered[0], 3),
        "max_latency_ms": round(ordered[-1], 3),
        "iterations": iterations,
        "warmup": warmup,
        "validator_imgsz": validator.imgsz,
        "identifier_imgsz": identifier.imgsz if identifier else None,
    }
