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

#: Checked in order, then any attached dataset is searched. The glob matters:
#: a kernel that harvested for 35 minutes and then died on "no Hugging Face
#: token found" is a bad way to learn that a dataset mounted under a slug these
#: two paths did not anticipate.
KAGGLE_SECRET_PATHS = (
    Path("/kaggle/input/sbr-secrets/hf_token.txt"),
    Path("/kaggle/input/chexvision-secrets/hf_token.txt"),  # shared secrets dataset
)

#: Filenames a token might be stored under in an attached Kaggle dataset.
KAGGLE_SECRET_NAMES = ("hf_token.txt", "HF_TOKEN.txt", "hf_token", "token.txt")

#: Where Kaggle mounts attached datasets. A module constant so a test can point
#: it somewhere real instead of stubbing out the function under test.
KAGGLE_INPUT = Path("/kaggle/input")

#: Dataset revision each repo is pinned to. Filled in by
#: ``ml/scripts/push_dataset.py``, which prints the sha after an upload; an empty
#: string means "never pushed", and a strict run against it is an error rather
#: than a silent fall back to ``main``.
#:
#: Changing a pin means the next training run sees different data. That is a
#: deliberate act and belongs in its own commit, with the reason in the message.
PINS: dict[str, str] = {
    # legacy + open_images + negatives. 18 954 frames over three subsets:
    #   legacy       370 frames, 403 boxes, flat layout, one city, one week
    #   open_images  1 110 frames, 1 936 boxes, 98 of them with 4+ bins
    #   negatives    17 474 background frames (14 975 street, 2 499 hard)
    # Pushed 2026-08-16, 37 913 files. Two repairs landed on top of the harvest
    # and are part of this revision: the manifest had recorded 25 frames twice,
    # as both street and hard, and the card described only the legacy subset.
    # No frame carries a usable second region_id, so holdout_region is empty and
    # the generalisation number is NOT available from this data.
    # Previous, legacy only: 581eedae78c69fbaa02c2db77687d030e309b5ed
    "arudaev/smart-bin-detect": "8666aa23ff1a8572cd57349a8c5bd1f0b2d88285",
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

    # Any attached dataset, at any depth. The named paths above are a fast path,
    # not the whole search: Kaggle mounts attached datasets under
    # /kaggle/input/datasets/<owner>/<slug>/ now, not /kaggle/input/<slug>/, and
    # a resolver that knows only the old shape finds nothing and says nothing
    # useful about why.
    inputs = KAGGLE_INPUT
    if inputs.is_dir():
        for name in KAGGLE_SECRET_NAMES:
            for found in sorted(inputs.rglob(name)):
                logger.info("found a token at %s", found)
                return found.read_text(encoding="utf-8").strip()
        listing = [str(p.relative_to(inputs)) for p in sorted(inputs.rglob("*")) if p.is_file()]
        logger.warning(
            "no token in any attached dataset. /kaggle/input holds %d files: %s",
            len(listing), listing[:20] or "nothing",
        )

    try:
        from kaggle_secrets import UserSecretsClient

        return UserSecretsClient().get_secret("HF_TOKEN")
    except Exception:  # noqa: BLE001 – absent outside interactive Kaggle
        logger.warning("no Hugging Face token found")
        return None


def require_hf_token(purpose: str = "upload") -> str:
    """Resolve a token or stop now, before doing expensive work.

    Called at the *top* of any kernel that will eventually upload. The negatives
    harvest streamed a 2.2 GB CSV and fetched 18 609 images before discovering
    it had nowhere to put them; that is a 35-minute way to find out something
    knowable in the first second.
    """
    token = load_hf_token()
    if not token:
        raise SystemExit(
            f"cannot {purpose} without a Hugging Face token, and this run would "
            "have spent its whole budget before finding out.\n"
            "Attach a Kaggle dataset containing hf_token.txt, or set HF_TOKEN."
        )
    return token


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


#: Above this many files, ``upload_folder`` is the wrong tool – see
#: :func:`upload_dataset`.
LARGE_UPLOAD_FILES = 500


def preflight_layout(local_dir: Path) -> None:
    """Refuse a tree the Hub will reject, before spending anything on it.

    The Hub caps a directory at 10 000 files. The first negatives harvest found
    that out after thirty minutes of downloading, in the middle of an upload,
    from an error message that ``upload_large_folder`` responded to by halving
    its batch size six times – a remedy for a different problem entirely, which
    then tripped the API rate limit as well.

    Same argument as :func:`require_hf_token`: this is knowable in the first
    second, so it is checked in the first second. The fix is to shard the pool
    (:mod:`sbr.dataset.pool`), not to retry.
    """
    from sbr.dataset.pool import MAX_FILES_PER_DIR, oversized_directories

    oversized = oversized_directories(local_dir)
    if not oversized:
        return
    listing = "\n".join(
        f"  {directory.relative_to(local_dir)}: {count} files" for directory, count in oversized.items()
    )
    raise ValueError(
        f"the Hub rejects a push where any directory holds more than "
        f"{MAX_FILES_PER_DIR} files, and this one would:\n{listing}\n"
        "Shard the pool - sbr.dataset.pool.shard puts a two-hex-character "
        "directory between images/ and the file. Retrying will not help; the "
        "rejection is about the tree, not the batch."
    )


def ensure_repo(repo_id: str, private: bool = False, repo_type: str = "dataset") -> None:
    """Create the repo now, so the upload path holds no fatal one-shot call.

    Called at the *top* of a kernel, beside :func:`require_hf_token`, and for the
    same reason. ``create_repo`` is one request, but it is a request: a run whose
    quota is exhausted by the time the harvest finishes dies on it having done
    all of the work and none of the upload. That is exactly how the second
    negatives run ended – a previous run of the same kernel was still uploading
    eleven hours later and was holding the account's entire 1000-per-5-minutes
    budget, so the first Hub call after a clean 16-minute harvest got a 429.
    """
    from huggingface_hub import HfApi

    configure_hf_runtime()
    HfApi(token=load_hf_token()).create_repo(
        repo_id=repo_id, repo_type=repo_type, private=private, exist_ok=True
    )
    logger.info("%s exists (%s)", repo_id, "private" if private else "public")


def delete_subsets(repo_id: str, names: list[str]) -> None:
    """Remove subset directories from a dataset repo, tolerating absent ones.

    A push that failed partway leaves a half-written subset behind – the first
    negatives run left 10 000 label files with no images beside them. Uploading
    on top of that starts the next push already over the directory cap, so a
    replacing push deletes first.

    **Absent is tolerated; failed is not.** A 404 means there was nothing to
    delete, which is the ordinary case. Anything else – a 429 above all – means
    the tree is still there, and returning quietly would let the caller upload
    onto the very files it was asked to clear.
    """
    from huggingface_hub import HfApi

    configure_hf_runtime()
    api = HfApi(token=load_hf_token())
    for name in names:
        try:
            api.delete_folder(path_in_repo=name, repo_id=repo_id, repo_type="dataset")
            logger.info("deleted %s/ from %s", name, repo_id)
        except Exception as error:  # noqa: BLE001 - classified by status below
            # Duck-typed rather than caught by class: the Hub's error types have
            # moved between huggingface_hub versions, and this runs on whatever
            # Kaggle's pip resolves to that morning.
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status == 404:
                logger.info("nothing to delete at %s/ in %s", name, repo_id)
                continue
            raise RuntimeError(
                f"could not delete {name}/ from {repo_id} (HTTP {status}). "
                "Refusing to continue: the caller asked for a replacing push, and "
                "uploading now would land on top of the tree this was meant to "
                "clear. If this is a 429, another run is holding the account's "
                "API quota - find it and stop it before retrying."
            ) from error


def upload_dataset(
    repo_id: str,
    local_dir: Path,
    commit_message: str,
    private: bool = False,
    allow_patterns: list[str] | None = None,
    workers: int = 4,
    create: bool = True,
) -> str:
    """Upload a prepared pool as a dataset revision. Returns the commit sha.

    The sha is the point: it goes into :data:`PINS`, and every number measured
    afterwards names it.

    **Why this is not just ``upload_folder``.** Every ``.jpg`` is an LFS object
    under the default ``.gitattributes``, and ``upload_folder`` asks the Hub for
    pre-signed S3 URLs for the *whole batch* before uploading any of it. Those
    URLs last 900 seconds. Pushing 18 609 harvested images over a Kaggle
    connection took longer than that, so the run died sixteen minutes in with::

        AccessDenied / Request has expired / X-Amz-Expires 900

    which the Hub reports as "403 Forbidden – make sure your token has the
    correct permissions", and which has nothing to do with the token.

    ``upload_large_folder`` is built for this shape: many small commits, LFS
    URLs requested in small batches, parallel workers, and resumption on retry.

    ``create=False`` skips ``create_repo`` for callers that ran
    :func:`ensure_repo` up front. An unattended run should: by the time a harvest
    finishes, the API quota may be gone, and dying on repo creation after all the
    work and before any of the upload is the worst available outcome.
    """
    from huggingface_hub import HfApi

    configure_hf_runtime()
    token = load_hf_token()
    if not token:
        raise RuntimeError("cannot upload without a Hugging Face token")
    if not local_dir.exists():
        raise FileNotFoundError(f"nothing to upload: {local_dir}")
    preflight_layout(local_dir)

    api = HfApi(token=token)
    if create:
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)

    count = sum(1 for path in local_dir.rglob("*") if path.is_file())
    large = count > LARGE_UPLOAD_FILES and hasattr(api, "upload_large_folder")

    if large:
        logger.info(
            "%d files – using upload_large_folder (pre-signed LFS URLs expire "
            "after 900 s, and a single batch of this many does not finish in time). "
            "Expect 429s: the Hub allows 1000 API requests per 5 minutes and this "
            "needs several thousand. huggingface_hub backs off and retries on its "
            "own, so a wall of 'Rate limited. Waiting 283.0s' is the upload "
            "working, not failing. %d workers, deliberately few – more "
            "concurrency against a per-window quota buys nothing.",
            count, workers,
        )
        # No commit object: it makes many commits by design.
        api.upload_large_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=str(local_dir),
            allow_patterns=allow_patterns,
            num_workers=workers,
            print_report=False,
        )
        sha = api.dataset_info(repo_id, token=token).sha
    else:
        commit = api.upload_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=str(local_dir),
            commit_message=commit_message,
            allow_patterns=allow_patterns,
        )
        sha = getattr(commit, "oid", None) or api.dataset_info(repo_id, token=token).sha

    logger.info("uploaded %s (%d files) -> %s at %s", local_dir, count, repo_id, sha)
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
