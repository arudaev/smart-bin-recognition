#!/usr/bin/env python3
"""docs/12 P3: label body and lid colour, then score the sampler against it.

    python ml/scripts/colour_labels.py sample     --pool data/legacy/pool
    python ml/scripts/colour_labels.py sheets     --pool data/legacy/pool --out <dir>
    python ml/scripts/colour_labels.py label      --pool data/legacy/pool --reviewer alex
    python ml/scripts/colour_labels.py spot-check --pool data/legacy/pool --reviewer alex -n 25
    python ml/scripts/colour_labels.py score      --pool data/legacy/pool --labeller alex

**Why this is not adjudicate.py.** That script is a localhost keystroke UI, and
it is the right shape for a person with a screen. It is useless to an agent, and
P3's labelling fell to an agent because the maintainer was away. So this tool has
two front doors onto **one** record: ``sheets`` renders contact sheets an agent
can read, ``label`` is the same blinded keystroke UI a person gets, and both
write rows to ``colour-labels.json`` tagged with **who wrote them**.

That tagging is the point. `labeller: claude` rows are recorded as
``provisional_proposals``; `score` refuses to report a settled number against
them and says PROVISIONAL instead. Two passes coexist in one file, and the
maintainer's rows win wherever both exist.

**The sample is frozen** - 160 crops, seed 20260821, stratified by capture
cluster - and ``sample`` is deterministic, so re-running it after labelling has
started cannot quietly change what was sampled. It refuses to overwrite a
different sample.

**Colour is measured from the FRAME, never the crop.** ``service/colour.py``
estimates the illuminant with shades-of-gray over the whole scene, and its own
docstring records that estimating from a crop turns every bin grey. So `score`
loads ``images/<frame>`` and cuts the box itself rather than reading
``crops/``.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import threading
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
sys.path.insert(0, str(ML_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "service"))

logger = logging.getLogger("colour_labels")

SAMPLE_FILE = "colour-sample.json"
LABELS_FILE = "colour-labels.json"

#: Frozen in docs/12 P3's 2026-08-22 amendment, before a label was written.
SEED = 20260821
SAMPLE_TOTAL = 160

#: The vocabulary is the taxonomy's, read from it rather than restated - a
#: second copy of the colour list is one more thing that can drift.
#: ``unsure`` is not a colour and is not in the taxonomy; it is the honest answer
#: for a crop nobody can call, and it is excluded from every scored denominator.
UNSURE = "unsure"
NOT_VISIBLE = "not_visible"


def colour_vocabulary() -> list[str]:
    from sbr.taxonomy import TAXONOMY_PATH

    raw = json.loads(Path(TAXONOMY_PATH).read_text(encoding="utf-8"))
    return [c["id"] for c in raw["colors"] if c.get("hex_ref")]


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def pool_index(pool: Path) -> tuple[dict[str, dict], dict[str, dict], dict[str, str]]:
    """crop file -> crop record, frame file -> frame record, crop -> form factor."""
    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    adjud = json.loads((pool / "adjudication.json").read_text(encoding="utf-8"))
    crops = {r["file"]: r for r in manifest["crop_records"]}
    frames = {r["file"]: r for r in manifest["records"]}
    factors = {d["file"]: d["form_factor"] for d in adjud["decisions"] if d.get("form_factor")}
    return crops, frames, factors


# --------------------------------------------------------------------------- #
# sample
# --------------------------------------------------------------------------- #


def draw_sample(pool: Path) -> dict[str, Any]:
    """The frozen 160. Deterministic, and stratified by capture cluster.

    **Why cluster-stratified rather than simple random.** The largest capture
    cluster in this pool holds 18 crops of one bin. A simple random sample would
    spend a ninth of its wheelie budget on a single object and then report the
    agreement of one lid as though it were many. Drawing round-robin over
    clusters spends the budget on distinct bins.
    """
    crops, _frames, factors = pool_index(pool)
    manifest_frames = {r["file"]: r for r in json.loads((pool / "manifest.json").read_text(encoding="utf-8"))["records"]}

    by_cluster: dict[str, list[str]] = defaultdict(list)
    for crop, factor in factors.items():
        cluster = manifest_frames[crops[crop]["frame"]].get("capture_cluster")
        by_cluster[f"{factor}::{cluster}"].append(crop)

    rng = random.Random(SEED)

    def take(pred, budget: int) -> list[str]:
        """Round-robin over matching clusters, one crop each pass."""
        keys = sorted(k for k in by_cluster if pred(k.split("::", 1)[0]))
        pools = {k: sorted(by_cluster[k]) for k in keys}
        for k in keys:
            rng.shuffle(pools[k])
        picked: list[str] = []
        while len(picked) < budget and any(pools.values()):
            for k in keys:
                if not pools[k]:
                    continue
                picked.append(pools[k].pop())
                if len(picked) >= budget:
                    break
        return picked

    igloo = take(lambda f: f == "igloo", 10**6)  # all of them
    basket = take(lambda f: f == "street_basket", 10**6)  # the single one
    wheelie = take(lambda f: f.startswith("wheelie"), SAMPLE_TOTAL - len(igloo) - len(basket))

    chosen = sorted(igloo + basket + wheelie)
    return {
        "probe": "P3",
        "frozen": "docs/12-validation-protocol.md, amended 2026-08-22, before any label",
        "seed": SEED,
        "requested": SAMPLE_TOTAL,
        "drawn": len(chosen),
        "stratification": "round-robin over (form_factor, capture_cluster), so one bin is not counted many times",
        "composition": dict(Counter(factors[c] for c in chosen)),
        "distinct_clusters": len({manifest_frames[crops[c]["frame"]].get("capture_cluster") for c in chosen}),
        "crops": chosen,
    }


# --------------------------------------------------------------------------- #
# sheets - the agent's front door
# --------------------------------------------------------------------------- #


def build_sheets(pool: Path, out: Path, per_sheet: int = 12, tile: int = 260) -> list[Path]:
    """Contact sheets of the sampled crops, each tile numbered.

    An agent has no screen and cannot press a key, but it can look at an image.
    Twelve numbered tiles per sheet turns 160 individual reads into fourteen.
    """
    import cv2
    import numpy as np

    sample = _load(pool / SAMPLE_FILE, None)
    if sample is None:
        raise SystemExit(f"no {SAMPLE_FILE} - run `sample` first")

    out.mkdir(parents=True, exist_ok=True)
    cols, rows = 4, (per_sheet + 3) // 4
    written: list[Path] = []

    for start in range(0, len(sample["crops"]), per_sheet):
        chunk = sample["crops"][start : start + per_sheet]
        # Mid grey, not black or white: the tiles carry the colours being judged
        # and a neutral surround is the one that biases none of them.
        sheet = np.full((rows * (tile + 26), cols * tile, 3), 128, np.uint8)
        for i, name in enumerate(chunk):
            img = cv2.imread(str(pool / "crops" / name))
            if img is None:
                continue
            h, w = img.shape[:2]
            scale = min(tile / w, tile / h)
            resized = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))))
            rh, rw = resized.shape[:2]
            r, c = divmod(i, cols)
            y0 = r * (tile + 26) + 26 + (tile - rh) // 2
            x0 = c * tile + (tile - rw) // 2
            sheet[y0 : y0 + rh, x0 : x0 + rw] = resized
            cv2.putText(
                sheet,
                f"{start + i:03d}",
                (c * tile + 6, r * (tile + 26) + 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
        path = out / f"sheet-{start // per_sheet:02d}.png"
        cv2.imwrite(str(path), sheet)
        written.append(path)

    (out / "index.json").write_text(
        json.dumps({"per_sheet": per_sheet, "crops": sample["crops"]}, indent=2), encoding="utf-8"
    )
    return written


def record_labels(pool: Path, labeller: str, rows: list[dict[str, Any]], provisional: bool) -> int:
    """Append or replace rows for one labeller. Never touches another's."""
    path = pool / LABELS_FILE
    store = _load(path, {"probe": "P3", "labels": []})
    vocab = set(colour_vocabulary()) | {UNSURE, NOT_VISIBLE}

    by_key = {(r["file"], r["labeller"]): r for r in store["labels"]}
    for row in rows:
        for field in ("body_color", "lid_color"):
            if row.get(field) not in vocab:
                raise SystemExit(f"{row['file']}: {field}={row.get(field)!r} is not in the vocabulary")
        row = {
            **row,
            "labeller": labeller,
            "provisional_proposals": provisional,
            "decided": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        by_key[(row["file"], labeller)] = row

    store["labels"] = sorted(by_key.values(), key=lambda r: (r["file"], r["labeller"]))
    store["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store["labellers"] = sorted({r["labeller"] for r in store["labels"]})
    store["provisional_labellers"] = sorted(
        {r["labeller"] for r in store["labels"] if r.get("provisional_proposals")}
    )
    _save(path, store)
    return len(rows)


# --------------------------------------------------------------------------- #
# score
# --------------------------------------------------------------------------- #


def score(pool: Path, labeller: str | None) -> dict[str, Any]:
    """P3's four body variants and the lid band, against the labels on file.

    The four variants are P3's, unchanged: whole crop, centre-weighted, centre
    with Gray World, centre with Shades of Gray p=6.
    """
    import colour as colour_mod
    import cv2
    import numpy as np

    crops, frames, factors = pool_index(pool)
    store = _load(pool / LABELS_FILE, {"labels": []})
    rows = [r for r in store["labels"] if labeller is None or r["labeller"] == labeller]
    if not rows:
        raise SystemExit("no labels to score against")

    # The maintainer's rows win wherever both exist.
    best: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: bool(r.get("provisional_proposals")), reverse=True):
        best[r["file"]] = r
    rows = list(best.values())

    provisional = any(r.get("provisional_proposals") for r in rows)

    # neutrals THAT THE VOCABULARY CANNOT SEPARATE. `grey` and `metal` are 8.7
    # delta-E apart - colour.py says so in a comment - and `white` sits close
    # behind. Collapsing them is not a way to make the score look better: the
    # pre-registered rule is scored STRICTLY, and this runs beside it as a
    # diagnostic that says WHERE the strict number went.
    neutrals = {"grey", "metal", "white"}

    def collapse(name: str | None) -> str | None:
        return "neutral" if name in neutrals else name

    variants = ("whole_crop", "centre", "centre_grayworld", "centre_shades_of_gray_p6")
    hits: dict[str, int] = dict.fromkeys(variants, 0)
    body_n = 0
    lid_hits = 0
    lid_n = 0
    lid_visible_wheelies = 0
    wheelies = 0
    lid_confusion: Counter = Counter()
    unmeasurable = dict.fromkeys(variants, 0)
    body_collapsed = 0
    lid_collapsed = 0
    body_confusion: Counter = Counter()
    # Measured CIELAB per labelled colour. This is what audits the REFERENCES:
    # if real bins of a colour cluster far from that colour's hex_ref, the
    # vocabulary is describing swatches rather than objects.
    measured_lab: dict[str, list] = defaultdict(list)
    # (cluster, truth, Lab) for the recalibration check below.
    body_samples: list[tuple[str, str, Any]] = []
    lid_samples: list[tuple[str, str, Any]] = []
    frame_records = frames

    for row in rows:
        name = row["file"]
        rec = crops[name]
        frame_path = pool / "images" / rec["frame"]
        frame = cv2.imread(str(frame_path))
        if frame is None:
            continue
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        h, w = frame_rgb.shape[:2]
        # `crop_px` is what legacy_import.py actually cut, so it reproduces the
        # stored crop exactly. Recomputing from `bbox_norm` lands within a couple
        # of pixels but there is no reason to prefer a reconstruction over the
        # record.
        x0, y0, x1, y1 = rec["crop_px"]
        crop = frame_rgb[max(0, y0) : min(h, y1), max(0, x0) : min(w, x1)]
        if crop.size == 0:
            continue

        # THE ILLUMINANT COMES FROM THE FRAME. This is the line the whole
        # measurement turns on; see service/colour.py:estimate_illuminant.
        gain_sog = colour_mod.estimate_illuminant(frame_rgb, p=colour_mod.SHADES_OF_GRAY_P)
        gain_gw = colour_mod.estimate_illuminant(frame_rgb, p=1.0)

        truth = row.get("body_color")
        if truth not in (UNSURE, NOT_VISIBLE, None):
            body_n += 1
            got = {
                "whole_crop": _name_of(colour_mod, crop, None, whole=True),
                "centre": _name_of(colour_mod, crop, None),
                "centre_grayworld": _name_of(colour_mod, crop, gain_gw),
                "centre_shades_of_gray_p6": _name_of(colour_mod, crop, gain_sog),
            }
            for v in variants:
                if got[v] is None:
                    unmeasurable[v] += 1
                elif got[v] == truth:
                    hits[v] += 1
            best_v = "centre_shades_of_gray_p6"
            body_confusion[f"{truth}->{got[best_v]}"] += 1
            if collapse(got[best_v]) == collapse(truth):
                body_collapsed += 1
            sample = colour_mod.apply_illuminant(colour_mod.centre_sample(crop), gain_sog)
            lab_body = colour_mod.srgb_to_lab(sample.mean(axis=0))
            measured_lab[truth].append(lab_body)
            body_samples.append((str(frame_records[rec["frame"]].get("capture_cluster")), truth, lab_body))

        if factors.get(name, "").startswith("wheelie"):
            wheelies += 1
            lid_truth = row.get("lid_color")
            if lid_truth not in (UNSURE, NOT_VISIBLE, None):
                lid_visible_wheelies += 1
                lid_n += 1
                lid_got, _de = colour_mod.measure_lid_colour(crop, gain_sog)
                lid_confusion[f"{lid_truth}->{lid_got}"] += 1
                if lid_got == lid_truth:
                    lid_hits += 1
                if collapse(lid_got) == collapse(lid_truth):
                    lid_collapsed += 1
                lid_lab = colour_mod.srgb_to_lab(
                    colour_mod.apply_illuminant(colour_mod.lid_sample(crop), gain_sog).mean(axis=0)
                )
                lid_samples.append((str(frame_records[rec["frame"]].get("capture_cluster")), lid_truth, lid_lab))

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 4) if den else None

    body = {v: rate(hits[v], body_n) for v in variants}
    winner = max((v for v in variants if body[v] is not None), key=lambda v: body[v], default=None)

    lid_agreement = rate(lid_hits, lid_n)
    if lid_agreement is None:
        verdict = "no scored lids"
    elif lid_agreement >= 0.75:
        verdict = "wire it through"
    elif lid_agreement >= 0.60:
        verdict = "wire it, bounded by delta-E, and call it marginal"
    else:
        verdict = "do not wire it - the pack matches on an axis this geometry cannot measure"

    # THE REFERENCE AUDIT. For each labelled colour, where do real bins of that
    # colour actually sit in CIELAB, and how far is that from the hex swatch the
    # taxonomy names them by?
    refs = colour_mod.named_colours()
    centroids = {}
    for name, labs in sorted(measured_lab.items()):
        centroid = np.mean(np.array(labs), axis=0)
        ref = refs.get(name)
        centroids[name] = {
            "n": len(labs),
            "measured_lab": [round(float(x), 1) for x in centroid],
            "reference_lab": [round(float(x), 1) for x in ref] if ref is not None else None,
            "delta_e_measured_to_reference": round(colour_mod.delta_e_2000(centroid, ref), 1)
            if ref is not None
            else None,
            "nearest_reference_to_the_measured_centroid": min(
                refs, key=lambda n: colour_mod.delta_e_2000(centroid, refs[n])
            ),
        }

    def recalibrated(samples: list[tuple[str, str, Any]]) -> dict[str, Any]:
        """What would the same geometry score against MEASURED references?

        **Leave-one-CLUSTER-out, not leave-one-out.** Plain LOO scores 0.91 on
        the body here, and it is inflated: 160 crops come from ~99 capture
        clusters and the largest holds eighteen photographs of one bin, so
        holding out a single crop leaves its near-duplicates in the fit. That is
        the memorisation P1 built GroupKFold to avoid, and it would be the same
        mistake with a different estimator.
        """
        if not samples:
            return {"n": 0}
        clusters = sorted({c for c, _t, _l in samples})
        hits = 0
        for held in clusters:
            train = [(t, lab) for c, t, lab in samples if c != held]
            test = [(t, lab) for c, t, lab in samples if c == held]
            cent: dict[str, Any] = {}
            for name in {t for t, _ in train}:
                cent[name] = np.mean(np.array([lab for t, lab in train if t == name]), axis=0)
            if not cent:
                continue
            for truth, lab in test:
                got = min(cent, key=lambda n: colour_mod.delta_e_2000(lab, cent[n]))
                hits += got == truth
        return {
            "n": len(samples),
            "held_out_groups": len(clusters),
            "agreement": round(hits / len(samples), 4),
            "protocol": "leave-one-capture-cluster-out; centroids refitted without the held-out cluster",
        }

    return {
        "probe": "P3",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labeller": labeller or "all",
        "PROVISIONAL": provisional,
        "provisional_note": (
            "scored against labels written by an agent (labeller: claude), recorded as "
            "provisional_proposals. P3 does NOT close on these. The maintainer pre-registered "
            "a 25-crop spot-check on return; quote no number here without the word PROVISIONAL"
        )
        if provisional
        else None,
        "n_labelled": len(rows),
        "body": {
            "n_scored": body_n,
            "agreement": body,
            "unmeasurable_above_max_delta_e": unmeasurable,
            "best_variant": winner,
            "confusion": dict(body_confusion.most_common()),
            "agreement_with_neutrals_collapsed": rate(body_collapsed, body_n),
            "decision_rule": "docs/12 P3: (2) or (3) within 5 points of the best means SAM leaves the critical path",
        },
        "lid": {
            "wheelies_in_sample": wheelies,
            "wheelies_with_a_visible_lid": lid_visible_wheelies,
            "lid_visible_fraction": rate(lid_visible_wheelies, wheelies),
            "n_scored": lid_n,
            "agreement": lid_agreement,
            "confusion": dict(lid_confusion.most_common()),
            "band_fraction": colour_mod.LID_BAND_FRACTION,
            "width_fraction": colour_mod.LID_WIDTH_FRACTION,
            "agreement_with_neutrals_collapsed": rate(lid_collapsed, lid_n),
            "decision_rule": "docs/12 P3 amended 2026-08-22: >=0.75 wire it, 0.60-0.75 marginal, <0.60 do not",
            "verdict": verdict,
        },
        "reference_audit": {
            "what_this_is": (
                "where real bins of each labelled colour actually sit in CIELAB, against the "
                "hex_ref the taxonomy names them by. A large delta_e here means the vocabulary "
                "is describing paint swatches rather than weathered objects under overcast light"
            ),
            "neutrals_that_cannot_be_separated": sorted(neutrals),
            "centroids": centroids,
            "if_the_references_were_recalibrated": {
                "what_this_is": (
                    "the SAME sampling geometry, scored against centroids measured from real bins "
                    "instead of the taxonomy's hex_ref, leave-one-capture-cluster-out. It separates "
                    "'the geometry is wrong' from 'the reference colours are wrong'"
                ),
                "body": recalibrated(body_samples),
                "lid": recalibrated(lid_samples),
                "this_is_not_a_proposal": (
                    "changing hex_ref changes every resolution outcome in every region pack, so it "
                    "is a taxonomy decision and the maintainer's. This measures what it would buy"
                ),
            },
        },
    }


def _name_of(colour_mod, crop, gain, whole: bool = False) -> str | None:
    import numpy as np

    if whole:
        sample = crop.reshape(-1, 3).astype(np.float64) / 255.0
        if gain is not None:
            sample = colour_mod.apply_illuminant(sample, gain)
        lab = colour_mod.srgb_to_lab(sample.mean(axis=0))
        distances = {n: colour_mod.delta_e_2000(lab, ref) for n, ref in colour_mod.named_colours().items()}
        best = min(distances, key=lambda n: distances[n])
        return None if distances[best] > colour_mod.MAX_DELTA_E else best
    name, _de = colour_mod.measure_body_colour(crop, gain)
    return name


# --------------------------------------------------------------------------- #
# label / spot-check - the human's front door
# --------------------------------------------------------------------------- #

PAGE = """<!doctype html><meta charset=utf-8><title>P3 colour</title>
<style>
 body{font:15px system-ui;margin:0;background:#808080;color:#fff}
 .wrap{display:flex;gap:24px;padding:20px}
 img{max-height:70vh;background:#808080}
 .keys{display:grid;grid-template-columns:repeat(2,auto);gap:6px 18px}
 kbd{background:#222;padding:2px 7px;border-radius:4px}
 .done{opacity:.7}
 h2{margin:.2em 0}
</style>
<div class=wrap>
 <div><img id=img><div id=meta class=done></div></div>
 <div>
  <h2 id=field>body colour</h2>
  <div class=keys id=keys></div>
  <p class=done id=progress></p>
 </div>
</div>
<script>
let state=null;
const KEYS={};
async function load(){state=await (await fetch('/next')).json();draw();}
function draw(){
 if(!state.file){document.body.innerHTML='<h1 style="padding:40px">done</h1>';return;}
 img.src='/crop?f='+encodeURIComponent(state.file)+'&t='+Date.now();
 field.textContent=state.field==='body'?'BODY colour':'LID colour';
 meta.textContent=state.file+'  -  '+state.form_factor;
 progress.textContent=state.done+' / '+state.total;
 keys.innerHTML='';
 state.options.forEach((o,i)=>{
  const k=o.key,d=document.createElement('div');
  d.innerHTML='<kbd>'+k+'</kbd> '+o.name;keys.appendChild(d);KEYS[k]=o.name;});
}
addEventListener('keydown',async e=>{
 const v=KEYS[e.key];if(!v)return;
 await fetch('/set?f='+encodeURIComponent(state.file)+'&field='+state.field+'&v='+encodeURIComponent(v));
 load();
});
load();
</script>"""


def serve(pool: Path, reviewer: str, subset: list[str] | None, port: int = 8766) -> None:
    """The keystroke UI. One field at a time, body then lid, blinded.

    Blinded means the machine's guess is never shown. adjudicate.py learned this
    the expensive way: the pool's shipped proposals turned out wrong on 116 of
    403 crops, and a primed reviewer would have confirmed them.
    """
    import cv2

    crops, _frames, factors = pool_index(pool)
    sample = _load(pool / SAMPLE_FILE, None)
    if sample is None:
        raise SystemExit(f"no {SAMPLE_FILE} - run `sample` first")
    queue = subset if subset is not None else sample["crops"]

    vocab = colour_vocabulary()
    keys = "1234567890qwerty"
    options = [{"key": keys[i], "name": n} for i, n in enumerate(vocab)]
    body_opts = options + [{"key": "u", "name": UNSURE}]
    lid_opts = options + [{"key": "u", "name": UNSURE}, {"key": "n", "name": NOT_VISIBLE}]

    store = _load(pool / LABELS_FILE, {"probe": "P3", "labels": []})
    mine = {r["file"]: dict(r) for r in store["labels"] if r["labeller"] == reviewer}

    def next_task() -> dict[str, Any]:
        for f in queue:
            row = mine.get(f, {})
            if "body_color" not in row:
                return {"file": f, "field": "body", "options": body_opts,
                        "form_factor": factors.get(f, "?"),
                        "done": len(mine), "total": len(queue)}
            if factors.get(f, "").startswith("wheelie") and "lid_color" not in row:
                return {"file": f, "field": "lid", "options": lid_opts,
                        "form_factor": factors.get(f, "?"),
                        "done": len(mine), "total": len(queue)}
        return {"file": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):  # noqa: A003 - quiet
            pass

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            q = parse_qs(url.query)
            if url.path == "/":
                return self._send(PAGE.encode(), "text/html; charset=utf-8")
            if url.path == "/next":
                return self._send(json.dumps(next_task()).encode(), "application/json")
            if url.path == "/crop":
                data = cv2.imencode(".png", cv2.imread(str(pool / "crops" / q["f"][0])))[1].tobytes()
                return self._send(data, "image/png")
            if url.path == "/set":
                f, field, v = q["f"][0], q["field"][0], q["v"][0]
                row = mine.setdefault(f, {"file": f})
                row[f"{field}_color"] = v
                if field == "body" and not factors.get(f, "").startswith("wheelie"):
                    row.setdefault("lid_color", NOT_VISIBLE)
                record_labels(pool, reviewer, [row], provisional=False)
                return self._send(b"{}", "application/json")
            self.send_error(404)

        def _send(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", port), Handler)
    logger.info("reviewing %d crops as %r on http://127.0.0.1:%d", len(queue), reviewer, port)
    threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    server.serve_forever()


# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["sample", "sheets", "label", "spot-check", "score"])
    parser.add_argument("--pool", type=Path, default=REPO_ROOT / "data/legacy/pool")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--reviewer", default="alex")
    parser.add_argument("--labeller")
    parser.add_argument("-n", type=int, default=25)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pool: Path = args.pool

    if args.command == "sample":
        drawn = draw_sample(pool)
        path = pool / SAMPLE_FILE
        existing = _load(path, None)
        if existing and existing["crops"] != drawn["crops"]:
            raise SystemExit(
                f"{path} already holds a DIFFERENT sample. The sample is frozen; refusing to replace it."
            )
        _save(path, drawn)
        logger.info("%d crops, %d clusters, %s", drawn["drawn"], drawn["distinct_clusters"], drawn["composition"])
        logger.info("wrote %s", path)
        return 0

    if args.command == "sheets":
        out = args.out or (pool / "colour-sheets")
        written = build_sheets(pool, out)
        logger.info("wrote %d sheets to %s", len(written), out)
        return 0

    if args.command == "label":
        serve(pool, args.reviewer, None, args.port)
        return 0

    if args.command == "spot-check":
        sample = _load(pool / SAMPLE_FILE, None)
        if sample is None:
            raise SystemExit(f"no {SAMPLE_FILE} - run `sample` first")
        # A DIFFERENT seed from the sample's, so the spot-check is not a
        # deterministic function of the thing it is checking.
        rng = random.Random(SEED + 1)
        subset = sorted(rng.sample(sample["crops"], min(args.n, len(sample["crops"]))))
        logger.info("spot-checking %d crops as %r - these overwrite nothing but your own rows", len(subset), args.reviewer)
        serve(pool, args.reviewer, subset, args.port)
        return 0

    if args.command == "score":
        report = score(pool, args.labeller)
        out = args.out or (REPO_ROOT / "docs/research/probes/data/P3-colour-measurement.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        _save(out, report)
        logger.info(json.dumps(report["body"], indent=2))
        logger.info(json.dumps(report["lid"], indent=2))
        if report["PROVISIONAL"]:
            logger.info("")
            logger.info("*** PROVISIONAL - agent labels. P3 does not close on this. ***")
        logger.info("wrote %s", out)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
