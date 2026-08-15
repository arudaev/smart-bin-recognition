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


# --------------------------------------------------------------------------- #
# Token resolution
# --------------------------------------------------------------------------- #


def test_a_token_is_found_wherever_kaggle_mounts_the_dataset(tmp_path, monkeypatch):
    """Kaggle moved the mount point and the resolver did not know.

    It mounts attached datasets under ``/kaggle/input/datasets/<owner>/<slug>/``
    now, not ``/kaggle/input/<slug>/``. Two hard-coded paths found nothing, and a
    harvest that had already spent 35 minutes died with nowhere to put its work.
    """
    deep = tmp_path / "datasets" / "hlexnc" / "chexvision-secrets"
    deep.mkdir(parents=True)
    (deep / "hf_token.txt").write_text("hf_deadbeef\n", encoding="utf-8")

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(hub, "KAGGLE_SECRET_PATHS", ())
    monkeypatch.setattr(hub, "KAGGLE_INPUT", tmp_path)
    assert hub.load_hf_token() == "hf_deadbeef"


def test_the_environment_still_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_from_env")
    monkeypatch.setattr(hub, "KAGGLE_INPUT", tmp_path)
    assert hub.load_hf_token() == "hf_from_env"


def test_a_missing_token_reports_what_was_actually_mounted(tmp_path, monkeypatch, caplog):
    # "no Hugging Face token found" on its own does not say where to look.
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "something-else.csv").write_text("x", encoding="utf-8")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(hub, "KAGGLE_SECRET_PATHS", ())
    monkeypatch.setattr(hub, "KAGGLE_INPUT", tmp_path)

    hub.load_hf_token()
    assert "something-else.csv" in caplog.text


def test_require_hf_token_stops_before_the_expensive_work(monkeypatch):
    # The whole point: fail in a second, not after a 2.2 GB stream and 18 609
    # image fetches, or a GPU hour.
    monkeypatch.setattr(hub, "load_hf_token", lambda: None)
    with pytest.raises(SystemExit, match="would\n?\\s*have spent its whole budget"):
        hub.require_hf_token("push the harvested pools")


def test_require_hf_token_returns_the_token_when_there_is_one(monkeypatch):
    monkeypatch.setattr(hub, "load_hf_token", lambda: "hf_ok")
    assert hub.require_hf_token() == "hf_ok"
