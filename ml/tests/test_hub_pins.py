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


# --------------------------------------------------------------------------- #
# Uploading many files
# --------------------------------------------------------------------------- #


def test_a_big_folder_uses_the_resumable_uploader(tmp_path, monkeypatch):
    """Pre-signed LFS URLs expire after 900 s.

    upload_folder asks for the whole batch up front, so 18 609 harvested images
    over a Kaggle connection died sixteen minutes in with "Request has expired",
    which the Hub reports as a 403 about token permissions.
    """
    for index in range(hub.LARGE_UPLOAD_FILES + 1):
        (tmp_path / f"{index}.jpg").write_bytes(b"x")

    calls = []

    class FakeApi:
        def create_repo(self, **kwargs):
            pass

        def upload_folder(self, **kwargs):
            calls.append("upload_folder")
            raise AssertionError("must not be used for a folder this size")

        def upload_large_folder(self, **kwargs):
            calls.append("upload_large_folder")

        def dataset_info(self, *args, **kwargs):
            return type("Info", (), {"sha": "abc123"})()

    monkeypatch.setattr(hub, "load_hf_token", lambda: "hf_x")
    monkeypatch.setattr(hub, "configure_hf_runtime", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "huggingface_hub",
                        type("M", (), {"HfApi": lambda **kw: FakeApi()}))

    assert hub.upload_dataset("owner/repo", tmp_path, "msg") == "abc123"
    assert calls == ["upload_large_folder"]


def test_a_small_folder_uses_a_single_commit(tmp_path, monkeypatch):
    # One commit is nicer when it fits: it yields a real sha directly.
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    calls = []

    class FakeApi:
        def create_repo(self, **kwargs):
            pass

        def upload_folder(self, **kwargs):
            calls.append("upload_folder")
            return type("Commit", (), {"oid": "deadbeef"})()

        def upload_large_folder(self, **kwargs):
            raise AssertionError("not needed for one file")

        def dataset_info(self, *args, **kwargs):
            return type("Info", (), {"sha": "unused"})()

    monkeypatch.setattr(hub, "load_hf_token", lambda: "hf_x")
    monkeypatch.setattr(hub, "configure_hf_runtime", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "huggingface_hub",
                        type("M", (), {"HfApi": lambda **kw: FakeApi()}))

    assert hub.upload_dataset("owner/repo", tmp_path, "msg") == "deadbeef"
    assert calls == ["upload_folder"]


# --------------------------------------------------------------------------- #
# The preflight
# --------------------------------------------------------------------------- #


def test_the_cap_is_the_hubs_cap():
    # Not a tunable. The Hub's message is "up to 10000 files" per directory.
    from sbr.dataset.pool import MAX_FILES_PER_DIR

    assert MAX_FILES_PER_DIR == 10_000


def test_an_oversized_directory_is_refused_and_named(tmp_path, monkeypatch):
    # The failure this exists to move earlier: the first negatives harvest spent
    # thirty minutes downloading and then learned this from the Hub, mid-upload.
    monkeypatch.setattr("sbr.dataset.pool.MAX_FILES_PER_DIR", 3)
    labels = tmp_path / "negatives" / "labels"
    labels.mkdir(parents=True)
    for i in range(4):
        (labels / f"{i}.txt").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="negatives.labels"):
        hub.preflight_layout(tmp_path)


def test_the_preflight_passes_at_the_cap(tmp_path, monkeypatch):
    # Off-by-one matters: the Hub's message says "up to 10000", not "under".
    monkeypatch.setattr("sbr.dataset.pool.MAX_FILES_PER_DIR", 3)
    for i in range(3):
        (tmp_path / f"{i}.txt").write_text("", encoding="utf-8")
    hub.preflight_layout(tmp_path)


def test_a_sharded_tree_passes_the_preflight(tmp_path, monkeypatch):
    from sbr.dataset.pool import SHARDED, image_path

    monkeypatch.setattr("sbr.dataset.pool.MAX_FILES_PER_DIR", 3)
    for i in range(20):
        target = image_path(tmp_path, f"{i:04x}.jpg", SHARDED)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")
    hub.preflight_layout(tmp_path)


def test_upload_refuses_a_tree_the_hub_would_reject(tmp_path, monkeypatch):
    monkeypatch.setattr("sbr.dataset.pool.MAX_FILES_PER_DIR", 2)
    for i in range(3):
        (tmp_path / f"{i}.txt").write_text("", encoding="utf-8")
    monkeypatch.setattr(hub, "load_hf_token", lambda: "hf_x")
    monkeypatch.setattr(hub, "configure_hf_runtime", lambda: None)

    # Before create_repo, so a refused push leaves nothing behind.
    class FakeApi:
        def create_repo(self, **kwargs):
            raise AssertionError("the preflight must run first")

    monkeypatch.setitem(__import__("sys").modules, "huggingface_hub",
                        type("M", (), {"HfApi": lambda **kw: FakeApi()}))
    with pytest.raises(ValueError, match="10000|files per directory|more than"):
        hub.upload_dataset("owner/repo", tmp_path, "msg")


# --------------------------------------------------------------------------- #
# Deleting, and not pretending it worked
# --------------------------------------------------------------------------- #


def _fake_hub(monkeypatch, api):
    monkeypatch.setattr(hub, "load_hf_token", lambda: "hf_x")
    monkeypatch.setattr(hub, "configure_hf_runtime", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "huggingface_hub",
                        type("M", (), {"HfApi": lambda **kw: api}))


def _http_error(status: int):
    """An error shaped like the Hub's, without naming a class that moves."""
    error = RuntimeError(f"HTTP {status}")
    error.response = type("R", (), {"status_code": status})()
    return error


def test_deleting_an_absent_subset_is_fine(monkeypatch):
    # The ordinary case: a first push, or a subset that was never written.
    class FakeApi:
        def delete_folder(self, **kwargs):
            raise _http_error(404)

    _fake_hub(monkeypatch, FakeApi())
    hub.delete_subsets("owner/repo", ["negatives"])


def test_a_delete_that_fails_stops_the_run(monkeypatch):
    # The failure that let run 5 upload onto a tree it had not cleared: a 429
    # swallowed and logged looks exactly like "there was nothing there".
    class FakeApi:
        def delete_folder(self, **kwargs):
            raise _http_error(429)

    _fake_hub(monkeypatch, FakeApi())
    with pytest.raises(RuntimeError, match="API quota|could not delete"):
        hub.delete_subsets("owner/repo", ["negatives"])


def test_upload_can_skip_repo_creation(tmp_path, monkeypatch):
    # An unattended run makes every Hub call it can BEFORE the harvest. After
    # sixteen minutes of downloading, create_repo is a one-shot way to lose all
    # of it - which is precisely how the second negatives run ended.
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")

    class FakeApi:
        def create_repo(self, **kwargs):
            raise AssertionError("create=False must not touch the repo endpoint")

        def upload_folder(self, **kwargs):
            return type("Commit", (), {"oid": "deadbeef"})()

    _fake_hub(monkeypatch, FakeApi())
    assert hub.upload_dataset("owner/repo", tmp_path, "msg", create=False) == "deadbeef"


def test_ensure_repo_creates_it_up_front(monkeypatch):
    seen = []

    class FakeApi:
        def create_repo(self, **kwargs):
            seen.append(kwargs)

    _fake_hub(monkeypatch, FakeApi())
    hub.ensure_repo("owner/repo", private=True)
    assert seen == [{"repo_id": "owner/repo", "repo_type": "dataset",
                     "private": True, "exist_ok": True}]


# --------------------------------------------------------------------------- #
# Where we are, and where the token lives
# --------------------------------------------------------------------------- #


def test_kaggle_is_detected_by_its_environment_not_by_a_path(monkeypatch):
    r"""``Path("/kaggle")`` is drive-relative on Windows and resolves to C:\kaggle.

    This returned True on a developer laptop, and the bug was self-perpetuating:
    ``configure_hf_runtime`` believed it, pointed HF_HOME at
    ``/kaggle/working/hf_home``, and created the directory the next call would
    detect. The symptom surfaced somewhere else entirely - ``.env`` was never
    read, so a local upload failed with "cannot upload without a Hugging Face
    token" beside a file that contained one.
    """
    monkeypatch.delenv("KAGGLE_KERNEL_RUN_TYPE", raising=False)
    monkeypatch.delenv("KAGGLE_URL_BASE", raising=False)
    monkeypatch.setattr(hub.os, "name", "nt")
    monkeypatch.setattr(hub.Path, "is_dir", lambda self: True)
    assert hub.on_kaggle() is False

    monkeypatch.setenv("KAGGLE_KERNEL_RUN_TYPE", "Batch")
    assert hub.on_kaggle() is True


def test_a_posix_kernel_with_a_stripped_environment_still_counts(monkeypatch):
    monkeypatch.delenv("KAGGLE_KERNEL_RUN_TYPE", raising=False)
    monkeypatch.delenv("KAGGLE_URL_BASE", raising=False)
    monkeypatch.setattr(hub.os, "name", "posix")
    monkeypatch.setattr(hub.Path, "is_dir", lambda self: True)
    assert hub.on_kaggle() is True


def test_the_token_is_read_from_the_repo_dotenv(tmp_path, monkeypatch):
    """AGENTS.md says tokens live in .env at the repo root. Act on it.

    Only dispatch.py did, in two private copies, so every other local entry
    point - push_dataset.py among them - refused to work against a file that
    had the token in it.
    """
    (tmp_path / ".env").write_text("HF_TOKEN=hf_from_dotenv\n", encoding="utf-8")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(hub, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hub, "KAGGLE_SECRET_PATHS", ())
    monkeypatch.setattr(hub, "KAGGLE_INPUT", tmp_path / "absent")
    monkeypatch.setattr(hub, "on_kaggle", lambda: False)

    assert hub.load_hf_token() == "hf_from_dotenv"


def test_an_exported_token_beats_the_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("HF_TOKEN=hf_from_dotenv\n", encoding="utf-8")
    monkeypatch.setenv("HF_TOKEN", "hf_exported")
    monkeypatch.setattr(hub, "REPO_ROOT", tmp_path)
    assert hub.load_hf_token() == "hf_exported"
