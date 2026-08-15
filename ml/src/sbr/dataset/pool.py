"""How a pool is laid out on disk, and why it is not one flat directory.

A pool is ``manifest.json`` plus ``images/``, ``labels/`` and sometimes
``crops/``. Small pools keep those flat. The harvested ones cannot, because the
Hugging Face Hub refuses a push where any directory holds more than 10 000
files::

    Your push was rejected because it contains too many files per directory.
    Each directory in your git repo can only contain up to 10000 files.
    Offending directories: /negatives/labels/

``ml/configs/open_images.yaml`` asks for 15 000 street plus 2 500 hard
negatives, so ``negatives/labels/`` is ~17 500 files. The first harvest spent
thirty minutes streaming a 2.2 GB CSV and downloading 18 609 images before
learning that, which is a bad way to find out something knowable in the first
second – hence :data:`MAX_FILES_PER_DIR` and the preflight in
``sbr.utils.hub.upload_dataset`` that reads it.

So a harvested pool interposes a shard level::

    negatives/
    ├── manifest.json      "layout": "sharded"
    ├── images/ab/<id>.jpg
    └── labels/ab/<id>.txt

**Both layouts have to keep working.** The legacy subset was pushed flat and is
pinned at revision ``581eedae…``; a resolver that only understood shards would
invalidate the one pin this project has. So the layout is declared in the
manifest, a manifest without the key is flat, and :func:`layout_of` is the only
thing that decides.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

#: The Hub's hard cap, quoted above. Not a guideline – the push is rejected.
MAX_FILES_PER_DIR = 10_000

#: Shard directories per pool subdirectory. 17 500 files over 256 buckets is
#: ~68 each; a bucket would need a 146x skew to reach the cap.
SHARD_BUCKETS = 256

FLAT = "flat"
SHARDED = "sharded"


def shard(stem: str) -> str:
    """The shard directory a file belongs in: two hex characters.

    sha256 rather than ``hash()``, which is salted per process and would scatter
    a pool differently on every run – the same reason ``prepare._bucket`` uses
    it for split assignment.

    Keyed on the *stem*, so a frame's image and its label land in the same
    bucket name and a shard can be read as one unit.
    """
    digest = hashlib.sha256(stem.encode("utf-8")).hexdigest()
    return f"{int(digest[:8], 16) % SHARD_BUCKETS:02x}"


def layout_of(manifest: dict[str, Any]) -> str:
    """``"sharded"`` or ``"flat"``, from the manifest.

    The default is load-bearing: the pinned legacy revision predates the key.
    """
    declared = manifest.get("layout", FLAT)
    if declared not in (FLAT, SHARDED):
        raise ValueError(
            f"manifest declares layout {declared!r}; expected {FLAT!r} or {SHARDED!r}"
        )
    return declared


def _resolve(pool: Path, directory: str, name: str, layout: str, key: str) -> Path:
    if layout == SHARDED:
        return pool / directory / shard(key) / name
    return pool / directory / name


def image_path(pool: Path, name: str, layout: str = FLAT) -> Path:
    """Where frame ``name`` lives in ``pool``."""
    return _resolve(pool, "images", name, layout, Path(name).stem)


def label_path(pool: Path, stem: str, layout: str = FLAT) -> Path:
    """Where the YOLO label for frame ``stem`` lives in ``pool``.

    An empty file here is a deliberate background image, not a missing label.
    """
    return _resolve(pool, "labels", f"{stem}.txt", layout, stem)


def crop_path(pool: Path, name: str, layout: str = FLAT) -> Path:
    """Where identifier crop ``name`` lives in ``pool``."""
    return _resolve(pool, "crops", name, layout, Path(name).stem)


def oversized_directories(root: Path, cap: int | None = None) -> dict[Path, int]:
    """Directories under ``root`` holding more than ``cap`` files, and how many.

    Counts files only – a subdirectory does not count towards its parent, which
    is what makes sharding work.

    ``cap`` is resolved at call time rather than bound as a default, so that a
    test can move :data:`MAX_FILES_PER_DIR` and have this follow.
    """
    cap = MAX_FILES_PER_DIR if cap is None else cap
    counts: dict[Path, int] = {}
    for path in root.rglob("*"):
        if path.is_file():
            counts[path.parent] = counts.get(path.parent, 0) + 1
    return {directory: count for directory, count in sorted(counts.items()) if count > cap}
