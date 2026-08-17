"""The measuring instrument's own arithmetic.

`loadtest/run.py` is not in the container, but the concurrency figure in
docs/05 § 3, docs/07's gate and docs/11's table all come out of it, and a number
that decides a kill criterion deserves a test on the rule that produced it.

What is checked here is the *verdict*, not the load: whether a level counts as
passing, and how the levels compose into a ceiling. Those are the two places
where a plausible wrong answer was available and the earlier version took one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LOADTEST = Path(__file__).resolve().parents[1] / "loadtest"
sys.path.insert(0, str(LOADTEST))

from run import Level, monotonic_prefix, parse_args  # noqa: E402 - after the path insert

BUDGET = 250.0


def level(scanners: int, p95: float, *, errors: int = 0, repeat: int = 0) -> Level:
    entry = Level(scanners=scanners, repeat=repeat, errors=errors)
    entry.latencies_ms = [p95] * 20
    return entry


# --------------------------------------------------------------------------- #
# The verdict
# --------------------------------------------------------------------------- #


def test_the_verdict_stops_at_the_first_failure():
    """A level that scrapes under budget ABOVE a failed one is not capacity.

    The old rule kept the highest passing level, so a ramp that failed at 3 and
    passed at 4 reported 4 - which is noise wearing capacity's clothes, and it
    would have overstated the service in the direction the project most wants to
    be overstated.
    """
    ramp = [level(1, 100), level(2, 100), level(3, 300), level(4, 100)]
    assert monotonic_prefix([ramp], [1, 2, 3, 4], BUDGET) == 2


def test_a_level_must_pass_in_every_repeat():
    # The proxy host varied ~25 % between runs six minutes apart. One good ramp
    # is not evidence that a recovery is real.
    good = [level(1, 100), level(2, 100)]
    bad = [level(1, 100, repeat=1), level(2, 300, repeat=1)]
    assert monotonic_prefix([good, bad], [1, 2], BUDGET) == 1


def test_errors_fail_a_level_however_fast_it_was():
    # A ramp of timeouts has a beautiful p95 over the frames that came back.
    ramp = [level(1, 100), level(2, 100, errors=3)]
    assert monotonic_prefix([ramp], [1, 2], BUDGET) == 1


def test_a_level_a_repeat_never_reached_has_not_passed():
    # --stop-when-over cuts a ramp short. Absence is not a pass.
    assert monotonic_prefix([[level(1, 100)]], [1, 2], BUDGET) == 1


def test_no_verdict_when_even_one_scanner_misses():
    assert monotonic_prefix([[level(1, 900)]], [1], BUDGET) is None


def test_a_level_with_no_samples_at_all_does_not_pass():
    empty = Level(scanners=1)
    assert empty.passed is False
    assert monotonic_prefix([[empty]], [1], BUDGET) is None


# --------------------------------------------------------------------------- #
# The decomposition (docs/12 P8b)
# --------------------------------------------------------------------------- #


def test_a_frame_decomposes_into_four_buckets():
    entry = level(1, 120.0)
    entry.server_ms = [100.0] * 20
    entry.validator_ms = [30.0] * 20
    entry.identifier_ms = [20.0] * 20

    block = entry.decomposition()
    assert block["outside_pipeline_ms"] == pytest.approx(20.0)   # wall - server
    assert block["other_server_ms"] == pytest.approx(50.0)       # server - both graphs
    assert block["outside_pipeline_is"] == "network only"


def test_above_one_scanner_the_outside_bucket_says_what_it_really_holds():
    """It is not the network, and calling it transport_ms invited exactly that.

    The server's `ms` starts inside `Pipeline.run`, after the shedder has
    admitted the request and after it has taken the single inference slot. At
    twelve scanners this bucket was four seconds while the service reported 391
    ms, which reads as a catastrophic network problem and is a queue.
    """
    entry = level(12, 4600.0)
    entry.server_ms = [391.0] * 20
    block = entry.decomposition()
    assert "queueing for the inference slot" in block["outside_pipeline_is"]


def test_without_debug_only_the_free_half_is_reported():
    # `ms` rides on every reply; the per-graph split needs --debug. Reporting a
    # bucket that was not measured would be inventing evidence.
    entry = level(1, 120.0)
    entry.server_ms = [100.0] * 20
    block = entry.decomposition()
    assert "outside_pipeline_ms" in block
    assert "other_server_ms" not in block


def test_no_decomposition_at_all_when_nothing_was_collected():
    assert level(1, 120.0).decomposition() is None


# --------------------------------------------------------------------------- #
# The arguments that keep a report honest
# --------------------------------------------------------------------------- #


def test_the_default_levels_are_contiguous():
    """A ladder of 1 2 3 4 5 6 8 10 12 cannot see 6 -> 7.

    That is exactly the size of win docs/12 P8 is looking for, so the default
    has to be able to resolve it.
    """
    levels = parse_args([]).levels
    assert levels == list(range(1, 13))


def test_out_still_requires_naming_the_hardware():
    with pytest.raises(SystemExit):
        parse_args(["--out", "somewhere.json"])


def test_repeats_defaults_to_one_and_must_be_positive():
    assert parse_args([]).repeats == 1
    with pytest.raises(SystemExit):
        parse_args(["--repeats", "0"])
