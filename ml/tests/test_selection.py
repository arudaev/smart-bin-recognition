"""Tests for docs/12 P9's winner rule.

The rule decides which export configuration reaches the ship gate, so it is
exactly the wrong thing to leave untested - and it *was* untested, because the
first version lived inside a Kaggle kernel, which cannot be imported.

Two defects are pinned here, both of which would have chosen a different winner
than the protocol says:

- **the reference was the fp32 ONNX score, not the PyTorch one.** The protocol
  names PyTorch fp32 because a lossy ONNX export would otherwise lower the bar
  every candidate is measured against;
- **the tie-break rounded into buckets instead of filtering in sequence.**
  "Within 0.005 of the best" and "in the same 0.005-wide bin as the best" agree
  most of the time and disagree near an edge, which is the worst possible
  failure mode: right in testing, wrong in production.
"""

from __future__ import annotations

from sbr.export.selection import Candidate, choose_winner, eligible

REFERENCE = 0.7524389678079388   # PyTorch fp32, the frozen v1 number
MAX_DROP = 0.02


def candidate(variant, map50, latency_ms=30.0, departures=1, shippable=True):
    return Candidate(
        variant=variant, map50=map50, latency_ms=latency_ms,
        departures=departures, shippable=shippable,
    )


# --------------------------------------------------------------------------- #
# Eligibility
# --------------------------------------------------------------------------- #


def test_only_candidates_within_the_budget_are_eligible():
    candidates = [
        candidate("just-inside", REFERENCE - 0.019),
        candidate("just-outside", REFERENCE - 0.021),
        candidate("collapsed", 0.025),
    ]
    assert [c.variant for c in eligible(candidates, REFERENCE, MAX_DROP)] == ["just-inside"]


def test_nothing_eligible_means_no_winner_and_no_test_evaluation():
    """The point of holding `test` back: if nothing qualifies there is nothing
    to confirm, and the split stays untouched."""
    candidates = [candidate("a", 0.10), candidate("b", 0.20)]
    assert choose_winner(candidates, reference_map50=REFERENCE, max_drop=MAX_DROP) is None


def test_an_unshippable_candidate_is_never_selected_however_well_it_scores():
    # fp16 is the case: onnxruntime's CPU execution provider does not broadly
    # support fp16, so the row is reported and cannot be chosen.
    candidates = [
        candidate("fp16", REFERENCE, latency_ms=5.0, departures=0, shippable=False),
        candidate("int8", REFERENCE - 0.01),
    ]
    winner = choose_winner(candidates, reference_map50=REFERENCE, max_drop=MAX_DROP)
    assert winner is not None and winner.variant == "int8"


def test_the_reference_is_the_pytorch_score_not_a_re_derived_one():
    """A lossy fp32 export must not lower the bar its own candidates are judged against.

    Same candidate, two references: against the frozen PyTorch number it misses,
    against a degraded fp32 ONNX score it would pass. The rule reads the former.
    """
    lossy_onnx_reference = 0.70
    contender = candidate("borderline", 0.69)

    assert choose_winner([contender], reference_map50=REFERENCE, max_drop=MAX_DROP) is None
    assert choose_winner(
        [contender], reference_map50=lossy_onnx_reference, max_drop=MAX_DROP
    ) is not None


# --------------------------------------------------------------------------- #
# The tie-break, in sequence
# --------------------------------------------------------------------------- #


def test_the_highest_map_wins_when_the_gap_is_real():
    candidates = [
        candidate("better", REFERENCE - 0.001, latency_ms=40.0),
        candidate("faster-but-worse", REFERENCE - 0.015, latency_ms=20.0),
    ]
    winner = choose_winner(candidates, reference_map50=REFERENCE, max_drop=MAX_DROP)
    assert winner.variant == "better"


def test_within_the_map_noise_the_faster_graph_wins():
    candidates = [
        candidate("slow", REFERENCE - 0.001, latency_ms=40.0),
        candidate("quick", REFERENCE - 0.004, latency_ms=20.0),   # 0.003 apart
    ]
    winner = choose_winner(candidates, reference_map50=REFERENCE, max_drop=MAX_DROP)
    assert winner.variant == "quick"


def test_within_both_noise_floors_the_simpler_configuration_wins():
    candidates = [
        candidate("exotic", REFERENCE - 0.001, latency_ms=30.0, departures=4),
        candidate("plain", REFERENCE - 0.002, latency_ms=30.5, departures=1),
    ]
    winner = choose_winner(candidates, reference_map50=REFERENCE, max_drop=MAX_DROP)
    assert winner.variant == "plain"


def test_a_tie_surviving_every_criterion_is_still_deterministic():
    candidates = [
        candidate("b-variant", REFERENCE - 0.001, latency_ms=30.0, departures=1),
        candidate("a-variant", REFERENCE - 0.001, latency_ms=30.0, departures=1),
    ]
    winner = choose_winner(candidates, reference_map50=REFERENCE, max_drop=MAX_DROP)
    assert winner.variant == "a-variant"


def test_an_untimed_candidate_does_not_win_the_latency_tie_break():
    # A graph nobody timed has not earned "and it is faster".
    candidates = [
        candidate("untimed", REFERENCE - 0.001, latency_ms=None),
        candidate("timed", REFERENCE - 0.002, latency_ms=25.0),
    ]
    winner = choose_winner(candidates, reference_map50=REFERENCE, max_drop=MAX_DROP)
    assert winner.variant == "timed"


# --------------------------------------------------------------------------- #
# The bucket-boundary case, which is the whole reason this is sequential
# --------------------------------------------------------------------------- #


def test_sequential_filtering_beats_bucketing_at_a_boundary():
    """Two candidates 0.002 apart, straddling a 0.005 bucket edge.

    The rounding implementation put 0.7024 in bucket 140 and 0.7044 in bucket
    141, declared them different on accuracy, and returned the slower one
    without ever consulting latency. They are 0.002 apart - inside the stated
    noise floor - so the protocol says the faster one wins.
    """
    slow = candidate("slow", 0.7044, latency_ms=45.0)
    quick = candidate("quick", 0.7024, latency_ms=25.0)

    winner = choose_winner(
        [slow, quick], reference_map50=0.7124, max_drop=MAX_DROP
    )
    assert winner.variant == "quick", "0.002 apart is within the 0.005 noise floor"

    # And the rule the old code actually implemented, for contrast: bucketing
    # separates them and latency is never reached.
    bucketed = min(
        [slow, quick],
        key=lambda c: (-round(c.map50 / 0.005), round(c.latency_ms / 1.0), c.variant),
    )
    assert bucketed.variant == "slow", (
        "if this ever equals 'quick' the boundary case has moved and this test "
        "has stopped demonstrating the difference it exists to demonstrate"
    )
