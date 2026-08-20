"""Pick the winning export configuration, by the rule docs/12 P9 fixed in advance.

This lives here rather than inside the Kaggle kernel for one reason: a kernel
cannot be imported, so a selection rule written there is a rule nothing can
test. The rule decides whether an artefact reaches the ship gate at all, which
makes it exactly the wrong thing to leave unexercised.

**The order matters and it is sequential, not scored.** An earlier version
ranked candidates by rounding mAP into 0.005 buckets and latency into 1 ms
buckets and sorting on the tuple. That is not the same rule: two candidates
0.002 apart fall either side of a bucket edge roughly as often as not, so the
"within 0.005, prefer the faster one" clause silently became "in the same
0.005-wide bin, prefer the faster one" - and near an edge it picks a different
winner. :func:`choose_winner` filters in sequence instead, which is what the
protocol says.
"""

from __future__ import annotations

from dataclasses import dataclass

#: docs/12 P9. Two candidates closer than this in mAP are the same candidate as
#: far as accuracy goes, and the next criterion decides.
MAP_NOISE = 0.005

#: Likewise for p50 latency, in milliseconds.
LATENCY_NOISE_MS = 1.0


@dataclass(frozen=True)
class Candidate:
    """One scored export configuration, reduced to what the rule reads."""

    variant: str
    map50: float
    latency_ms: float | None
    #: How many settings differ from the shipped defaults - the protocol's
    #: "simpler" tie-break, made countable. See ``QuantSettings.departures``.
    departures: int
    #: False for anything that cannot be served, whatever it scores. fp16 is the
    #: case that matters: onnxruntime's CPU execution provider does not broadly
    #: support fp16 ops, so an fp16 row measures a configuration this service
    #: cannot run, and it is reported without being selectable.
    shippable: bool = True


def eligible(
    candidates: list[Candidate], reference_map50: float, max_drop: float
) -> list[Candidate]:
    """Those within ``max_drop`` of the reference, and actually servable.

    ``reference_map50`` must be the **PyTorch fp32** score on the same split.
    Using the fp32 *ONNX* score instead would let a lossy export lower the bar
    the candidates are judged against, which is the same failure the three-drop
    accounting exists to prevent - one split further up.
    """
    return [
        candidate for candidate in candidates
        if candidate.shippable and (reference_map50 - candidate.map50) <= max_drop
    ]


def choose_winner(
    candidates: list[Candidate],
    *,
    reference_map50: float,
    max_drop: float,
    map_noise: float = MAP_NOISE,
    latency_noise_ms: float = LATENCY_NOISE_MS,
) -> Candidate | None:
    """The protocol's tie-break, applied in order. ``None`` if nothing qualifies.

    1. eligible: within ``max_drop`` of the PyTorch fp32 reference;
    2. highest mAP, then everything within ``map_noise`` of it;
    3. lowest p50, then everything within ``latency_noise_ms`` of that;
    4. fewest departures from the default settings;
    5. the variant name, so a tie surviving all four is still deterministic.

    An unmeasured latency sorts last rather than first: a graph nobody timed has
    not earned the "and it is faster" tie-break.
    """
    shortlist = eligible(candidates, reference_map50, max_drop)
    if not shortlist:
        return None

    best_map = max(candidate.map50 for candidate in shortlist)
    shortlist = [c for c in shortlist if (best_map - c.map50) <= map_noise]

    timed = [c.latency_ms for c in shortlist if c.latency_ms is not None]
    if timed:
        best_latency = min(timed)
        shortlist = [
            c for c in shortlist
            if c.latency_ms is not None and (c.latency_ms - best_latency) <= latency_noise_ms
        ]

    return min(shortlist, key=lambda c: (c.departures, c.variant))
