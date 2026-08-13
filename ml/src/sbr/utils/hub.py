"""Hugging Face Hub helpers: token resolution, dataset download, artefact upload.

Token resolution order mirrors CheXVision, because the same Kaggle dispatch
mechanism is used and the same failure modes apply:

1. ``HF_TOKEN`` in the environment (local, and injected by CI).
2. A private Kaggle dataset mounted at ``/kaggle/input/<secrets>/hf_token.txt``.
   This is the reliable path for API-pushed kernels.
3. ``UserSecretsClient`` – works only in interactive Kaggle sessions.

**Revisions are pinned here** (docs/04-ml-pipeline.md § 5). ``main`` moves; a
number measured against a moving target cannot be reproduced, and this project's
whole complaint about its predecessor is that its headline number could not be
reproduced from its own artefacts. :data:`PINS` is the record, and
``download_dataset(..., strict=True)`` refuses to run without one.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

KAGGLE_SECRET_PATHS = (
    Path("/kaggle/input/sbr-secrets/hf_token.txt"),
    Path("/kaggle/input/chexvision-secrets/hf_token.txt"),  # shared secrets dataset
)

#: Dataset revision each repo is pinned to. Filled in by
#: ``ml/scripts/push_dataset.py``, which prints the sha after an upload; an empty
#: string means "never pushed", and a strict run against it is an error rather
#: than a silent fall back to ``main``.
#:
#: Changing a pin means the next training run sees different data. That is a
#: deliberate act and belongs in its own commit, with the reason in the message.
PINS: dict[str, str] = {
    # legacy subset only: 370 usable frames, 403 boxes, one city, one week.
    # Pushed 2026-08-13 from cv_garbage.zip sha256 028b1f55…96ea3.
    "arudaev/smart-bin-detect": "581eedae78c69fbaa02c2db77687d030e309b5ed",
    # Needs the human pass first - there are no adjudicated crops yet.
    "arudaev/smart-bin-identify": "",
    "arudaev/smart-bin-raw": "",
}


class UnpinnedRevisionError(RuntimeError):
    """Raised when a run that will be quoted asks for an unpinned revision."""


def resolve_revision(repo_id: str, requested: str = "main", strict: bool = False) -> str:
    """Turn a config's ``data.revision`` into the revision actually used.

    ``main`` is not a revision, it is a promise to change. When a specific sha is
    requested it wins; otherwise the pin does; and under ``strict`` the absence
    of a pin is an error, because the alternative is quoting a number nobody can
    reproduce.
    """
    if requested and requested != "main":
        return requested

    pinned = PINS.get(repo_id, "")
    if pinned:
        logger.info("%s: resolved 'main' to pinned revision %s", repo_id, pinned[:12])
        return pinned

    if strict:
        raise UnpinnedRevisionError(
            f"{repo_id} has no pinned revision, and this run is strict.\n"
            "Push the dataset with `python ml/scripts/push_dataset.py`, then record "
            f"the sha it prints in PINS[{repo_id!r}] in ml/src/sbr/utils/hub.py.\n"
            "Training against 'main' produces numbers that cannot be reproduced, "
            "which is the specific failure this project exists not to repeat."
        )

    logger.warning(
        "%s is unpinned – acceptable while iterating, but pin it before any run "
        "whose numbers will be quoted",
        repo_id,
    )
    return "main"


def configure_hf_runtime() -> None:
    """Set HF env vars before any HF-backed library is imported.

    Xet is disabled and timeouts are raised because Kaggle's network to the Hub
    is slow and flaky enough that the defaults time out on large shard pulls.
    """
    os.environ.setdefault("HF_HOME", "/kaggle/working/hf_home" if on_kaggle() else str(Path.home() / ".cache" / "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
    Path(os.environ["HF_HOME"]).mkdir(parents=True, exist_ok=True)


def on_kaggle() -> bool:
    return Path("/kaggle").exists()


def load_hf_token() -> str | None:
    """Resolve a Hugging Face token, or return None."""
    token = os.environ.get("HF_TOKEN")
    if token:
        return token.strip()

    for path in KAGGLE_SECRET_PATHS:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()

    try:
        from kaggle_secrets import UserSecretsClient

        return UserSecretsClient().get_secret("HF_TOKEN")
    except Exception:  # noqa: BLE001 – absent outside interactive Kaggle
        logger.warning("no Hugging Face token found")
        return None


def download_dataset(
    repo_id: str,
    revision: str = "main",
    local_dir: Path | None = None,
    strict: bool = False,
) -> Path:
    """Snapshot a dataset repo at a pinned revision.

    ``strict=True`` refuses to proceed without a pin. Training kernels pass it,
    because their numbers get quoted.
    """
    from huggingface_hub import snapshot_download

    configure_hf_runtime()
    revision = resolve_revision(repo_id, revision, strict=strict)

    target = snapshot_download(
        repo_id=repo_id,
        revision=revision,
        repo_type="dataset",
        local_dir=str(local_dir) if local_dir else None,
        token=load_hf_token(),
    )
    return Path(target)


def upload_dataset(
    repo_id: str,
    local_dir: Path,
    commit_message: str,
    private: bool = False,
    allow_patterns: list[str] | None = None,
) -> str:
    """Upload a prepared pool as a dataset revision. Returns the commit sha.

    The sha is the point: it goes into :data:`PINS`, and every number measured
    afterwards names it.
    """
    from huggingface_hub import HfApi

    configure_hf_runtime()
    token = load_hf_token()
    if not token:
        raise RuntimeError("cannot upload without a Hugging Face token")
    if not local_dir.exists():
        raise FileNotFoundError(f"nothing to upload: {local_dir}")

    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)

    commit = api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(local_dir),
        commit_message=commit_message,
        allow_patterns=allow_patterns,
    )
    sha = getattr(commit, "oid", None) or api.dataset_info(repo_id, token=token).sha
    logger.info("uploaded %s -> %s at %s", local_dir, repo_id, sha)
    return sha


def upload_artifacts(
    repo_id: str,
    files: dict[str, Path],
    commit_message: str,
    private: bool = False,
) -> None:
    """Upload artefacts to a model repo, creating it if needed.

    ``files`` maps path-in-repo -> local path.
    """
    from huggingface_hub import HfApi

    configure_hf_runtime()
    token = load_hf_token()
    if not token:
        raise RuntimeError("cannot upload without a Hugging Face token")

    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="model", private=private, exist_ok=True)

    for path_in_repo, local_path in files.items():
        if not local_path.exists():
            logger.warning("skipping missing artefact: %s", local_path)
            continue
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            repo_type="model",
            commit_message=commit_message,
        )
        logger.info("uploaded %s -> %s", local_path.name, path_in_repo)
