"""Fixtures for the service tests.

Nothing here loads onnxruntime. The service's own logic - the refusal, the
framing, the crop batching, the resolver call, the ladder - is all testable
against a stub session, and a test suite that needed a 10 MB int8 graph to run
would be a test suite nobody runs on every commit.

The one thing a stub cannot check is that a real graph's output decodes
correctly, and that is what the end-to-end run against the container is for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))
sys.path.insert(0, str(SERVICE.parent / "ml" / "src"))


class FakeSession:
    """Records what it was asked, answers with whatever it was given.

    ``outputs`` is a callable so a test can decide the answer from the input
    shape - which is how the identifier's batch dimension gets checked.
    """

    def __init__(self, outputs: Any = None) -> None:
        self.calls: list[tuple[int, ...]] = []
        self._outputs = outputs

    def run(self, _names: Any, feed: dict) -> list[np.ndarray]:
        (array,) = feed.values()
        self.calls.append(tuple(array.shape))
        if callable(self._outputs):
            return [self._outputs(array)]
        if self._outputs is not None:
            return [self._outputs]
        return [np.zeros((1, 5, 10), dtype=np.float32)]


def sidecar(
    role: str,
    *,
    may_ship: bool = True,
    imgsz: int | None = None,
    classes: list[str] | None = None,
    dynamic_batch: bool | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """A sidecar shaped exactly like ``write_sidecar`` produces one."""
    payload: dict[str, Any] = {
        "role": role,
        "version": 1,
        "onnx_path": f"{role}-v1.onnx",
        "imgsz": imgsz if imgsz is not None else (448 if role == "validator" else 320),
        "classes": classes if classes is not None else (["bin"] if role == "validator" else []),
        "quantised": True,
        "input_name": "images",
        "layout": "NCHW",
        "normalisation": {"scale": 1 / 255.0, "mean": [0, 0, 0], "std": [1, 1, 1]},
        "dynamic_batch": dynamic_batch
        if dynamic_batch is not None
        else (role == "identifier"),
        "nms": {"in_graph": False, "iou": 0.45, "score": 0.35},
        "gate_result": {
            "failures": [] if may_ship else ["median latency 91.0 ms exceeds the 50 ms budget"],
            "unmeasured": [],
            "may_ship": may_ship,
        },
        "target_result": {"met": {}, "missed": {}, "unmeasurable": []},
    }
    return payload | extra


@pytest.fixture
def artefact_dir(tmp_path: Path):
    """Writes sidecars and placeholder graphs into a directory the loader reads.

    The ``.onnx`` files are empty. Every test that gets as far as opening one is
    a test about the refusal, and the refusal happens first - which is itself
    worth asserting, since a gate that ran after the model was loaded would be a
    gate that had already lost.
    """

    def write(role: str, **kwargs: Any) -> Path:
        payload = sidecar(role, **kwargs)
        (tmp_path / f"{role}-v1.json").write_text(json.dumps(payload), encoding="utf-8")
        (tmp_path / f"{role}-v1.onnx").write_bytes(b"")
        return tmp_path

    write.path = tmp_path  # type: ignore[attr-defined]
    return write


@pytest.fixture
def jpeg() -> bytes:
    """A small real JPEG, so decode_jpeg is exercised rather than mocked."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(
        np.random.default_rng(0).integers(0, 256, (240, 320, 3), dtype=np.uint8)
    ).save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()
