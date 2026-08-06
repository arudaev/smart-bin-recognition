"""Tests for revision pinning.

The predecessor's central artefact could not reproduce its own model. The
mechanism that prevents a repeat is boring and easy to bypass by accident, so
it is tested: a run that will be quoted must not silently read whatever ``main``
happens to point at today.
"""

from __future__ import annotations

import pytest

from sbr.utils import hub
from sbr.utils.hub import PINS, UnpinnedRevisionError, resolve_revision

SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def pinned(monkeypatch):
    monkeypatch.setitem(hub.PINS, "arudaev/smart-bin-detect", SHA)


def test_an_explicit_sha_always_wins(pinned):
    other = "f" * 40
    assert resolve_revision("arudaev/smart-bin-detect", other, strict=True) == other


def test_main_resolves_to_the_pin(pinned):
    assert resolve_revision("arudaev/smart-bin-detect", "main", strict=True) == SHA


def test_strict_run_against_an_unpinned_repo_is_an_error():
    with pytest.raises(UnpinnedRevisionError, match="no pinned revision"):
        resolve_revision("arudaev/smart-bin-identify", "main", strict=True)


def test_lenient_run_against_an_unpinned_repo_warns_and_uses_main(caplog):
    assert resolve_revision("arudaev/smart-bin-identify", "main") == "main"
    assert "unpinned" in caplog.text


def test_every_dataset_this_repo_trains_on_has_a_pin_slot():
    # A repo missing from PINS resolves to 'main' even under strict, because
    # dict.get returns "". The slot existing is what makes strict meaningful.
    assert {
        "arudaev/smart-bin-detect",
        "arudaev/smart-bin-identify",
    } <= set(PINS)


def test_an_unknown_repo_is_still_an_error_under_strict():
    with pytest.raises(UnpinnedRevisionError):
        resolve_revision("someone/else", "main", strict=True)
