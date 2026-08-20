"""The refusal.

An ungated model reaching users is the failure the whole gate apparatus in
``ml/`` exists to prevent. Every other test in this repo checks that gates are
*computed* correctly; these check that the answer is *obeyed* - which is the half
that was missing, because until ``service/`` existed there was nothing on the
other end of the verdict.
"""

from __future__ import annotations

import pytest

from artefacts import ArtefactMissingError, UngatedArtefactError, load_artefact
from settings import Settings


def _settings(directory, **overrides) -> Settings:
    return Settings(artefact_dir=directory, **overrides)


def test_an_artefact_that_may_not_ship_is_refused(artefact_dir):
    directory = artefact_dir("validator", may_ship=False)
    with pytest.raises(UngatedArtefactError) as raised:
        load_artefact("validator", _settings(directory))

    # The message has to name what failed. An operator reading a 503 at 3 a.m.
    # needs the gate, not the fact that there was one.
    assert "exceeds the 50 ms budget" in str(raised.value)


def test_the_refusal_happens_before_the_graph_is_opened(artefact_dir):
    """A gate that ran after loading would be a gate that had already lost.

    The .onnx files this fixture writes are empty, so onnxruntime would raise if
    it were ever reached. UngatedArtefactError rather than an onnxruntime error
    is the proof that it is not.
    """
    directory = artefact_dir("validator", may_ship=False)
    with pytest.raises(UngatedArtefactError):
        load_artefact("validator", _settings(directory))


def test_an_unmeasured_gate_is_also_a_refusal(artefact_dir):
    # GateResult distinguishes measured-and-over-budget from not-yet-judgeable,
    # and neither is permission to ship. Only may_ship is.
    directory = artefact_dir(
        "validator",
        may_ship=False,
        gate_result={
            "failures": [],
            "unmeasured": ["median latency has not been measured on the service CPU"],
            "may_ship": False,
        },
    )
    with pytest.raises(UngatedArtefactError) as raised:
        load_artefact("validator", _settings(directory))
    assert "has not been measured" in str(raised.value)


def test_a_sidecar_with_no_verdict_at_all_is_refused(artefact_dir):
    # Absence is not consent. A sidecar predating the gates, or one truncated in
    # transit, must not read as permission.
    directory = artefact_dir("validator", may_ship=True, gate_result=None)
    with pytest.raises(UngatedArtefactError):
        load_artefact("validator", _settings(directory))


def test_the_override_exists_and_announces_itself(artefact_dir, caplog):
    """SBR_ALLOW_UNGATED is how latency and concurrency get measured before a
    model is trained. It must be loud, and it must mark the artefact."""
    directory = artefact_dir("validator", may_ship=False)
    with pytest.raises(Exception) as raised:  # noqa: B017 - onnxruntime on an empty file
        load_artefact("validator", _settings(directory, allow_ungated=True))

    # It got past the gate - the failure is now the empty graph, not the verdict.
    assert not isinstance(raised.value, UngatedArtefactError)
    assert any("SERVING AN UNGATED ARTEFACT" in record.message for record in caplog.records)


def test_a_missing_artefact_is_not_an_ungated_one(artefact_dir):
    """The distinction the service runs on today.

    "There is no identifier yet" is an expected state - it is blocked on the
    human adjudication pass - and the service answers where a bin is without it.
    "There is an identifier and it failed its gates" must never be silently the
    same thing.
    """
    directory = artefact_dir("validator")
    with pytest.raises(ArtefactMissingError):
        load_artefact("identifier", _settings(directory))


def test_a_second_session_does_not_die_on_the_global_thread_pool(monkeypatch):
    """onnxruntime's global pools cannot be replaced, and this service opens two.

    The first implementation called ``set_global_thread_pool_sizes`` per session,
    so ``SBR_ORT_SHARED_POOL=1`` opened the validator and then took the process
    down on the identifier with ``FAIL: Global thread pools have already been
    created``. Invisible to every test that opens one session - which was all of
    them - and found by running it in the container.
    """
    import artefacts

    calls: list[tuple[int, int]] = []

    class FakeOrt:
        __version__ = "1.28.0"

        @staticmethod
        def set_global_thread_pool_sizes(intra: int, inter: int) -> None:
            if calls:
                raise RuntimeError("Global thread pools have already been created")
            calls.append((intra, inter))

    monkeypatch.setattr(artefacts, "_GLOBAL_POOL", None)
    assert artefacts._use_global_pool(FakeOrt, 2) is True
    assert artefacts._use_global_pool(FakeOrt, 2) is True   # the identifier
    assert calls == [(2, 1)], "the pool must be created exactly once per process"


def test_an_old_runtime_falls_back_and_says_so(monkeypatch, caplog):
    # Silently measuring the default configuration while the report says
    # "shared_pool" is the one outcome worse than not measuring at all.
    import artefacts

    class Ancient:
        __version__ = "1.18.0"

    monkeypatch.setattr(artefacts, "_GLOBAL_POOL", None)
    assert artefacts._use_global_pool(Ancient, 2) is False
    assert "falling back to per-session pools" in caplog.text


def test_an_unknown_role_is_rejected_before_any_io(artefact_dir):
    with pytest.raises(ValueError, match="unknown model role"):
        load_artefact("detector", _settings(artefact_dir("validator")))


# --------------------------------------------------------------------------- #
# One thread pool or two - decided before anything is opened
# --------------------------------------------------------------------------- #


def test_the_existence_probe_does_not_open_a_session(artefact_dir):
    """It has to answer before the first session, so it cannot use one.

    onnxruntime's global thread pools cannot be created after the first session
    that opts out of per-session threads, so "will there be two graphs" must be
    answered from the sidecars alone. The .onnx files this fixture writes are
    empty, so anything that opened one would raise rather than return.
    """
    from artefacts import artefact_exists

    directory = artefact_dir("validator")
    assert artefact_exists("validator", _settings(directory)) is True
    assert artefact_exists("identifier", _settings(directory)) is False


def test_an_ungated_artefact_still_counts_as_existing(artefact_dir):
    # The pool decision is about how many graphs get opened, not about whether
    # they are allowed to serve. Conflating the two would silently change the
    # threading of every ungated measurement run.
    from artefacts import artefact_exists

    directory = artefact_dir("validator", may_ship=False)
    assert artefact_exists("validator", _settings(directory)) is True
