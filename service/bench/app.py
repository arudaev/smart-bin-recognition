"""The latency bench: what the ship gate actually measures.

The budgets in ``ml/configs/*.yaml`` say "service CPU" – validator ≤ 50 ms
@ 448, identifier ≤ 25 ms per crop. A number measured on a training GPU or on a
laptop that throttles differently is not evidence for those budgets, so this
runs where the service will run: a free Hugging Face Space, CPU-basic, 2 vCPU.

It is deliberately small and deliberately boring. It loads an int8 ONNX artefact
and its sidecar from the model repo, runs the graph, and reports percentiles
together with the machine it saw them on. Nothing about the model is hard-coded
here – input name, shape and normalisation all come from the sidecar, which is
the same contract the real inference service will read in phase 3.

This is also the skeleton ``service/`` needs: a Space that boots, pulls a pinned
revision, and answers over HTTP.
"""

from __future__ import annotations

import os
import platform
import statistics
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException
from huggingface_hub import hf_hub_download

#: The service has two vCPUs. Pinning onnxruntime to them is what makes the
#: number mean "one frame on the free tier" rather than "one frame on however
#: many cores the scheduler felt like giving us".
INTRA_OP_THREADS = int(os.environ.get("SBR_INTRA_OP_THREADS", "2"))

#: Only this project's own artefact repos. The Space is public; without this it
#: would happily download and execute an ONNX graph from any repo a caller named.
ALLOWED_REPOS = {
    "arudaev/smart-bin-detect",
    "arudaev/smart-bin-identify",
}

DEFAULT_ITERATIONS = 50
DEFAULT_WARMUP = 10
MAX_ITERATIONS = 500

app = FastAPI(title="Smart Bin Recognition – latency bench")


# --------------------------------------------------------------------------- #
# The machine
# --------------------------------------------------------------------------- #


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
    """Named, because an unattributed latency number is not evidence."""

    cpu: str
    cores: int
    threads: int
    onnxruntime: str
    space: str | None

    @property
    def label(self) -> str:
        where = self.space or "local"
        return (
            f"{where}, {self.cores} vCPU, {self.threads} intra-op threads, "
            f"{self.cpu}, onnxruntime {self.onnxruntime}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "cpu": self.cpu,
            "cores": self.cores,
            "intra_op_threads": self.threads,
            "onnxruntime": self.onnxruntime,
            "space": self.space,
        }


def hardware() -> Hardware:
    space = os.environ.get("SPACE_ID")
    return Hardware(
        cpu=cpu_model(),
        cores=os.cpu_count() or 0,
        threads=INTRA_OP_THREADS,
        onnxruntime=ort.__version__,
        space=f"HF Space {space} (CPU-basic)" if space else None,
    )


# --------------------------------------------------------------------------- #
# The artefact
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=8)
def load(repo_id: str, revision: str, role: str, version: int) -> tuple[ort.InferenceSession, dict]:
    """Pull an int8 artefact and its sidecar, and open a session over it."""
    if repo_id not in ALLOWED_REPOS:
        raise HTTPException(400, f"repo {repo_id!r} is not one of {sorted(ALLOWED_REPOS)}")

    import json

    token = os.environ.get("HF_TOKEN")
    sidecar_path = hf_hub_download(
        repo_id, f"v{version}/{role}-v{version}.json", revision=revision, token=token
    )
    sidecar = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))

    onnx_name = Path(sidecar["onnx_path"]).name
    onnx_path = hf_hub_download(
        repo_id, f"v{version}/{onnx_name}", revision=revision, token=token
    )

    options = ort.SessionOptions()
    options.intra_op_num_threads = INTRA_OP_THREADS
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    session = ort.InferenceSession(onnx_path, options, providers=["CPUExecutionProvider"])
    return session, sidecar


def measure(session: ort.InferenceSession, sidecar: dict, iterations: int, warmup: int) -> dict:
    """Time one forward pass, repeatedly.

    The input is synthetic and seeded. int8 QDQ convolution latency does not
    depend on pixel values, so a photograph would buy realism nobody can use and
    cost the bench a dependency on image data it has no reason to hold.
    """
    imgsz = int(sidecar["imgsz"])
    name = sidecar.get("input_name", "images")
    rng = np.random.default_rng(0)
    frame = rng.random((1, 3, imgsz, imgsz), dtype=np.float32)

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
    }


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


@app.get("/")
def root() -> dict:
    return {
        "service": "smart-bin-recognition latency bench",
        "purpose": "measure the ship-gate latency on the CPU the service runs on",
        "hardware": hardware().as_dict(),
        "usage": "/bench?role=validator&version=1&repo=arudaev/smart-bin-detect&revision=<sha>",
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/bench")
def bench(
    role: str,
    version: int,
    repo: str = "arudaev/smart-bin-detect",
    revision: str = "main",
    iterations: int = DEFAULT_ITERATIONS,
    warmup: int = DEFAULT_WARMUP,
) -> dict:
    if role not in ("validator", "identifier"):
        raise HTTPException(400, f"unknown role {role!r}")
    iterations = max(1, min(iterations, MAX_ITERATIONS))
    warmup = max(0, min(warmup, MAX_ITERATIONS))

    session, sidecar = load(repo, revision, role, version)
    result = measure(session, sidecar, iterations, warmup)

    return {
        "role": role,
        "version": version,
        "repo": repo,
        "revision": revision,
        "onnx_path": sidecar["onnx_path"],
        "hardware": hardware().as_dict(),
        **result,
    }
