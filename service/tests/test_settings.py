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


def test_the_threading_defaults_are_the_runtimes_own():
    """P8b's baseline has to be the runtime as it ships.

    A default of "spinning off" would make the probe measure a recovery against
    a configuration nobody was running, and the 15-40 ms it exists to explain
    was measured on the defaults.
    """
    settings = Settings.from_env()
    assert settings.ort_spinning is True
    assert settings.ort_shared_pool is False
    assert settings.identifier_threads is None
    assert settings.intra_op_threads == DEFAULT_INTRA_OP_THREADS


def test_spinning_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("SBR_ORT_SPINNING", "0")
    assert Settings.from_env().ort_spinning is False


def test_the_shared_pool_is_opt_in(monkeypatch):
    monkeypatch.setenv("SBR_ORT_SHARED_POOL", "1")
    assert Settings.from_env().ort_shared_pool is True


def test_the_identifier_can_be_given_its_own_thread_count(monkeypatch):
    monkeypatch.setenv("SBR_IDENTIFIER_THREADS", "1")
    assert Settings.from_env().identifier_threads == 1


# --------------------------------------------------------------------------- #
# The refusals
# --------------------------------------------------------------------------- #


def test_a_shared_pool_and_a_per_session_count_cannot_both_be_set(monkeypatch):
    # A shared pool has one size, so the per-session count would be ignored -
    # and the probe would report the effect of one change having made two.
    monkeypatch.setenv("SBR_ORT_SHARED_POOL", "1")
    monkeypatch.setenv("SBR_IDENTIFIER_THREADS", "1")
    with pytest.raises(ValueError, match="cannot both be set"):
        Settings.from_env()


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
