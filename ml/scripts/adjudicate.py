#!/usr/bin/env python3
"""The human pass: decide the form factor of each crop, by cluster, one key each.

    python ml/scripts/adjudicate.py --pool data/legacy/pool
    python ml/scripts/adjudicate.py --pool data/legacy/pool --reviewer alex

Opens a page on localhost. Nothing is uploaded, nothing is installed, and there
is no notebook: this is stdlib ``http.server`` and one HTML string.

**Why this exists.** The legacy labels are waste *streams* – Biomüll, Glas,
Papier, Restmüll – and the identifier's classes are physical *form factors*. A
stream does not determine a shape: the same Restmüll is a small wheelie bin
outside a house and a large one behind a block of flats. No mapping table can
close that gap, so a person looks at the picture. It is roughly 400 decisions,
most of them one keystroke, and it is the only irreplaceable step in the phase.

**Why by cluster.** Crops are ordered so that near-identical bins sit together:
by capture cluster first – one visit to one bin, reconstructed from EXIF times –
then by legacy class. Consecutive frames of the same bin get the same answer, so
`A` applies the current answer to the rest of the cluster in one key.

Decisions append to ``<pool>/adjudication.json`` after every keystroke, so the
tab can be closed at any point and reopened where it left off. Nothing is
overwritten: the file is the record of who decided what, and when.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.taxonomy import load_taxonomy  # noqa: E402

logger = logging.getLogger("adjudicate")

DECISIONS_FILE = "adjudication.json"


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #


class Review:
    """The crop queue and the decisions taken on it."""

    def __init__(self, pool: Path, reviewer: str) -> None:
        self.pool = pool
        self.reviewer = reviewer
        self.manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
        self.classes = load_taxonomy().detector_classes

        frames = {r["file"]: r for r in self.manifest["records"]}
        crops = list(self.manifest.get("crop_records", []))
        for crop in crops:
            frame = frames.get(crop["frame"], {})
            crop["_cluster"] = frame.get("capture_cluster", "")
            crop["_annotator"] = frame.get("annotator") or ""

        # Cluster first, then legacy class, so visually near-identical bins are
        # adjacent and "apply to the rest of this cluster" is one key.
        self.queue = sorted(
            crops, key=lambda c: (c["_cluster"], c["legacy_class"], c["file"])
        )
        self.decisions: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self.pool / DECISIONS_FILE

    def _load(self) -> None:
        if self.path.exists():
            for entry in json.loads(self.path.read_text(encoding="utf-8"))["decisions"]:
                self.decisions[entry["file"]] = entry
            logger.info("resuming: %d decisions already recorded", len(self.decisions))

    def save(self) -> None:
        payload = {
            "pool": str(self.pool),
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reviewer": self.reviewer,
            "classes": self.classes,
            "decisions": list(self.decisions.values()),
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def record(self, file: str, verdict: str, form_factor: str | None) -> None:
        crop = next((c for c in self.queue if c["file"] == file), None)
        if crop is None:
            raise KeyError(file)
        if verdict not in ("confirmed", "corrected", "rejected"):
            raise ValueError(f"{verdict!r} is not a verdict")
        if verdict != "rejected" and form_factor not in self.classes:
            raise ValueError(f"{form_factor!r} is not a form factor")

        proposed = crop.get("form_factor_proposed")
        if verdict != "rejected":
            # Derived, not taken on trust. Whether the pre-fill was right is a
            # measurement - if most decisions turn out to be corrections the
            # proposal is not helping - and a caller must not be able to record
            # a correction as a confirmation, by mistake or otherwise.
            verdict = "confirmed" if form_factor == proposed else "corrected"

        self.decisions[file] = {
            "file": file,
            "frame": crop["frame"],
            "legacy_class": crop["legacy_class"],
            "proposed": proposed,
            "adjudication": verdict,
            "form_factor": form_factor if verdict != "rejected" else None,
            "reviewer": self.reviewer,
            "decided": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.save()

    def cluster_of(self, file: str) -> list[str]:
        crop = next((c for c in self.queue if c["file"] == file), None)
        if crop is None:
            return []
        return [
            c["file"] for c in self.queue
            if c["_cluster"] == crop["_cluster"] and c["legacy_class"] == crop["legacy_class"]
        ]

    def state(self) -> dict[str, Any]:
        return {
            "classes": self.classes,
            "reviewer": self.reviewer,
            "total": len(self.queue),
            "done": len(self.decisions),
            "queue": [
                {
                    "file": c["file"],
                    "frame": c["frame"],
                    "legacy_class": c["legacy_class"],
                    "stream": c.get("deggendorf_stream"),
                    "candidates": c.get("form_factor_candidates", []),
                    "proposed": c.get("form_factor_proposed"),
                    "note": c.get("adjudication_note", ""),
                    "cluster": c["_cluster"],
                    "annotator": c["_annotator"],
                    "bins_in_frame": c.get("bins_in_frame", 1),
                    "decision": self.decisions.get(c["file"]),
                }
                for c in self.queue
            ],
        }


def apply_decisions(pool: Path) -> dict[str, int]:
    """Fold ``adjudication.json`` back into the manifest. Returns a summary.

    Kept separate from the reviewing so the record of who decided what survives
    independently of the derived manifest, and so re-importing never silently
    discards a human's work.
    """
    decisions_path = pool / DECISIONS_FILE
    if not decisions_path.exists():
        raise SystemExit(f"no decisions at {decisions_path} - nothing to apply")

    decisions = {
        entry["file"]: entry
        for entry in json.loads(decisions_path.read_text(encoding="utf-8"))["decisions"]
    }
    manifest_path = pool / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    applied = rejected = untouched = 0
    for crop in manifest.get("crop_records", []):
        entry = decisions.get(crop["file"])
        if entry is None:
            untouched += 1
            continue
        crop["adjudication"] = entry["adjudication"]
        crop["form_factor"] = entry["form_factor"]
        crop["adjudicated_by"] = entry["reviewer"]
        crop["adjudicated_at"] = entry["decided"]
        crop["label_origin"] = "human"
        if entry["adjudication"] == "rejected":
            rejected += 1
        else:
            applied += 1

    manifest["crops_pending_adjudication"] = untouched
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {"applied": applied, "rejected": rejected, "still_pending": untouched}
    logger.info("applied decisions: %s", summary)
    return summary


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #

PAGE = """<!doctype html>
<meta charset="utf-8"><title>Form-factor adjudication</title>
<style>
 :root { color-scheme: light dark; --gap: 12px; }
 body { font: 15px/1.5 system-ui, sans-serif; margin: 0; display: grid;
        grid-template-rows: auto 1fr auto; height: 100vh; }
 header, footer { padding: 10px 16px; border-block: 1px solid #8888; }
 header { display: flex; gap: 16px; align-items: baseline; flex-wrap: wrap; }
 main { display: grid; grid-template-columns: 1fr 320px; gap: var(--gap);
        padding: var(--gap); min-height: 0; }
 #stage { display: grid; place-items: center; min-height: 0; }
 #crop { max-width: 100%; max-height: 100%; object-fit: contain; }
 ul { list-style: none; margin: 0; padding: 0; }
 li { padding: 6px 8px; border-radius: 6px; display: flex; gap: 8px; }
 li.pick { background: #8882; }
 kbd { font: 12px monospace; border: 1px solid #8888; border-radius: 4px;
       padding: 0 5px; min-width: 1.2em; text-align: center; }
 .muted { opacity: .65; }
 .done { color: #2a2; } .todo { color: #c70; }
 progress { width: 220px; }
</style>
<header>
 <strong>Form factor</strong>
 <span id="pos" class="muted"></span>
 <progress id="bar" max="1" value="0"></progress>
 <span id="count" class="muted"></span>
 <span id="who" class="muted"></span>
</header>
<main>
 <div id="stage"><img id="crop" alt="crop awaiting adjudication"></div>
 <div>
  <p class="muted" id="context"></p>
  <ul id="options"></ul>
  <p class="muted"><kbd>A</kbd> apply to the rest of this cluster &middot;
     <kbd>X</kbd> not a bin &middot; <kbd>&larr;</kbd><kbd>&rarr;</kbd> move &middot;
     <kbd>U</kbd> next undecided</p>
  <p class="muted" id="note"></p>
 </div>
</main>
<footer class="muted" id="status">loading&hellip;</footer>
<script>
let S = null, i = 0;

async function load() {
  S = await (await fetch('/state')).json();
  i = Math.max(0, S.queue.findIndex(c => !c.decision));
  if (i < 0) i = 0;
  render();
}

function current() { return S.queue[i]; }

function render() {
  const c = current();
  if (!c) return;
  document.getElementById('crop').src = '/crop/' + encodeURIComponent(c.file);
  document.getElementById('pos').textContent = (i + 1) + ' / ' + S.total;
  document.getElementById('bar').max = S.total;
  document.getElementById('bar').value = S.done;
  document.getElementById('count').textContent = S.done + ' decided, ' + (S.total - S.done) + ' to go';
  document.getElementById('who').textContent = 'reviewer: ' + S.reviewer;
  document.getElementById('context').innerHTML =
    'legacy class <b>' + c.legacy_class + '</b> &middot; stream <b>' + c.stream + '</b><br>' +
    'cluster ' + c.cluster + ' &middot; ' + c.annotator +
    ' &middot; ' + c.bins_in_frame + ' bin(s) in frame';
  document.getElementById('note').textContent = c.note || '';

  // Candidates first and numbered, then every other form factor, so the common
  // case is one key and the rare case is still reachable without a mouse.
  const rest = S.classes.filter(f => !c.candidates.includes(f));
  const ordered = c.candidates.concat(rest);
  const keys = '123456789abcdefghij';
  document.getElementById('options').innerHTML = ordered.map((f, n) => {
    const chosen = c.decision && c.decision.form_factor === f;
    return '<li class="' + (chosen ? 'pick' : '') + '">' +
      '<kbd>' + keys[n] + '</kbd><span>' + f +
      (f === c.proposed ? ' <span class="muted">(proposed)</span>' : '') +
      (chosen ? ' &check;' : '') + '</span></li>';
  }).join('');

  const d = c.decision;
  document.getElementById('status').innerHTML = d
    ? '<span class="done">' + d.adjudication + ': ' + (d.form_factor || 'not a bin') + '</span>'
    : '<span class="todo">undecided</span>';
}

async function decide(form_factor, verdict, spread) {
  const c = current();
  await fetch('/decide', {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({file: c.file, form_factor, verdict, spread: !!spread})
  });
  S = await (await fetch('/state')).json();
  if (i < S.total - 1) i++;
  render();
}

addEventListener('keydown', e => {
  const c = current();
  if (!c) return;
  const rest = S.classes.filter(f => !c.candidates.includes(f));
  const ordered = c.candidates.concat(rest);
  const keys = '123456789abcdefghij';
  const k = e.key.toLowerCase();

  if (k === 'arrowright') { if (i < S.total - 1) i++; render(); return; }
  if (k === 'arrowleft')  { if (i > 0) i--; render(); return; }
  if (k === 'u') { const n = S.queue.findIndex(x => !x.decision); if (n >= 0) i = n; render(); return; }
  if (k === 'x') { decide(null, 'rejected'); return; }
  if (k === 'a') { const d = c.decision; if (d) decide(d.form_factor, d.adjudication, true); return; }
  if (k === 'enter' && c.proposed) { decide(c.proposed, 'confirmed'); return; }

  const n = keys.indexOf(k);
  if (n >= 0 && n < ordered.length) {
    const f = ordered[n];
    decide(f, f === c.proposed ? 'confirmed' : 'corrected');
  }
});

load();
</script>
"""


class Handler(BaseHTTPRequestHandler):
    review: Review

    def log_message(self, *args) -> None:  # noqa: A003 - quieten the default logger
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's interface
        route = urlparse(self.path)
        if route.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif route.path == "/state":
            self._send(200, json.dumps(self.review.state()).encode("utf-8"), "application/json")
        elif route.path.startswith("/crop/"):
            name = Path(route.path[len("/crop/"):]).name  # never leaves the pool
            image = self.review.pool / "crops" / name
            if not image.exists():
                self._send(404, b"no such crop", "text/plain")
                return
            self._send(200, image.read_bytes(), "image/jpeg")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/decide":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")

        targets = (
            self.review.cluster_of(payload["file"])
            if payload.get("spread")
            else [payload["file"]]
        )
        try:
            for file in targets:
                self.review.record(file, payload["verdict"], payload.get("form_factor"))
        except (KeyError, ValueError) as error:
            self._send(400, str(error).encode("utf-8"), "text/plain")
            return
        self._send(200, json.dumps({"decided": len(targets)}).encode("utf-8"), "application/json")


def serve(review: Review, port: int, open_browser: bool = True) -> None:
    Handler.review = review
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    remaining = review.state()["total"] - review.state()["done"]
    print(f"adjudication on {url}  ({remaining} crops still to decide)")
    print("decisions save after every keystroke; close the tab whenever you like")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nstopped. {review.state()['done']} decisions in {review.path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", type=Path, default=Path("data/legacy/pool"))
    parser.add_argument("--reviewer", default="maintainer")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="fold adjudication.json back into the manifest and exit",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.apply:
        summary = apply_decisions(args.pool)
        print(json.dumps(summary, indent=2))
        return

    serve(Review(args.pool, args.reviewer), args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
