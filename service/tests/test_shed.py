"""The degradation ladder.

docs/05 § 3 gives three rungs and one prohibition. The rungs are easy to test.
The prohibition - *never a spinner that lies* - is the one worth writing tests
about, because it is a property of what the service **says**, and a service can
be perfectly correct and still leave a person staring at a spinner.
"""

from __future__ import annotations

from settings import ShedThresholds
from shed import CLIENT_MAX_FPS, SLOWED_FPS, LoadShedder, admitted

THRESHOLDS = ShedThresholds(slow=2, tap=4, queue=6)


def shedder() -> LoadShedder:
    return LoadShedder(THRESHOLDS, frame_cost_ms=100.0)


def fill(load: LoadShedder, depth: int) -> None:
    """Put `depth` requests in flight and leave them there."""
    for _ in range(depth):
        load.admit()


def test_an_idle_service_asks_for_nothing():
    verdict = shedder().admit()
    assert verdict.accept
    assert verdict.advice is None
    assert verdict.rung == "none"


def test_rung_one_serves_the_frame_and_asks_for_two_fps():
    """The frame is still answered. Nothing is refused until rung 3.

    A ladder whose first rung dropped requests would convert a busy service into
    a broken one, and the client would retry - which is how a busy free tier
    stays busy.
    """
    load = shedder()
    fill(load, THRESHOLDS.slow)
    verdict = load.admit()

    assert verdict.accept
    assert verdict.advice is not None
    assert verdict.advice.max_fps == SLOWED_FPS
    assert verdict.rung == "slow"


def test_rung_two_turns_streaming_off_without_turning_the_product_off():
    # "still works, still useful, visibly different" - docs/05 § 3.
    load = shedder()
    fill(load, THRESHOLDS.tap)
    verdict = load.admit()

    assert verdict.accept
    assert verdict.advice.max_fps == 0
    assert verdict.rung == "tap"


def test_rung_three_refuses_with_a_stated_wait():
    load = shedder()
    fill(load, THRESHOLDS.queue)
    verdict = load.admit()

    assert not verdict.accept
    assert verdict.retry_after_ms is not None and verdict.retry_after_ms > 0
    assert verdict.advice.queue_wait_ms == verdict.retry_after_ms


def test_the_stated_wait_is_derived_from_what_a_frame_actually_costs():
    """Not from a number in a document.

    A wait quoted from docs/05's 65 ms while the service is really taking 200 ms
    is a lie with a decimal point on it. The estimate is observed and the quote
    follows it.
    """
    load = shedder()
    for _ in range(60):
        load.observe(250.0)
    fill(load, THRESHOLDS.queue)

    verdict = load.admit()
    assert verdict.retry_after_ms > THRESHOLDS.queue * 200


def test_the_service_may_lower_a_clients_cadence_and_never_raise_it():
    """A gate a server could switch off is not a gate.

    docs/05 § 3 calls the client-side gates load-bearing infrastructure: without
    them one user on a fast connection consumes a third of total capacity. Advice
    that could raise the cap would be a remote off switch for that.
    """
    load = shedder()
    for depth in range(THRESHOLDS.queue):
        fill(load, 1)
        verdict = load.admit()
        if verdict.advice is not None:
            assert verdict.advice.max_fps < CLIENT_MAX_FPS, depth


def test_depth_falls_when_work_completes():
    load = shedder()
    with admitted(load) as verdict:
        assert verdict.accept
        assert load.depth == 1
    assert load.depth == 0


def test_a_failed_frame_still_releases_its_slot():
    """Otherwise one bad JPEG permanently costs a slot, and enough of them
    saturate a service that is doing no work at all."""
    load = shedder()
    try:
        with admitted(load):
            raise ValueError("undecodable frame")
    except ValueError:
        pass
    assert load.depth == 0


def test_a_refused_request_never_took_a_slot():
    load = shedder()
    fill(load, THRESHOLDS.queue)
    before = load.depth
    with admitted(load) as verdict:
        assert not verdict.accept
    assert load.depth == before


def test_a_refusal_always_states_a_positive_wait():
    """Even when the queue threshold is zero.

    "Retry after 0 ms" is not a stated wait, it is an invitation for every client
    that was just refused to come back at once - which is how a service under
    load converts a queue into a stampede.
    """
    load = LoadShedder(ShedThresholds(slow=0, tap=0, queue=0), frame_cost_ms=65.0)
    verdict = load.admit()
    assert not verdict.accept
    assert verdict.retry_after_ms >= 65


def test_shed_requests_are_counted_for_the_load_test_to_read():
    load = shedder()
    fill(load, THRESHOLDS.queue)
    load.admit()
    assert load.stats()["shed"] == 1
    assert load.stats()["peak_depth"] == THRESHOLDS.queue
