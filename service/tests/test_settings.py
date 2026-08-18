"""The environment, and the two refusals in it.

``settings.py`` is where a container's configuration is read, so it is also
where a configuration that would produce a misleading measurement has to be
refused. Two of those live here: forcing crops without the ungated flag, which
would let a service invent bins, and combining a shared thread pool with a
per-session thread count, which would move two variables while docs/12 probe
P8b measures one.
"""

from __future__ import annotations

import os

import pytest

from settings import DEFAULT_INTRA_OP_THREADS, Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No SBR_ variable survives from the ambient shell into a test.

    Otherwise a developer who exported SBR_MAX_CROPS to run the load test gets a
    different suite from CI, which is the kind of difference that is only ever
    noticed once it has cost an afternoon.
    """
    for name in list(os.environ):
        if name.startswith("SBR_"):
            monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------- #
# Defaults are onnxruntime's own
# --------------------------------------------------------------------------- #


def test_the_shared_thread_pool_defaults_to_deciding_at_load_time():
    """The one recovery of P8's three that survived measurement - conditionally.

    Two sessions on two cores get two intra-op pools and both spin, so the idle
    model burns the running model's cycles: switching measured +36.9 ms and one
    shared pool removed it. But the same experiment measured the other side, and
    with ONE hot session sharing cost 29.6 -> 33.0 ms. The service is
    single-session today, so an unconditional default would take a measured 11 %
    regression now for a benefit that arrives with the identifier.

    ``None`` means "decide from how many graphs actually load", and `app._load`
    is where that is decided - it has to be, because onnxruntime's global pools
    cannot be created after the first session that opts out of per-session
    threads.
    """
    settings = Settings.from_env()
    assert settings.ort_shared_pool is None
    assert settings.ort_spinning is True
    assert settings.identifier_threads is None
    assert settings.intra_op_threads == DEFAULT_INTRA_OP_THREADS


def test_the_shared_pool_can_be_forced_on(monkeypatch):
    # The x86 confirmation run needs to measure both settings deliberately.
    monkeypatch.setenv("SBR_ORT_SHARED_POOL", "1")
    assert Settings.from_env().ort_shared_pool is True


def test_the_shared_pool_can_be_turned_off_again(monkeypatch):
    # It was measured on arm64, and an x86 host may yet disagree. A recovery
    # with no way back is not a recovery, it is a commitment.
    monkeypatch.setenv("SBR_ORT_SHARED_POOL", "0")
    assert Settings.from_env().ort_shared_pool is False


def test_spinning_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("SBR_ORT_SPINNING", "0")
    assert Settings.from_env().ort_spinning is False


def test_the_identifier_can_be_given_its_own_thread_count(monkeypatch):
    monkeypatch.setenv("SBR_IDENTIFIER_THREADS", "1")
    assert Settings.from_env().identifier_threads == 1


# --------------------------------------------------------------------------- #
# The refusals
# --------------------------------------------------------------------------- #


def test_forcing_the_shared_pool_and_a_per_session_count_is_refused(monkeypatch):
    """It would be ignored, not applied, and the refusal names the way out.

    Only when the pool is forced ON. Left to decide for itself, a per-session
    thread count is a perfectly coherent request and simply implies per-session
    pools - which is what `app._load` does with it.
    """
    monkeypatch.setenv("SBR_ORT_SHARED_POOL", "1")
    monkeypatch.setenv("SBR_IDENTIFIER_THREADS", "1")
    with pytest.raises(ValueError, match="SBR_ORT_SHARED_POOL=0"):
        Settings.from_env()


def test_a_per_session_count_alone_is_allowed(monkeypatch):
    # No conflict: it just means the pools stay per-session.
    monkeypatch.setenv("SBR_IDENTIFIER_THREADS", "1")
    settings = Settings.from_env()
    assert settings.identifier_threads == 1
    assert settings.ort_shared_pool is None


def test_forcing_crops_without_the_ungated_flag_is_refused(monkeypatch):
    monkeypatch.setenv("SBR_FORCE_CROPS", "6")
    with pytest.raises(ValueError, match="SBR_ALLOW_UNGATED"):
        Settings.from_env()


def test_forcing_crops_is_allowed_once_ungated_is_explicit(monkeypatch):
    monkeypatch.setenv("SBR_FORCE_CROPS", "6")
    monkeypatch.setenv("SBR_ALLOW_UNGATED", "1")
    settings = Settings.from_env()
    assert settings.force_crops == 6
    assert settings.allow_ungated is True


# --------------------------------------------------------------------------- #
# What /health has to say
# --------------------------------------------------------------------------- #


def test_health_reports_every_knob_that_changes_a_measurement(monkeypatch):
    """A load-test report records /health verbatim beside its numbers.

    Any knob that changes what a millisecond means has to be in there, or a JSON
    file outlives the terminal it was run in and nobody can tell afterwards which
    configuration produced it.
    """
    monkeypatch.setenv("SBR_ORT_SPINNING", "0")
    monkeypatch.setenv("SBR_MAX_CROPS", "3")
    reported = Settings.from_env().as_dict()

    for key in (
        "intra_op_threads",
        "identifier_threads",
        "ort_spinning",
        "ort_shared_pool",
        "inference_slots",
        "max_crops",
        "force_crops",
        "allow_ungated",
    ):
        assert key in reported, f"/health does not report {key}"
    assert reported["ort_spinning"] is False
    assert reported["max_crops"] == 3
