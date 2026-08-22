#!/usr/bin/env python3
"""The human pass over Open Images: what form factor is each box?

    python ml/scripts/label_open_images.py fetch
    python ml/scripts/label_open_images.py label --reviewer alex
    python ml/scripts/label_open_images.py report

**Why this exists, and what it is worth.** `docs/research/11-open-images-form-factors.md`
already asked whether a second adjudication pass over this corpus is worth
anybody's time, and answered it from a frozen 384-box survey:

    "A second adjudication pass over Open Images is worth it for `street_basket`
     and for reinforcing the wheelies, and for nothing else. It cannot produce
     `underground`, `textile_bank` or `wall_unit` at all."

So read the yield before spending an evening on it. `street_basket` was 35.2 % of
the survey - roughly 600-700 boxes across the corpus - against **one** crop in the
legacy archive, which is why P1 has to drop the class. The three empty form
factors were **0 of 384**; Open Images' vocabulary does not contain underground
drop columns, clothing banks or wall units, and no amount of labelling invents
them. Whether a class the pack answers with one fixed sentence is *worth* 600
training crops is a product judgement and it is the maintainer's.

**Why a second tool rather than adjudicate.py.** That script is bound to the
legacy pool: it reads `crop_records` from a manifest that has them, orders by
`capture_cluster`, and compares against the archive's shipped stream->shape
proposals. Open Images has none of those. Boxes come from YOLO label files, there
are no clusters, and - the one genuinely nice part - there are **no proposals at
all**, so this pass is blind by construction rather than by a flag somebody has
to remember to pass.

**The unit is the box, not the frame.** A frame with six bins holds six answers,
and `bins_in_frame >= 4` is the only place in the whole dataset those exist.

**`not_a_bin` is its own answer.** research/11 section 4 found 11 skips in 384 -
a French postbox among them, boxed as a waste container - and folded them into
`uncertain` because the survey had nowhere else to put them. That conflated "I
cannot tell what this is" with "I can tell, and it is not one of ours", which are
different facts about the corpus. They are separate here.

Decisions append to `<pool>/adjudication.json` after every keystroke, so the tab
can be closed at any point and reopened where it left off. Nothing is
overwritten and nothing is uploaded: stdlib `http.server` and one HTML string,
exactly as adjudicate.py does it.
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import logging
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
sys.path.insert(0, str(ML_ROOT / "src"))
sys.path.insert(0, str(ML_ROOT / "scripts"))

from survey_open_images import REPO, SUBSET, boxes_in, crop_of, fetch  # noqa: E402

from sbr.dataset.pool import layout_of  # noqa: E402
from sbr.taxonomy import load_taxonomy  # noqa: E402
from sbr.utils.hub import resolve_revision  # noqa: E402

logger = logging.getLogger("label-oi")

DEFAULT_POOL = REPO_ROOT / "data/open_images" / SUBSET
RECORD = "adjudication.json"

#: Not form factors. Kept out of the taxonomy on purpose - see the module note.
UNCERTAIN = "uncertain"
NOT_A_BIN = "not_a_bin"


# --------------------------------------------------------------------------- #
# the record
# --------------------------------------------------------------------------- #


def load_record(path: Path) -> dict:
    if not path.exists():
        return {"corpus": "open_images", "revision": None, "decisions": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_record(path: Path, record: dict) -> None:
    record["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def key_of(box: dict) -> str:
    """One box, named so a decision survives a re-download of the pool."""
    return f"{box['frame']}#{box['box_index']}"


# --------------------------------------------------------------------------- #
# the UI
# --------------------------------------------------------------------------- #

PAGE = """<!doctype html><meta charset=utf-8><title>Open Images form factors</title>
<style>
 body{font:15px system-ui;margin:0;background:#1b1d21;color:#eee}
 .wrap{display:flex;gap:24px;padding:18px;align-items:flex-start}
 .shot{flex:1;min-width:0;text-align:center}
 img{max-height:74vh;max-width:100%;background:#333;border-radius:6px}
 .keys{display:grid;grid-template-columns:auto 1fr;gap:7px 14px;align-content:start;min-width:290px}
 kbd{background:#000;padding:3px 9px;border-radius:4px;font:13px ui-monospace;color:#8fd}
 .meta{opacity:.65;font:12px ui-monospace;letter-spacing:.06em;text-transform:uppercase}
 .bar{height:4px;background:#333;border-radius:2px;margin:10px 0}
 .bar i{display:block;height:100%;background:#8fd;border-radius:2px}
 h1{font-size:17px;margin:0 0 2px}
 .sep{grid-column:1/-1;height:1px;background:#333;margin:6px 0}
 .tally{grid-column:1/-1;font:12px ui-monospace;opacity:.6;white-space:pre-wrap;line-height:1.5}
</style>
<div class=wrap>
  <div class=shot><img id=crop alt=""><div class=meta id=meta></div></div>
  <div>
    <h1>What is this?</h1>
    <div class=meta id=progress></div>
    <div class=bar><i id=fill style="width:0"></i></div>
    <div class=keys id=keys></div>
  </div>
</div>
<script>
let cur = null;
async function load() {
  const r = await fetch('/next');
  cur = await r.json();
  if (!cur.key) {
    document.getElementById('crop').removeAttribute('src');
    document.getElementById('progress').textContent = 'done - every box in the queue has an answer';
    document.getElementById('keys').innerHTML = '';
    return;
  }
  document.getElementById('crop').src = '/crop?k=' + encodeURIComponent(cur.key) + '&t=' + Date.now();
  document.getElementById('meta').textContent =
    cur.frame + ' / box ' + cur.box_index + ' - ' + cur.bins_in_frame + ' in frame';
  document.getElementById('progress').textContent = cur.done + ' of ' + cur.total;
  document.getElementById('fill').style.width = (100 * cur.done / cur.total) + '%';
  const rows = cur.options.map(o =>
    '<kbd>' + o.key + '</kbd><span>' + o.name + '</span>').join('');
  const extra = (cur.previous
    ? '<div class=sep></div><kbd>a</kbd><span>same as last (' + cur.previous + ')</span>'
    : '') + '<div class=sep></div><kbd>&larr;</kbd><span>undo the last one</span>' +
    '<div class="tally">' + cur.tally + '</div>';
  document.getElementById('keys').innerHTML = rows + extra;
}
async function decide(v) {
  if (!cur || !cur.key) return;
  await fetch('/set?k=' + encodeURIComponent(cur.key) + '&v=' + encodeURIComponent(v));
  load();
}
addEventListener('keydown', e => {
  if (!cur) return;
  if (e.key === 'ArrowLeft') { fetch('/undo').then(load); return; }
  if (e.key === 'a' && cur.previous) { decide(cur.previous); return; }
  const hit = (cur.options || []).find(o => o.key === e.key);
  if (hit) decide(hit.name);
});
load();
</script>
"""


def serve(pool: Path, reviewer: str, port: int) -> None:
    from PIL import Image

    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    layout = layout_of(manifest)

    boxes = boxes_in(pool, manifest)
    # Sorted, so the queue does not depend on the order the filesystem handed
    # back, and so the several boxes of one frame arrive together - which is what
    # makes "same as last" worth a key.
    boxes.sort(key=lambda b: (b["frame"], b["box_index"]))
    by_key = {key_of(b): b for b in boxes}

    classes = load_taxonomy().detector_classes
    keys = "1234567890"
    options = [{"key": keys[i], "name": name} for i, name in enumerate(classes)]
    options += [{"key": "u", "name": UNCERTAIN}, {"key": "x", "name": NOT_A_BIN}]

    path = pool / RECORD
    record = load_record(path)
    record["revision"] = manifest.get("revision") or record.get("revision")
    decided = {d["box"]: d for d in record["decisions"]}
    order: list[str] = [d["box"] for d in record["decisions"]]

    def tally() -> str:
        counts = collections.Counter(d["form_factor"] for d in record["decisions"])
        if not counts:
            return ""
        return "\n".join(f"{n:>4}  {name}" for name, n in counts.most_common())

    def next_task() -> dict:
        for box in boxes:
            k = key_of(box)
            if k in decided:
                continue
            return {
                "key": k,
                "frame": box["frame"],
                "box_index": box["box_index"],
                "bins_in_frame": box["bins_in_frame"],
                "options": options,
                "previous": decided[order[-1]]["form_factor"] if order else None,
                "done": len(decided),
                "total": len(boxes),
                "tally": tally(),
            }
        return {"key": None, "done": len(decided), "total": len(boxes), "tally": tally()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:  # noqa: D102 - quiet
            return

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            q = parse_qs(url.query)

            if url.path == "/":
                return self._send(PAGE.encode(), "text/html; charset=utf-8")

            if url.path == "/next":
                return self._send(json.dumps(next_task()).encode(), "application/json")

            if url.path == "/crop":
                box = by_key.get(q["k"][0])
                image = crop_of(pool, layout, box) if box else None
                if image is None:
                    return self.send_error(404)
                buffer = io.BytesIO()
                image.resize(_fit(image.size, 900), Image.LANCZOS).save(buffer, "JPEG", quality=88)
                return self._send(buffer.getvalue(), "image/jpeg")

            if url.path == "/set":
                k, verdict = q["k"][0], q["v"][0]
                if verdict not in {o["name"] for o in options}:
                    return self.send_error(400)
                entry = {
                    "box": k,
                    "frame": by_key[k]["frame"],
                    "box_index": by_key[k]["box_index"],
                    "form_factor": verdict,
                    "reviewer": reviewer,
                    "decided": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                decided[k] = entry
                order.append(k)
                record["decisions"] = [decided[key] for key in order]
                save_record(path, record)
                return self._send(b"{}", "application/json")

            if url.path == "/undo":
                if order:
                    decided.pop(order.pop(), None)
                    record["decisions"] = [decided[key] for key in order]
                    save_record(path, record)
                return self._send(b"{}", "application/json")

            self.send_error(404)

        def _send(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", port), Handler)
    logger.info("%d boxes, %d already decided, as %r", len(boxes), len(decided), reviewer)
    logger.info("http://127.0.0.1:%d - close the tab whenever; it resumes where it stopped", port)
    threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    server.serve_forever()


def _fit(size: tuple[int, int], longest: int) -> tuple[int, int]:
    """Upscale a small crop so a 40px bin is not judged at 40px."""
    width, height = size
    scale = longest / max(width, height)
    return (max(1, int(width * scale)), max(1, int(height * scale)))


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #


def report(pool: Path) -> dict:
    """What has been decided so far, against what the survey projected."""
    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    total = len(boxes_in(pool, manifest))
    record = load_record(pool / RECORD)
    counts = collections.Counter(d["form_factor"] for d in record["decisions"])
    n = sum(counts.values())

    classes = load_taxonomy().detector_classes
    return {
        "corpus": "open_images",
        "revision": record.get("revision"),
        "reviewers": sorted({d["reviewer"] for d in record["decisions"]}),
        "boxes_in_corpus": total,
        "boxes_decided": n,
        "fraction_decided": round(n / total, 4) if total else 0.0,
        "counts": {name: counts.get(name, 0) for name in [*classes, UNCERTAIN, NOT_A_BIN]},
        # research/11's frozen survey, for the reader who wants to know whether
        # this pass is landing where it was projected to.
        "survey_projection_note": (
            "docs/research/11: 384-box survey found street_basket 35.2%, wheelie_small 19.8%, "
            "uncertain 33.6%, and ZERO underground / textile_bank / wall_unit. This pass cannot "
            "produce those three; it is worth running for street_basket and wheelie reinforcement."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fetch", "label", "report"])
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--reviewer", default="alex")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "fetch":
        revision = resolve_revision(REPO, "main", strict=True)
        pool = fetch(revision, args.pool.parent)
        logger.info("pool at %s", pool)
        return 0

    if not (args.pool / "manifest.json").exists():
        raise SystemExit(f"no manifest at {args.pool} - run `fetch` first")

    if args.command == "label":
        serve(args.pool, args.reviewer, args.port)
        return 0

    payload = report(args.pool)
    out = args.out or (REPO_ROOT / "docs/research/probes/data/open-images-form-factors.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
