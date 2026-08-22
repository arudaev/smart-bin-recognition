#!/usr/bin/env python3
"""Render docs/12 P3's pre-registered spot-check as a page you can tap on a phone.

    python ml/scripts/build_spotcheck.py --out docs/spot-check.html

**Why this exists.** `colour_labels.py spot-check` serves the same 25 crops over
`http://127.0.0.1:8766`, which is the right tool for somebody at the laptop that
holds the pool. The maintainer is frequently not at it, and the check gates three
decisions (D1, D2, D5 in docs/07). This renders the identical draw - same seed,
same subset - into one self-contained page that can be published as an Artifact
and answered from a phone.

**It is blinded, and that is not a detail.** The agent's own labels exist in
`colour-labels.json` and are deliberately not rendered. `adjudicate.py` learned
this expensively: the pool ships a stream-to-shape proposal on every crop, and
measured against the finished blind pass those proposals are wrong on **116 of
403**. A reviewer who is shown an answer confirms it.

**The output is gitignored** - 1.9 MB of base64 imagery, from a directory whose
images are already excluded. The generator is the artefact; the render is not.

**Reading the answers back.** The page declares the `artifact` capability and
runs as a live document: a tap writes `data-body` / `data-lid` onto the card, and
attribute changes made by a viewer gesture are what the platform saves. Fetch the
published page and parse those attributes, then feed them to
`colour_labels.record_labels(pool, "alex", rows, provisional=False)` - human rows
beat agent rows automatically wherever both exist.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import random
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
sys.path.insert(0, str(ML_ROOT / "scripts"))
sys.path.insert(0, str(ML_ROOT / "src"))

import colour_labels as cl  # noqa: E402

logger = logging.getLogger("spotcheck")

#: Longest edge, in pixels, of each embedded crop. 560 keeps a bin readable on a
#: phone at roughly 70 kB a card; the whole page lands near 1.9 MB against the
#: Artifact limit of 16 MB.
MAX_EDGE = 560
JPEG_QUALITY = 82


def draw(pool: Path, n: int) -> list[str]:
    """The same 25 crops `colour_labels.py spot-check` serves.

    `SEED + 1`, exactly as that command does - a different seed from the sample's
    own, so the check is not a deterministic function of the thing it checks.
    """
    sample = json.loads((pool / cl.SAMPLE_FILE).read_text(encoding="utf-8"))
    rng = random.Random(cl.SEED + 1)
    return sorted(rng.sample(sample["crops"], min(n, len(sample["crops"]))))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", type=Path, default=REPO_ROOT / "data/legacy/pool")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "docs/spot-check.html")
    parser.add_argument("-n", type=int, default=25)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    import cv2

    pool: Path = args.pool
    subset = draw(pool, args.n)
    _crops, _frames, factors = cl.pool_index(pool)

    tax = json.loads((REPO_ROOT / "data/taxonomy/waste-streams.json").read_text(encoding="utf-8"))
    colours = [(c["id"], c["hex_ref"]) for c in tax["colors"] if c.get("hex_ref")]

    def swatches(field: str) -> str:
        out = [
            f'<button class="sw" data-field="{field}" data-value="{cid}" '
            f'style="--sw:{hexv}" aria-label="{cid}"><i></i><span>{cid}</span></button>'
            for cid, hexv in colours
        ]
        out.append(f'<button class="sw x" data-field="{field}" data-value="unsure">unsure</button>')
        if field == "lid":
            out.append(f'<button class="sw x" data-field="{field}" data-value="not_visible">no lid</button>')
        return "".join(out)

    cards = []
    for i, name in enumerate(subset):
        img = cv2.imread(str(pool / "crops" / name))
        if img is None:
            logger.warning("skipping unreadable crop %s", name)
            continue
        h, w = img.shape[:2]
        scale = MAX_EDGE / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        _ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        b64 = base64.b64encode(buf.tobytes()).decode()

        factor = factors.get(name, "?")
        wheelie = factor.startswith("wheelie")
        # A non-wheelie has no lid to judge, so the field is pre-closed rather
        # than asked. P3 scores the lid on wheelies only.
        lid_attr = "" if wheelie else "not_visible"
        lid_block = (
            f'<div class="field"><h3>Lid colour</h3><div class="sws">{swatches("lid")}</div></div>'
            if wheelie
            else '<p class="na">No lid - not a wheelie.</p>'
        )
        cards.append(
            f'<article class="card" data-file="{name}" data-body="" data-lid="{lid_attr}">'
            f'<header><b>{i + 1} / {len(subset)}</b><span class="ff">{factor}</span>'
            f'<span class="tick" aria-hidden="true"></span></header>'
            f'<img src="data:image/jpeg;base64,{b64}" alt="bin crop {i + 1}">'
            f'<div class="field"><h3>Body colour</h3><div class="sws">{swatches("body")}</div></div>'
            f"{lid_block}</article>"
        )

    template = (ML_ROOT / "scripts" / "spotcheck_template.html").read_text(encoding="utf-8")
    html = template.replace("<!--CARDS-->", "\n".join(cards)).replace("{{N}}", str(len(subset)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    logger.info("%d cards -> %s (%.2f MB)", len(cards), args.out, args.out.stat().st_size / 1e6)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
