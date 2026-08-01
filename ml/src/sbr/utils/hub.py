"""Hugging Face Hub helpers: token resolution, dataset download, artefact upload.

Token resolution order mirrors CheXVision, because the same Kaggle dispatch
mechanism is used and the same failure modes apply:

1. ``HF_TOKEN`` in the environment (local, and injected by CI).
2. A private Kaggle dataset mounted at ``/kaggle/input/<secrets>/hf_token.txt``.
   This is the reliable path for API-pushed kernels.
3. ``UserSecretsClient`` – works only in interactive Kaggle sessions.
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


def download_dataset(repo_id: str, revision: str = "main", local_dir: Path | None = None) -> Path:
    """Snapshot a dataset repo. Pin ``revision`` to a commit for reproducibility."""
    from huggingface_hub import snapshot_download

    configure_hf_runtime()
    if revision == "main":
        logger.warning(
            "dataset revision is 'main' – acceptable during development, but pin a "
            "commit hash before any run whose numbers will be quoted"
        )

    target = snapshot_download(
        repo_id=repo_id,
        revision=revision,
        repo_type="dataset",
        local_dir=str(local_dir) if local_dir else None,
        token=load_hf_token(),
    )
    return Path(target)


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
