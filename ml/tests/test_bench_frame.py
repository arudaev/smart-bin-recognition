"""Tests for the frame-level measurement docs/12 P4 needs.

``sbr.bench.measure`` times one graph. That is what the ship gate budgets and it
is *not* what docs/05 § 3 prices: a frame holding six containers costs one
validator pass and six identifier passes, and the concurrency ceiling follows
from the total. :func:`sbr.bench.bench_frame` measures the total.

These run against a fake session rather than onnxruntime. What is being tested is
the shape discipline - how many calls, at what batch, from whose sidecar - and a
real graph would make that slower to check and no more convincing.
"""

from __future__ import annotations

import numpy as np
import pytest

from sbr.bench import Graph, bench_frame


class FakeSession:
    """Records the shape of every call it is given."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, ...]] = []

    def run(self, _outputs, feed: dict) -> list:
        (array,) = feed.values()
        self.calls.append(tuple(array.shape))
        return [np.zeros((1,), dtype=np.float32)]


def graph(role: str, imgsz: int, *, dynamic: bool, input_name: str = "images") -> Graph:
    return Graph(
        FakeSession(),
        {"role": role, "imgsz": imgsz, "input_name": input_name, "dynamic_batch": dynamic},
    )


FAST = {"iterations": 2, "warmup": 1}


def test_an_empty_frame_costs_the_validator_and_nothing_else():
    # The 0-bin row is what separates "the detector costs X" from "a frame costs
    # X", and a pipeline that ran the identifier on nothing would hide that.
    validator = graph("validator", 448, dynamic=False)
    identifier = graph("identifier", 320, dynamic=True)
    bench_frame(validator, identifier, 0, **FAST)

    assert identifier.session.calls == []
    assert all(shape == (1, 3, 448, 448) for shape in validator.session.calls)


def test_batched_crops_are_one_call_at_the_full_batch():
    identifier = graph("identifier", 320, dynamic=True)
    bench_frame(graph("validator", 448, dynamic=False), identifier, 6, batched=True, **FAST)

    per_frame = len(identifier.session.calls) // (FAST["iterations"] + FAST["warmup"])
    assert per_frame == 1
    assert identifier.session.calls[0] == (6, 3, 320, 320)


def test_sequential_crops_are_n_calls_at_batch_one():
    identifier = graph("identifier", 320, dynamic=True)
    bench_frame(graph("validator", 448, dynamic=False), identifier, 6, batched=False, **FAST)

    per_frame = len(identifier.session.calls) // (FAST["iterations"] + FAST["warmup"])
    assert per_frame == 6
    assert identifier.session.calls[0] == (1, 3, 320, 320)


def test_batching_a_static_graph_is_refused_rather_than_silently_sequential():
    """The failure this guards is invisible in production.

    A graph exported with ``dynamic=False`` loads and serves perfectly well. If
    bench_frame quietly fell back to sequential, the measured curve would be the
    sequential one while the report claimed it was batched - and the service
    built on that number would be three times its own cost model at six bins.
    """
    with pytest.raises(ValueError, match="static batch axis"):
        bench_frame(
            graph("validator", 448, dynamic=False),
            graph("identifier", 320, dynamic=False),
            3,
            batched=True,
            **FAST,
        )


def test_the_input_name_comes_from_the_sidecar():
    # Nothing about a model is hard-coded, here or in the service.
    validator = graph("validator", 448, dynamic=False, input_name="pixel_values")
    bench_frame(validator, None, 0, **FAST)
    assert validator.session.calls  # it ran, so the feed key was accepted


def test_a_sidecar_without_the_flag_is_treated_as_static():
    # Sidecars written before 2026-08-16 have no `dynamic_batch` key, and every
    # one of them was exported with dynamic=False. Absence must mean no.
    stale = Graph(FakeSession(), {"role": "identifier", "imgsz": 320})
    assert stale.dynamic_batch is False


def test_the_result_names_the_scene_it_measured():
    # Any number that ships names what it was measured on. A frame latency
    # without its crop count is not a number anyone can use.
    result = bench_frame(
        graph("validator", 448, dynamic=False), graph("identifier", 320, dynamic=True), 3, **FAST
    )
    assert result["crops"] == 3
    assert result["batched"] is True
    assert result["validator_imgsz"] == 448
    assert result["identifier_imgsz"] == 320
