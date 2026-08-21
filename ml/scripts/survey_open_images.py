#!/usr/bin/env python3
"""Sample Open Images bin crops and lay them out for a person to look at.

    python ml/scripts/survey_open_images.py --out artifacts/oi-survey

docs/12 P1 asks a question nobody has answered: the pinned pool holds 1 110 Open
Images bin frames carrying 1 936 boxes from global street scenes, and **nobody
has looked at what form factors are in them**. Six of the ten form factors have
no legacy data at all, so whether this corpus could close that gap decides
whether a second human pass is worth anybody's time.

**This script produces pictures, not labels.** It writes nothing back into any
manifest, no crop acquires a ``form_factor``, and the output is a set of contact
sheets plus an index. What is *in* them is reported separately, by a person, as
a visual survey - one observer, no blind protocol, no adjudication record.
Anything stronger than "counts over a sample" would be inventing evidence.

**The sample is frozen in docs/12 and fixed here**: 384 boxes, seed 20260821,
without replacement, sampling unit the **box** rather than the frame - a frame
with six bins holds six answers to "what form factors are in them".

Crops use the identifier's own padding, so what a reviewer sees is what a crop
would actually look like rather than a tighter or looser picture chosen here.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.dataset.pool import image_path, label_path, layout_of  # noqa: E402
from sbr.utils.hub import configure_hf_runtime, load_hf_token, resolve_revision  # noqa: E402

logger = logging.getLogger("survey")

#: docs/12, frozen before a single crop was opened. Do not tune these because a
#: result is uninteresting - that is a different survey and it needs its own
#: pre-registration.
SAMPLE = 384
SEED = 20260821

REPO = "arudaev/smart-bin-detect"
SUBSET = "open_images"

#: `identifier.yaml`'s `crops.padding`. Mirrored rather than imported because
#: this is a survey of what a crop looks like, and it should look like the one
#: the model would get.
PADDING = 0.12

#: Contact-sheet geometry. 48 per sheet over 384 boxes is eight sheets, which is
#: about as much as one person can hold in their head in one sitting.
COLUMNS = 8
ROWS = 6
CELL = 220
LABEL_BAND = 22


def fetch(revision: str, into: Path) -> Path:
    """Snapshot just the Open Images subset. The full pool is 37 913 files."""
    from huggingface_hub import snapshot_download

    configure_hf_runtime()
    target = snapshot_download(
        repo_id=REPO,
        revision=revision,
        repo_type="dataset",
        local_dir=str(into),
        allow_patterns=[f"{SUBSET}/*"],
        token=load_hf_token(),
    )
    return Path(target) / SUBSET


def boxes_in(pool: Path, manifest: dict) -> list[dict]:
    """Every box in the subset, as ``{file, index, bbox_norm, bins_in_frame}``.

    Read from the YOLO label files rather than from the manifest, because the
    manifest records how many boxes a frame has and not where they are.
    """
    layout = layout_of(manifest)
    found: list[dict] = []

    for record in manifest["records"]:
        # label_path takes a STEM and appends .txt - handing it "x.jpg" asks for
        # "x.jpg.txt", which exists nowhere and reports a pool of zero boxes.
        labels = label_path(pool, Path(record["file"]).stem, layout)
        if not labels.exists():
            continue
        for index, line in enumerate(labels.read_text(encoding="utf-8").splitlines()):
            parts = line.split()
            if len(parts) != 5:
                continue
            _, cx, cy, width, height = (float(p) for p in parts)
            found.append({
                "frame": record["file"],
                "box_index": index,
                "bbox_norm": [cx, cy, width, height],
                "bins_in_frame": record.get("bins_in_frame", 1),
                "source_url": record.get("source_url"),
                "attribution": record.get("attribution"),
            })
    return found


def crop_of(pool: Path, layout: str, box: dict):
    """The padded crop for one box, as a PIL image."""
    from PIL import Image

    with Image.open(image_path(pool, box["frame"], layout)) as handle:
        frame = handle.convert("RGB")

    width, height = frame.size
    cx, cy, box_width, box_height = box["bbox_norm"]
    half_width = box_width * (1 + PADDING) / 2
    half_height = box_height * (1 + PADDING) / 2

    left = max(0, int((cx - half_width) * width))
    top = max(0, int((cy - half_height) * height))
    right = min(width, int((cx + half_width) * width))
    bottom = min(height, int((cy + half_height) * height))
    if right - left < 2 or bottom - top < 2:
        return None
    return frame.crop((left, top, right, bottom))


def contact_sheets(crops: list[tuple[int, object]], out: Path) -> list[Path]:
    """Tile the sample into numbered sheets, so a count can be traced to a cell."""
    from PIL import Image, ImageDraw

    per_sheet = COLUMNS * ROWS
    written = []

    for start in range(0, len(crops), per_sheet):
        chunk = crops[start:start + per_sheet]
        sheet = Image.new(
            "RGB", (COLUMNS * CELL, ROWS * (CELL + LABEL_BAND)), (24, 24, 27)
        )
        draw = ImageDraw.Draw(sheet)

        for position, (number, image) in enumerate(chunk):
            column, row = position % COLUMNS, position // COLUMNS
            x, y = column * CELL, row * (CELL + LABEL_BAND)

            thumbnail = image.copy()
            thumbnail.thumbnail((CELL - 8, CELL - 8))
            sheet.paste(
                thumbnail,
                (x + (CELL - thumbnail.width) // 2, y + (CELL - thumbnail.height) // 2),
            )
            draw.text((x + 6, y + CELL + 4), f"{number:03d}", fill=(200, 200, 205))

        path = out / f"sheet-{start // per_sheet + 1:02d}.png"
        sheet.save(path)
        written.append(path)
        logger.info("wrote %s (%d crops)", path.name, len(chunk))

    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=Path("artifacts/oi-survey"))
    parser.add_argument("--pool", type=Path, default=None, help="an already-downloaded subset")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    revision = resolve_revision(REPO, "main", strict=True)
    pool = args.pool or fetch(revision, args.out / "pool")
    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    layout = layout_of(manifest)

    population = boxes_in(pool, manifest)
    logger.info("population: %d boxes over %d frames", len(population), len(manifest["records"]))

    # Deterministic and stated. Sorting first means the sample does not depend on
    # the order the filesystem happened to hand back.
    population.sort(key=lambda b: (b["frame"], b["box_index"]))
    sample = random.Random(SEED).sample(population, min(SAMPLE, len(population)))

    sheets_dir = args.out / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    crops, index = [], []
    for number, box in enumerate(sample, start=1):
        image = crop_of(pool, layout, box)
        if image is None:
            logger.warning("box %d degenerate after padding: %s", number, box["frame"])
            continue
        crops.append((number, image))
        index.append({
            "n": number,
            "frame": box["frame"],
            "box_index": box["box_index"],
            "bbox_norm": box["bbox_norm"],
            "bins_in_frame": box["bins_in_frame"],
            "crop_px": list(image.size),
            "source_url": box["source_url"],
            "attribution": box["attribution"],
        })

    sheets = contact_sheets(crops, sheets_dir)

    (args.out / "index.json").write_text(
        json.dumps({
            "survey": "docs/12 P1 - Open Images form-factor survey",
            "repo": REPO,
            "revision": revision,
            "subset": SUBSET,
            "population_boxes": len(population),
            "population_frames": len(manifest["records"]),
            "sample_size": SAMPLE,
            "seed": SEED,
            "sampling_unit": "box",
            "padding": PADDING,
            "sheets": [p.name for p in sheets],
            "produces": "pictures, not labels. Nothing is written back to any "
                        "manifest and no crop acquires a form_factor",
            "crops": index,
        }, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "%d crops over %d sheets in %s - now go and look at them",
        len(crops), len(sheets), sheets_dir,
    )


if __name__ == "__main__":
    main()
