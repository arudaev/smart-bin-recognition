"""Open Images V7: the validator's negative corpus, and free out-of-city bins.

Model A's training data is mostly **not** bins. A detector trained only on
photographs of bins learns that everything is a bin – which is exactly what
happened to the predecessor, and why it fires ``Glas`` at 0.39 on a slide of
black text on white (08-legacy-audit § 7.5). The negative corpus is what buys
precision, and precision is what makes "the identifier disagrees with me" a
trustworthy signal instead of noise.

Open Images also turns out to carry a boxable class ``Waste container`` with
human-verified boxes, photographed worldwide. That is out-of-city bin data with
labels already on it, which the legacy archive – one city, one week – cannot
provide at any price, and it contains frames with four or more bins, of which
the legacy archive has exactly zero.

**The exclusion is not optional.** An image holding a waste container can never
be a negative. Letting one through teaches the validator that a bin is not a
bin, and it would be invisible in every aggregate metric afterwards.

Everything here streams. The train annotation CSV is 2.2 GB and the images are
downloaded by the thousand, so this is built to run on a Kaggle kernel with
internet rather than on a laptop – the laptop's jobs are ``push`` and ``output``.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import random
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sbr.dataset.pool import SHARDED, image_path, label_path

logger = logging.getLogger(__name__)

SPLITS = ("train", "validation", "test")
STREAM_CHUNK = 1 << 20


class OpenImagesError(RuntimeError):
    """Raised when the vocabulary or the corpus is not what the config assumes."""


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #


def load_class_index(source: Path | str, timeout: int = 120) -> dict[str, str]:
    """Map display name -> MID from the boxable class descriptions CSV."""
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(source, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    index = {name: mid for mid, name in csv.reader(io.StringIO(text)) if name}
    if not index:
        raise OpenImagesError(f"no classes parsed from {source}")
    logger.info("open images vocabulary: %d boxable classes", len(index))
    return index


def resolve_mids(names: list[str], index: dict[str, str]) -> dict[str, str]:
    """Names to MIDs, failing loudly on anything the vocabulary does not have.

    Silently dropping an unknown class is how a "2 500 hard negative" corpus
    quietly becomes 900 and nobody notices until the false-positive rate does
    not move.
    """
    missing = [name for name in names if name not in index]
    if missing:
        raise OpenImagesError(
            f"not Open Images boxable classes: {missing}. "
            "Check ml/configs/open_images.yaml against the descriptions CSV; "
            "postboxes and vending machines genuinely are not in this vocabulary "
            "and come from the Commons harvest instead."
        )
    return {name: index[name] for name in names}


# --------------------------------------------------------------------------- #
# Annotations
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Box:
    """One annotated box, in Open Images' normalised xmin/xmax/ymin/ymax."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    is_group_of: bool = False

    def to_yolo(self) -> tuple[float, float, float, float]:
        """Convert to YOLO's centre-x, centre-y, width, height."""
        return (
            (self.x_min + self.x_max) / 2,
            (self.y_min + self.y_max) / 2,
            self.x_max - self.x_min,
            self.y_max - self.y_min,
        )

    @property
    def is_degenerate(self) -> bool:
        return self.x_max <= self.x_min or self.y_max <= self.y_min


@dataclass
class Scan:
    """What one pass over a bbox CSV found."""

    positives: dict[str, list[Box]] = field(default_factory=lambda: defaultdict(list))
    street: set[str] = field(default_factory=set)
    hard: set[str] = field(default_factory=set)
    rows: int = 0

    def negatives(self, exclude_positives: bool = True) -> tuple[set[str], set[str]]:
        """Street and hard-negative image ids, disjoint, with every bin removed.

        **Disjoint matters.** The two sets are filled row by row, so a photograph
        holding a car *and* a barrel joins both, and the two are then sampled and
        fetched independently: the first harvest downloaded 25 images twice and
        wrote 17 499 records over 17 474 files, which is a corpus that overstates
        itself. The overlap is small and it is exactly the kind of quiet miscount
        this project exists not to repeat.

        **Hard wins.** An image that is both is a hard negative. Those are the
        scarce, informative ones – roughly bin-shaped things on a pavement – and
        they carry a deliberate quota. Spending one as a street scene dilutes the
        category that actually buys the low false-positive rate.
        """
        banned = set(self.positives) if exclude_positives else set()
        hard = self.hard - banned
        return self.street - banned - hard, hard


def open_csv(source: Path | str, timeout: int = 600):
    """Open a CSV from disk or over HTTP, as a text stream."""
    if isinstance(source, Path):
        return source.open("r", encoding="utf-8", newline="")
    response = urllib.request.urlopen(source, timeout=timeout)
    return io.TextIOWrapper(response, encoding="utf-8", newline="")


def scan_boxes(
    source: Path | str,
    positive_mid: str,
    street_mids: set[str],
    hard_mids: set[str],
    drop_group_of: bool = True,
) -> Scan:
    """One streaming pass over a bbox CSV.

    One pass, not three: the train file is 2.2 GB and the exclusion needs the
    positives anyway, so everything is collected together.
    """
    scan = Scan()
    with open_csv(source) as handle:
        for row in csv.DictReader(handle):
            scan.rows += 1
            label = row["LabelName"]
            image_id = row["ImageID"]

            if label == positive_mid:
                group = row.get("IsGroupOf", "0") == "1"
                if group and drop_group_of:
                    # A group-of box covers a crowd with one rectangle instead of
                    # localising anything. Still records that the image HAS bins,
                    # so it stays excluded from the negatives below.
                    scan.positives.setdefault(image_id, [])
                    continue
                box = Box(
                    x_min=float(row["XMin"]), x_max=float(row["XMax"]),
                    y_min=float(row["YMin"]), y_max=float(row["YMax"]),
                    is_group_of=group,
                )
                if not box.is_degenerate:
                    scan.positives[image_id].append(box)
            elif label in street_mids:
                scan.street.add(image_id)
            elif label in hard_mids:
                scan.hard.add(image_id)

    logger.info(
        "scanned %d rows: %d images with a waste container, %d street, %d hard",
        scan.rows, len(scan.positives), len(scan.street), len(scan.hard),
    )
    return scan


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #


def image_url(base: str, split: str, image_id: str) -> str:
    if split not in SPLITS:
        raise OpenImagesError(f"unknown split {split!r}")
    return f"{base.rstrip('/')}/{split}/{image_id}.jpg"


def load_attribution(source: Path | str, wanted: set[str]) -> dict[str, dict[str, str]]:
    """Photographer, licence and original URL, for the images we keep.

    Open Images is CC-BY: attribution is a licence condition, not a nicety, so
    it is collected at build time rather than reconstructed later.
    """
    attribution: dict[str, dict[str, str]] = {}
    with open_csv(source) as handle:
        for row in csv.DictReader(handle):
            image_id = row.get("ImageID")
            if image_id in wanted:
                attribution[image_id] = {
                    "author": row.get("Author", ""),
                    "author_profile": row.get("AuthorProfileURL", ""),
                    "title": row.get("Title", ""),
                    "licence": row.get("License", ""),
                    "original_url": row.get("OriginalURL", ""),
                }
    logger.info("attribution recovered for %d/%d images", len(attribution), len(wanted))
    return attribution


def fetch_image(url: str, timeout: int = 60) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except Exception as error:  # noqa: BLE001 - one dead URL must not stop 15 000
        logger.debug("skipped %s: %s", url, error)
        return None


def save_resized(payload: bytes, target: Path, max_edge: int, quality: int, min_edge: int) -> tuple[int, int] | None:
    """Write a resized JPEG. Returns its size, or None if it was too small."""
    from PIL import Image

    try:
        # `handle` is an ImageFile and convert() returns an Image, so the
        # converted result gets its own name rather than rebinding the target.
        with Image.open(io.BytesIO(payload)) as handle:
            image = handle.convert("RGB")
            width, height = image.size
            if min(width, height) < min_edge:
                return None
            scale = min(1.0, max_edge / max(width, height))
            if scale < 1.0:
                image = image.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target, "JPEG", quality=quality, optimize=True)
            return image.size
    except Exception as error:  # noqa: BLE001
        logger.debug("undecodable image for %s: %s", target.name, error)
        return None


def sample(ids: set[str], count: int, seed: int) -> list[str]:
    """A deterministic sample. Sorted first so the seed means the same thing."""
    ordered = sorted(ids)
    if len(ordered) <= count:
        return ordered
    return random.Random(seed).sample(ordered, count)


@dataclass(frozen=True)
class Candidate:
    """One image to fetch, and the boxes it carries (empty for a negative)."""

    split: str
    image_id: str
    boxes: tuple[Box, ...] = ()
    kind: str = "positive"      # "positive" | "street" | "hard"

    @property
    def is_negative(self) -> bool:
        return self.kind != "positive"


def harvest(
    candidates: list[Candidate],
    out_dir: Path,
    config: dict[str, Any],
    attribution: dict[str, dict[str, str]] | None = None,
    fetch=fetch_image,
    workers: int = 16,
) -> dict[str, Any]:
    """Download, resize and write one pool. Returns its manifest.

    Negatives get an **empty** label file rather than no label file: to YOLO
    that is a background image, which is the whole point of them. A missing file
    would be an unlabelled image, which is a different thing and would be
    silently dropped from training.

    The pool is written **sharded** – ``images/ab/<id>.jpg`` – because this is
    the harvest that does not fit in one directory: the Hub rejects a push where
    any directory holds more than 10 000 files, and the negative corpus alone is
    ~17 500. See :mod:`sbr.dataset.pool`.
    """
    from concurrent.futures import ThreadPoolExecutor

    source = config["source"]
    settings = config["image"]
    attribution = attribution or {}

    # One frame, one record. A duplicate would be fetched twice, written twice
    # and counted twice, and the manifest would no longer be a faithful index of
    # what is on disk - which is how "17 499 negatives" became 17 474 files.
    # Belt and braces with Scan.negatives()'s disjointness: this is the last
    # place that can still tell, and it is cheap to ask.
    seen: set[str] = set()
    deduped: list[Candidate] = []
    for candidate in candidates:
        if candidate.image_id not in seen:
            seen.add(candidate.image_id)
            deduped.append(candidate)
    if len(deduped) < len(candidates):
        logger.warning(
            "%d duplicate candidates dropped before fetching (%d -> %d)",
            len(candidates) - len(deduped), len(candidates), len(deduped),
        )
    candidates = deduped

    images_dir, labels_dir = out_dir / "images", out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    failed = too_small = 0

    def one(candidate: Candidate) -> dict[str, Any] | None:
        url = image_url(source["image_base"], candidate.split, candidate.image_id)
        payload = fetch(url)
        if payload is None:
            return None
        name = f"{candidate.image_id}.jpg"
        size = save_resized(
            payload,
            image_path(out_dir, name, SHARDED),
            max_edge=settings["max_edge"],
            quality=settings["jpeg_quality"],
            min_edge=settings["min_edge"],
        )
        if size is None:
            return None

        # Class 0 for every box: the validator is class-agnostic.
        lines = [
            "0 {:.6f} {:.6f} {:.6f} {:.6f}".format(*box.to_yolo())
            for box in candidate.boxes
            if not box.is_degenerate
        ]
        label = label_path(out_dir, candidate.image_id, SHARDED)
        label.parent.mkdir(parents=True, exist_ok=True)
        label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        return {
            "file": name,
            "width": size[0],
            "height": size[1],
            "boxes": len(lines),
            "bins_in_frame": len(lines),
            "kind": candidate.kind,
            # Every Open Images photograph is its own capture cluster: they are
            # unrelated pictures by unrelated photographers, so grouping them
            # would invent a relationship that is not there.
            "capture_cluster": f"open-images/{candidate.image_id}",
            "annotator": None,
            "capture_date": None,
            **provenance(source, candidate.split, candidate.image_id,
                         attribution.get(candidate.image_id)),
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, record in enumerate(pool.map(one, candidates), start=1):
            if record is None:
                failed += 1
            else:
                records.append(record)
            if index % 500 == 0:
                logger.info("harvested %d/%d (%d failed)", index, len(candidates), failed)

    manifest = {
        # Read by sbr.dataset.pool.layout_of. Its absence means flat, which is
        # what the pinned legacy revision is.
        "layout": SHARDED,
        "images": len(records),
        "boxes": sum(r["boxes"] for r in records),
        "positives": sum(1 for r in records if r["boxes"]),
        "background_images": sum(1 for r in records if not r["boxes"]),
        "requested": len(candidates),
        "unavailable": failed,
        "too_small": too_small,
        "by_kind": dict(sorted(Counter(r["kind"] for r in records).items())),
        "bins_per_frame": dict(sorted(Counter(r["boxes"] for r in records).items())),
        "source": source["name"],
        "licence": source["licence"],
        "records": records,
        "crop_records": [],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info(
        "%s: %d images (%d with boxes, %d background), %d unavailable",
        out_dir.name, len(records), manifest["positives"], manifest["background_images"], failed,
    )
    return manifest


def provenance(source: dict[str, Any], split: str, image_id: str, attribution: dict[str, str] | None) -> dict[str, Any]:
    attribution = attribution or {}
    return {
        "source": source["name"],
        "source_url": attribution.get("original_url", ""),
        "licence": attribution.get("licence") or source["licence"],
        "attribution": attribution.get("author", ""),
        "attribution_profile": attribution.get("author_profile", ""),
        "open_images_id": image_id,
        "open_images_split": split,
        "region_id": "unknown",
        "label_origin": "open-images",
        "adjudication": "not_required",
    }
