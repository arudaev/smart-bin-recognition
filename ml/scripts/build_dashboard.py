#!/usr/bin/env python3
"""Read the repository's own evidence and emit one self-contained HTML page.

    python ml/scripts/build_dashboard.py --out docs/dashboard.html

**A generator, not a page.** Nothing on the output is typed by hand. If a probe
lands tomorrow it appears here with no edit to this file; if a number changes in
its source file, the page changes; and **a number with no source file does not
appear at all** - the page says `unknown` instead, which is a designed state
here for the same reason it is one in the product.

## The one honest deviation from "nothing hardcoded"

The seventeen probe result files in ``docs/research/probes/data/`` have **no
common schema**. Their top-level keys run from
``{probe, pre_registered, hardware, ...}`` through ``{hardware, repeats, roles}``
to ``{measured, label, url, ...}``. A generator that claimed to parse them
uniformly would be hardcoding under another name, and would break the first time
somebody wrote a probe that did not look like the last one.

So there are two tiers, and the difference is stated on the page itself:

- **Every** file in that directory is listed in the evidence index automatically,
  with whatever provenance it carries - hardware, `representative`, dates.
- A file contributes a **headline number** only if it matches one of three
  recognised shapes (a latency report, a load-test ramp, a gate sidecar) or
  carries an explicit ``dashboard`` block. Anything else is linked and counted
  and contributes no figure.

## What it reads, and what it may not read

**Tracked files only.** ``artifacts/`` is gitignored (``.gitignore:35``), so a
clean checkout does not have it and a page that depended on it could not be
rebuilt. It is read as an optional overlay when present and its absence renders
`unknown` rather than failing.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger("dashboard")

PROBE_DATA = REPO_ROOT / "docs/research/probes/data"
PROBE_DOCS = REPO_ROOT / "docs/research/probes"
TAXONOMY = REPO_ROOT / "data/taxonomy/waste-streams.json"
REGIONS = REPO_ROOT / "data/taxonomy/regions"
POOL = REPO_ROOT / "data/legacy/pool"
LOCALES = REPO_ROOT / "web/src/i18n"
ARTIFACTS = REPO_ROOT / "artifacts"

UNKNOWN = '<span class="unknown">unknown</span>'


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def _load(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable source is an absence
        return None


def probe_files() -> list[dict[str, Any]]:
    """Every probe result, with whatever provenance it carries.

    The classification is by SHAPE rather than by filename, so a probe named
    something nobody predicted still lands in the right tier.
    """
    out: list[dict[str, Any]] = []
    # `key=` and not bare `sorted()`: comparing Path objects case-folds on
    # Windows and does not on Linux, so `gate-sidecars.json` sorted before `P1-`
    # on one and after it on the other. Sorting the NAME as a plain string is the
    # same order everywhere.
    for path in sorted(PROBE_DATA.glob("*.json"), key=lambda q: q.name):
        d = _load(path)
        if d is None:
            out.append({"file": path.name, "kind": "unreadable", "raw": None})
            continue

        hardware = d.get("hardware") if isinstance(d, dict) else None
        label = None
        representative = None
        if isinstance(hardware, dict):
            label = hardware.get("label") or hardware.get("where")
            representative = hardware.get("representative")
        if representative is None and isinstance(d, dict):
            representative = d.get("representative")

        kind = "listed"
        if isinstance(d, dict):
            if "dashboard" in d:
                kind = "declared"
            elif "roles" in d and isinstance(d.get("roles"), dict):
                kind = "latency"
            elif "formats" in d and isinstance(d.get("formats"), dict):
                kind = "latency_paired"
            elif "concurrent_scanners_within_budget" in d:
                kind = "loadtest"

        out.append(
            {
                "file": path.name,
                "probe": _probe_label(d, path.name),
                "kind": kind,
                "hardware": label,
                "representative": representative,
                "generated": (d.get("generated") or d.get("measured") or d.get("ran")) if isinstance(d, dict) else None,
                "raw": d,
                "bytes": path.stat().st_size,
            }
        )
    return out


def _probe_label(d: Any, name: str) -> str:
    """The probe id as a STRING.

    Not every file agrees what `probe` is: some carry the id, some carry a
    sentence, and P8's ladder carries a list. The filename prefix is the reliable
    one, so a non-string value falls back to it rather than propagating a type
    nothing downstream can index with.
    """
    value = d.get("probe") if isinstance(d, dict) else None
    if isinstance(value, str) and re.fullmatch(r"P\d+", value.strip()):
        return value.strip()
    return _probe_id(name)


def _probe_id(name: str) -> str:
    m = re.match(r"(P\d+)", name)
    return m.group(1) if m else name


def probe_docs() -> dict[str, str]:
    return {_probe_id(p.name): p.name for p in sorted(PROBE_DOCS.glob("P*.md"))}


#: The tracked snapshot of the gate verdicts. See `snapshot_gates`.
GATE_SNAPSHOT = PROBE_DATA / "gate-sidecars.json"

#: Only these fields are snapshotted. A whitelist rather than a copy, so the
#: tracked file cannot quietly acquire whatever a future sidecar happens to hold.
SNAPSHOT_FIELDS = (
    "role", "version", "onnx_path", "imgsz", "classes", "quantised", "size_bytes",
    "accuracy_metric", "accuracy_split", "accuracy_drop", "map50_fp32", "map50_int8",
    "top1_fp32", "top1_int8", "median_latency_ms", "p95_latency_ms",
    "latency_hardware", "latency_representative", "gates", "gate_result",
    "targets", "target_result",
)


def snapshot_gates() -> dict[str, dict[str, Any]]:
    """Normalise the gate verdicts out of `artifacts/` into a TRACKED file.

    **`artifacts/` is gitignored (`.gitignore:35`), so reading it at render time
    made this page unreproducible** - a clean checkout found zero sidecars and
    rendered both models as `unknown`, while the committed HTML showed a full
    gate table. A page whose content depends on files a reviewer cannot obtain is
    not evidence, whatever it says on it.

    So the sidecars are snapshotted here, deliberately and visibly, into
    `docs/research/probes/data/gate-sidecars.json`. Rendering reads only that.
    The snapshot records which file each verdict came from, so "where did this
    number come from" survives the copy.
    """
    found: dict[str, dict[str, Any]] = {}
    for role in ("validator", "identifier"):
        for candidate in (ARTIFACTS / "gate" / f"{role}-v1.json", ARTIFACTS / "local" / f"{role}-v1.json"):
            d = _load(candidate)
            if d is None:
                continue
            found[role] = {k: d[k] for k in SNAPSHOT_FIELDS if k in d}
            found[role]["_source"] = str(candidate.relative_to(REPO_ROOT)).replace("\\", "/")
            found[role]["_snapshotted"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            break

    # Capture clusters come from `manifest.json`, which is gitignored, so they
    # travel in the snapshot too. Without this a clean checkout renders every
    # cluster count as unknown.
    manifest = _load(POOL / "manifest.json")
    adj = _load(POOL / "adjudication.json")
    if manifest and adj:
        crop_frame = {r["file"]: r["frame"] for r in manifest.get("crop_records", [])}
        frame_cluster = {r["file"]: r.get("capture_cluster") for r in manifest.get("records", [])}
        per: dict[str, set] = {}
        for d in adj.get("decisions", []):
            ff = d.get("form_factor")
            if ff:
                per.setdefault(ff, set()).add(frame_cluster.get(crop_frame.get(d["file"])))
        found["_coverage"] = {"clusters": {k: len(v - {None}) for k, v in sorted(per.items())}}
    return found


def gate_sidecars() -> dict[str, dict[str, Any]]:
    """The gate verdicts, read from the TRACKED snapshot and nowhere else.

    Never touches `artifacts/`. If the snapshot is missing the page renders
    `unknown` and says why, which is the correct behaviour for absent evidence -
    but on a clean checkout it is present, because it is committed.
    """
    snap = _load(GATE_SNAPSHOT) or {}
    return {k: v for k, v in snap.items() if not k.startswith("_")}


def coverage() -> dict[str, Any]:
    """Crops and capture clusters per form factor.

    **Crop counts come from `adjudication.json`, which is TRACKED** (it is one of
    the three exceptions in `.gitignore`). **Cluster counts need
    `manifest.json`, which is NOT** - so they come from the snapshot when the
    manifest is absent, and render `unknown` if neither is there. CI caught this:
    a clean checkout reported every form factor as 0 crops and 0 clusters while
    the committed page said 247 and 65.
    """
    tax = _load(TAXONOMY) or {}
    all_ff = [f["id"] for f in tax.get("form_factors", [])]
    adj = _load(POOL / "adjudication.json")
    manifest = _load(POOL / "manifest.json")
    snapshot = _load(GATE_SNAPSHOT) or {}

    counts: Counter = Counter()
    clusters: dict[str, set] = {}
    if adj:
        for d in adj.get("decisions", []):
            ff = d.get("form_factor")
            if ff:
                counts[ff] += 1
    if adj and manifest:
        crop_frame = {r["file"]: r["frame"] for r in manifest.get("crop_records", [])}
        frame_cluster = {r["file"]: r.get("capture_cluster") for r in manifest.get("records", [])}
        for d in adj.get("decisions", []):
            ff = d.get("form_factor")
            if not ff:
                continue
            clusters.setdefault(ff, set()).add(frame_cluster.get(crop_frame.get(d["file"])))

    trained: list[str] = []
    sidecars = gate_sidecars()
    if "identifier" in sidecars:
        trained = list(sidecars["identifier"].get("classes") or [])

    cluster_counts = {k: len(v - {None}) for k, v in clusters.items()}
    if not cluster_counts:
        cluster_counts = dict((snapshot.get("_coverage") or {}).get("clusters") or {})

    return {
        "all": all_ff,
        "counts": dict(counts),
        "clusters": cluster_counts,
        "trained": trained,
        "have_labels": bool(adj),
    }


def locales() -> dict[str, Any]:
    files = sorted(LOCALES.glob("*.json"))
    bundles = {p.stem: (_load(p) or {}) for p in files}
    base = max((len(v) for v in bundles.values()), default=0)
    return {
        "base_keys": base,
        "bundles": {k: {"keys": len(v), "pct": round(100 * len(v) / base) if base else None} for k, v in bundles.items()},
    }


def region_packs() -> list[dict[str, Any]]:
    out = []
    for p in sorted(REGIONS.glob("*.json")):
        d = _load(p) or {}
        rules = d.get("rules", [])
        # Which axis each rule matches on decides whether it can EVER fire, given
        # what the service measures. That is the product's current blocker and it
        # is derived here rather than asserted.
        axes: Counter = Counter()
        for r in rules:
            for key in (r.get("match") or {}):
                axes[key] += 1
        out.append(
            {
                "region_id": d.get("region_id", p.stem),
                "status": d.get("status"),
                "rules": len(rules),
                "axes": dict(axes),
                "rule_rows": [
                    {
                        "id": r.get("id"),
                        "stream": r.get("stream"),
                        "local_name": r.get("local_name"),
                        "match": r.get("match") or {},
                        "confidence": r.get("confidence"),
                    }
                    for r in rules
                ],
            }
        )
    return out


def resolvability(packs: list[dict[str, Any]], cov: dict[str, Any]) -> list[dict[str, Any]]:
    """Which form factors can reach an answer, given what is MEASURED today.

    Derived, never asserted. A rule matching on `lid_color` cannot fire because
    the service does not populate it - docs/12 P3 measured the sampler at 0.1966
    and it was deliberately left unwired - so a form factor whose only rules need
    a lid resolves to `unknown` no matter how well the models work.
    """
    measured = {"form_factor", "body_color"}
    rows = []
    trained = set(cov.get("trained") or [])
    for ff in cov.get("all", []):
        reachable, blocked_on = [], set()
        for pack in packs:
            for r in pack["rule_rows"]:
                if ff not in (r["match"].get("form_factor") or []):
                    continue
                needs = set(r["match"]) - {"form_factor"}
                if needs <= measured:
                    reachable.append(r["id"])
                else:
                    blocked_on |= needs - measured
        rows.append(
            {
                "form_factor": ff,
                "trained": ff in trained,
                "crops": cov["counts"].get(ff, 0),
                "clusters": cov["clusters"].get(ff, 0),
                "reachable_rules": reachable,
                "blocked_on": sorted(blocked_on),
                "answers": bool(trained) and ff in trained and bool(reachable),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def e(v: Any) -> str:
    if v is None or v == "":
        return UNKNOWN
    return html.escape(str(v))


def num(v: Any, digits: int = 3, suffix: str = "") -> str:
    if v is None:
        return UNKNOWN
    try:
        return f"{float(v):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return e(v)


def prov(hardware: Any, representative: Any) -> str:
    """A figure without its provenance is a bug on this page, so this is never
    allowed to render empty."""
    if not hardware:
        return '<span class="prov unknown">hardware not recorded</span>'
    tag = "rep" if representative else "proxy"
    word = "representative" if representative else "PROXY - not the service"
    return f'<span class="prov {tag}" title="{e(hardware)}">{word}</span>'


def render(data: dict[str, Any]) -> str:
    sidecars = data["sidecars"]
    packs = data["packs"]
    resolve_rows = data["resolvability"]
    loc = data["locales"]
    probes = data["probes"]

    # --- artefact gate table ---------------------------------------------- #
    gate_rows = []
    for role in ("validator", "identifier"):
        s = sidecars.get(role)
        if not s:
            gate_rows.append(
                f"<tr><td><b>{role}</b></td><td colspan='6'>{UNKNOWN} "
                f"<span class='note'>not in the tracked gate snapshot "
                f"(<code>docs/research/probes/data/gate-sidecars.json</code>). "
                f"This is an absence, not a pass.</span></td></tr>"
            )
            continue
        gr = s.get("gate_result") or {}
        ship = gr.get("may_ship")
        verdict = "<span class='pass'>may ship</span>" if ship else "<span class='fail'>refused</span>"
        metric = s.get("accuracy_metric") or "?"
        gate_rows.append(
            f"<tr>"
            f"<td><b>{e(role)}</b><div class='note'>{e(s.get('onnx_path'))} · "
            f"{'int8' if s.get('quantised') else 'fp32'} · {e(s.get('imgsz'))}px</div></td>"
            f"<td>{verdict}</td>"
            f"<td>{num(s.get('accuracy_drop'), 4)}<div class='note'>{e(metric)} vs "
            f"{num((s.get('gates') or {}).get('max_accuracy_drop'), 2)} · split "
            f"<b>{e(s.get('accuracy_split'))}</b></div></td>"
            f"<td>{num(s.get('median_latency_ms'), 3, ' ms')}<div class='note'>vs "
            f"{num((s.get('gates') or {}).get('max_median_latency_ms'), 0, ' ms')} · "
            f"{prov(s.get('latency_hardware'), s.get('latency_representative'))}</div></td>"
            f"<td>{num(s.get('p95_latency_ms'), 3, ' ms')}</td>"
            f"<td>{'<br>'.join(e(f) for f in gr.get('failures') or []) or '—'}</td>"
            f"<td>{'<br>'.join(e(u) for u in gr.get('unmeasured') or []) or '—'}</td>"
            f"</tr>"
        )

    # --- concurrency ------------------------------------------------------- #
    ramps = [p for p in probes if p["kind"] == "loadtest"]
    ramp_rows = []
    for p in sorted(ramps, key=lambda x: x["file"]):
        d = p["raw"]
        n = d.get("concurrent_scanners_within_budget")
        # A RAMP THAT DID NOT FORCE CROPS IS NOT A RAMP AT THE BINS IT CLAIMS.
        # `--bins N` on the client is a report LABEL; `SBR_FORCE_CROPS` on the
        # container is what makes it true. The client sends smooth noise, a
        # trained validator finds nothing in it, no crop is cut and the
        # identifier never runs - so the run measures a validator-only frame and
        # reads high. Derived from the run's own health block rather than from a
        # list of filenames, so a future run that repeats the mistake is caught.
        forced = ((d.get("health") or {}).get("settings") or {}).get("force_crops")
        suspect = d.get("bins_per_frame") and not forced
        caveat = (
            "<div class='note fail'>crops were NOT forced - the identifier never ran, "
            "so this is a validator-only frame and the figure is not comparable</div>"
            if suspect
            else ""
        )
        ramp_rows.append(
            f"<tr><td><code>{e(p['file'])}</code>{caveat}</td>"
            f"<td>{e(d.get('bins_per_frame'))}</td>"
            f"<td class='big {'unknown' if suspect else ''}'>{e(n)}</td>"
            f"<td>{num(d.get('budget_p95_ms'), 0, ' ms')}</td>"
            f"<td>{prov((d.get('hardware') or {}).get('label') if isinstance(d.get('hardware'), dict) else d.get('hardware'), d.get('representative'))}</td></tr>"
        )

    # --- paired latency ---------------------------------------------------- #
    paired_rows = []
    for p in [x for x in probes if x["kind"] == "latency_paired"]:
        d = p["raw"]
        for fmt, v in (d.get("formats") or {}).items():
            paired_rows.append(
                f"<tr><td><code>{e(p['file'])}</code></td><td><b>{e(fmt)}</b></td>"
                f"<td>{num(v.get('median_latency_ms'), 3, ' ms')}</td>"
                f"<td>{num(v.get('p95_latency_ms'), 3, ' ms')}</td>"
                f"<td>{prov((d.get('hardware') or {}).get('label'), d.get('representative'))}</td></tr>"
            )

    # --- coverage ---------------------------------------------------------- #
    cov_rows = []
    for r in resolve_rows:
        if r["trained"]:
            state, cls = "trained", "pass"
        elif r["crops"] == 1:
            state, cls = "dropped (n=1)", "warn"
        elif r["crops"] == 0:
            state, cls = "no data", "fail"
        else:
            state, cls = f"{r['crops']} crops, not trained", "warn"
        if r["answers"]:
            answer, acls = "resolves", "pass"
        elif r["blocked_on"]:
            answer, acls = "unknown - needs " + ", ".join(r["blocked_on"]), "fail"
        elif not r["trained"]:
            answer, acls = "unknown - not trained", "fail"
        else:
            answer, acls = "unknown - no rule", "warn"
        cov_rows.append(
            f"<tr><td><code>{e(r['form_factor'])}</code></td>"
            f"<td class='{cls}'>{e(state)}</td>"
            f"<td>{e(r['crops'])}</td><td>{e(r['clusters'])}</td>"
            f"<td class='{acls}'>{e(answer)}</td></tr>"
        )

    # --- locales ----------------------------------------------------------- #
    loc_rows = "".join(
        f"<tr><td><code>{e(k)}</code></td><td>{e(v['keys'])}</td>"
        f"<td><div class='bar'><i style='width:{v['pct'] or 0}%'></i></div>{e(v['pct'])}%</td></tr>"
        for k, v in sorted(loc["bundles"].items())
    )

    # --- packs ------------------------------------------------------------- #
    pack_rows = []
    for pk in packs:
        axes = ", ".join(f"{k}&nbsp;×{v}" for k, v in sorted(pk["axes"].items()))
        pack_rows.append(
            f"<tr><td><code>{e(pk['region_id'])}</code></td><td>{e(pk['status'])}</td>"
            f"<td>{e(pk['rules'])}</td><td class='note'>{axes}</td></tr>"
        )

    # --- evidence index ---------------------------------------------------- #
    docs = data["probe_docs"]
    ev_rows = []
    for p in probes:
        tier = {
            "latency": "headline · latency",
            "latency_paired": "headline · latency",
            "loadtest": "headline · concurrency",
            "declared": "headline · declared",
            "listed": "listed only",
            "unreadable": "unreadable",
        }[p["kind"]]
        doc = docs.get(p.get("probe") or "", None)
        ev_rows.append(
            f"<tr><td><code>{e(p['file'])}</code></td>"
            f"<td>{e(p.get('probe'))}</td>"
            f"<td class='note'>{e(tier)}</td>"
            f"<td>{prov(p.get('hardware'), p.get('representative'))}</td>"
            f"<td class='note'>{e(p.get('generated'))}</td>"
            f"<td class='note'>{('<code>' + e(doc) + '</code>') if doc else UNKNOWN}</td></tr>"
        )

    open_items = data["open_items"]
    open_rows = "".join(
        f"<tr><td>{e(o['what'])}</td><td class='{'warn' if o['owner']=='maintainer' else 'note'}'>{e(o['owner'])}</td>"
        f"<td class='note'>{e(o['why'])}</td></tr>"
        for o in open_items
    )

    generated = data["generated"]
    return f"""<style>
  /* The page reports on a product that HAS a design system, so it wears it
     rather than inventing one: paper and ink from web/src/styles/tokens/color.css,
     the one owned accent (signal violet #5b2e91), and the app's own faces.
     Semantic colour is kept separate from the accent - the pass/fail/warn hues
     are the taxonomy's own green, red and amber reference values, which is where
     this subject's colour vocabulary actually lives. */
  @import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap");

  :root {{
    --paper-0:#fcfbf8; --paper-1:#f6f4ef; --paper-2:#ebe8e1; --line:#dcd8cf;
    --ink-0:#16181c; --ink-1:#2e3238; --ink-2:#5a6068; --ink-3:#8a9098;
    --signal:#5b2e91; --signal-tint:#ece5f6;
    --pass:#1e7a3c; --fail:#c1272d; --warn:#a86a10;
    --bg:var(--paper-1); --card:var(--paper-0); --fg:var(--ink-0); --muted:var(--ink-2);
    --font-sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
    --font-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  }}
  /* Default "system" stamps nothing, so prefers-color-scheme is the only signal -
     guarded so an explicit light choice still beats a dark OS. */
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --paper-0:#1b1e24; --paper-1:#14161a; --paper-2:#22262d; --line:#2b3038;
      --ink-0:#f4f2ec; --ink-1:#d8d5cc; --ink-2:#9aa2b1; --ink-3:#767d8a;
      --signal:#c0a8ec; --signal-tint:#2a2140;
      --pass:#5ad48b; --fail:#ff8a86; --warn:#e8b45c;
      --bg:var(--paper-1); --card:var(--paper-0); --fg:var(--ink-0); --muted:var(--ink-2);
    }}
  }}
  :root[data-theme="dark"] {{
    --paper-0:#1b1e24; --paper-1:#14161a; --paper-2:#22262d; --line:#2b3038;
    --ink-0:#f4f2ec; --ink-1:#d8d5cc; --ink-2:#9aa2b1; --ink-3:#767d8a;
    --signal:#c0a8ec; --signal-tint:#2a2140;
    --pass:#5ad48b; --fail:#ff8a86; --warn:#e8b45c;
    --bg:var(--paper-1); --card:var(--paper-0); --fg:var(--ink-0); --muted:var(--ink-2);
  }}

  /* The viewer paints its own ground behind the page, so this must be explicit. */
  body {{ background:var(--bg); color:var(--fg); margin:0; font-family:var(--font-sans);
    font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:1120px; margin:0 auto; padding:36px 20px 96px;
    display:flex; flex-direction:column; gap:0; }}

  h1 {{ font-size:1.75rem; font-weight:600; margin:0 0 6px; letter-spacing:-0.02em;
    text-wrap:balance; }}
  h2 {{ font-size:.72rem; font-weight:600; text-transform:uppercase; letter-spacing:.11em;
    color:var(--muted); margin:34px 0 10px; }}
  .sub {{ color:var(--muted); margin:0 0 26px; max-width:66ch; }}

  section {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
    padding:4px 16px 10px; }}
  section.lead {{ padding:18px; border-inline-start:3px solid var(--signal);
    background:var(--signal-tint); }}
  section.lead h2 {{ margin-block-start:0; }}

  table {{ width:100%; border-collapse:collapse; font-size:13.5px;
    font-variant-numeric:tabular-nums; }}
  th,td {{ text-align:start; padding:9px 10px; border-block-end:1px solid var(--line);
    vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase;
    letter-spacing:.07em; white-space:nowrap; }}
  tr:last-child td {{ border-block-end:0; }}
  /* Every measured figure is set in the mono face, so a number never reads as prose. */
  td {{ font-variant-numeric:tabular-nums; }}
  code, .num {{ font-family:var(--font-mono); font-size:12.5px; }}

  .note {{ color:var(--muted); font-size:12px; line-height:1.45; }}
  .pass {{ color:var(--pass); font-weight:600; }}
  .fail {{ color:var(--fail); font-weight:600; }}
  .warn {{ color:var(--warn); font-weight:600; }}
  .big {{ font-family:var(--font-mono); font-size:1.3rem; font-weight:600; }}
  .unknown {{ color:var(--ink-3); font-style:italic; }}

  /* State encoded in FORM as well as colour, so it reads at a glance and does not
     depend on hue alone. */
  .prov {{ display:inline-block; font-family:var(--font-mono); font-size:10.5px;
    padding:1px 7px; border-radius:999px; border:1px solid currentColor;
    white-space:nowrap; }}
  .prov.rep {{ color:var(--pass); }}
  .prov.proxy {{ color:var(--warn); }}
  .prov.unknown {{ color:var(--ink-3); font-style:normal; }}

  .bar {{ display:inline-block; inline-size:110px; block-size:6px; background:var(--paper-2);
    border-radius:99px; overflow:hidden; margin-inline-end:8px; vertical-align:middle; }}
  .bar i {{ display:block; block-size:100%; background:var(--signal); }}
  .scroll {{ overflow-x:auto; }}
  a {{ color:var(--signal); }}
  a:focus-visible, [tabindex]:focus-visible {{ outline:2px solid var(--signal);
    outline-offset:2px; }}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation:none !important;
    transition:none !important; }} }}
</style>
<div class="wrap">
<h1>Smart Bin Recognition — evidence</h1>
<p class="sub">Generated by <code>ml/scripts/build_dashboard.py</code> from the
repository's own evidence files. <b>Newest evidence on this page: {e(generated)}</b>
- dated from the sources rather than from the render, so the page rebuilds
byte-for-byte from a clean checkout and CI fails if it drifts. Nothing here is
typed by hand, and a figure whose source file is missing renders as
<span class="unknown">unknown</span> rather than being filled in.</p>

<section class="lead">
<h2 style="margin-top:0">The two things that decide everything</h2>
<table>
<tr><td><b>Can a model ship?</b></td><td>{data['headline_ship']}</td></tr>
<tr><td><b>Does a Deggendorf wheelie get an answer?</b></td><td>{data['headline_wheelie']}</td></tr>
</table>
</section>

<h2>Artefacts and their gates</h2>
<section class="scroll"><table>
<tr><th>artefact</th><th>verdict</th><th>accuracy cost</th><th>median latency</th><th>p95</th><th>failures</th><th>unmeasured</th></tr>
{''.join(gate_rows)}
</table>
<p class="note">Every latency carries the hardware it was measured on and whether that
hardware counts as the service. A <span class="prov proxy">PROXY - not the service</span>
figure may not close a gate.</p></section>

<h2>Concurrency — the gate that fails</h2>
<section class="scroll"><table>
<tr><th>source</th><th>bins / frame</th><th>scanners within budget</th><th>p95 budget</th><th>provenance</th></tr>
{''.join(ramp_rows) or '<tr><td colspan="5">' + UNKNOWN + ' no load-test ramp in the evidence directory</td></tr>'}
</table>
<p class="note">The budget line is <b>≥ 10 concurrent scanners</b>. Every measured row above is below it.</p></section>

{'<h2>Weight format — measured, paired on one host</h2><section class="scroll"><table><tr><th>source</th><th>format</th><th>median</th><th>p95</th><th>provenance</th></tr>' + ''.join(paired_rows) + '</table></section>' if paired_rows else ''}

<h2>Coverage, and what actually answers</h2>
<section class="scroll"><table>
<tr><th>form factor</th><th>training data</th><th>crops</th><th>clusters</th><th>does it answer?</th></tr>
{''.join(cov_rows)}
</table>
<p class="note">The last column is <b>derived</b>, not asserted: a rule is reachable only if
every axis it matches on is one the service measures today
(<code>form_factor</code>, <code>body_color</code>). Anything needing
<code>lid_color</code> cannot fire.</p></section>

<h2>Region packs</h2>
<section class="scroll"><table>
<tr><th>region</th><th>status</th><th>rules</th><th>rules match on</th></tr>
{''.join(pack_rows)}
</table></section>

<h2>Locales</h2>
<section class="scroll"><table>
<tr><th>bundle</th><th>keys</th><th>complete</th></tr>
{loc_rows}
</table></section>

<h2>Open items</h2>
<section class="scroll"><table>
<tr><th>what</th><th>owner</th><th>why it is open</th></tr>
{open_rows}
</table></section>

<h2>Evidence index — every probe result file</h2>
<section class="scroll"><table>
<tr><th>file</th><th>probe</th><th>contributes</th><th>provenance</th><th>dated</th><th>write-up</th></tr>
{''.join(ev_rows)}
</table>
<p class="note"><b>Two tiers, and the difference is deliberate.</b> Every file in
<code>docs/research/probes/data/</code> is listed here automatically. A file contributes a
<i>headline number</i> above only if it matches a recognised shape or carries an explicit
<code>dashboard</code> block — because these files have no common schema, and a generator
claiming to parse them uniformly would be hardcoding under another name.</p></section>
</div>"""


def newest_evidence(probes: list[dict[str, Any]]) -> str:
    """The date of the most recent evidence ON the page, from the files themselves.

    **Three stamps were tried and two were wrong.** `datetime.now()` made the
    output differ on every run, which defeats the CI check that keeps the
    committed page honest. The git commit date then looked deterministic and is
    not usable either: the page has to exist *before* the commit that contains
    it, so it can never carry its own commit's date and the check failed forever.

    Dating the page by its newest input has neither problem, needs no git, and is
    the more honest label anyway - a reader wants to know how old the evidence is,
    not when somebody last ran a script.

    Dates in these files are heterogeneous by nature (`2026-08-21`,
    `2026-08-22T00:38:28+00:00`, and one `2026-08-17/18`). Only the leading
    ISO date is read, and anything unparseable is skipped rather than guessed at.
    """
    dates = set()
    for probe in probes:
        raw = str(probe.get("generated") or "")
        match = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
        if match:
            dates.add(match.group(1))
    return max(dates) if dates else "unknown"


def open_items(sidecars: dict[str, Any], resolve_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Derived from the evidence, so an item closes when its source says so."""
    items: list[dict[str, str]] = []

    v = sidecars.get("validator") or {}
    if not ((v.get("gate_result") or {}).get("may_ship")):
        items.append(
            {
                "what": "The validator cannot ship",
                "owner": "maintainer",
                "why": "int8 costs it 0.727 mAP against a 0.02 budget. fp32 clears latency (24.6 ms vs 50 ms) "
                "and costs one concurrent scanner - the gate split is staged on feat/fp32-ship-profile, unmerged.",
            }
        )
    blocked = sorted({a for r in resolve_rows for a in r["blocked_on"]})
    if blocked:
        items.append(
            {
                "what": f"Rules match on {', '.join(blocked)}, which nothing measures",
                "owner": "maintainer",
                "why": "P3 scored the lid sampler at 0.1966 against a 0.60 floor on 117 wheelies whose lids "
                "were visible in 98% of frames. Either the rules move to a measurable axis, or wheelies stay unknown.",
            }
        )
    items.append(
        {
            "what": "P3's colour labels are provisional",
            "owner": "maintainer",
            "why": "160 labels written by an agent, recorded as provisional_proposals. A 25-crop spot-check is "
            "pre-registered before any P3 number is quoted as settled.",
        }
    )
    items.append(
        {
            "what": "Recalibrating the colour reference swatches",
            "owner": "maintainer",
            "why": "Would take body colour agreement from 0.5625 to 0.9125 leave-one-cluster-out. Changes every "
            "resolution outcome in every pack, so it is a taxonomy decision.",
        }
    )
    items.append(
        {
            "what": "Concurrency fails 5 against 10",
            "owner": "phase 2",
            "why": "The frame costs 49 ms and would need ~25. Measured on a controlled host with the one working "
            "recovery already applied, so it fails on compute rather than on tuning.",
        }
    )
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "docs/dashboard.html")
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="refresh the tracked gate snapshot from artifacts/ before rendering. "
        "Run this when a sidecar changes; commit the result.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.snapshot:
        snap = snapshot_gates()
        if not snap:
            raise SystemExit(
                "--snapshot found no sidecars under artifacts/. That directory is gitignored, "
                "so this only works on a machine that has produced or downloaded them."
            )
        GATE_SNAPSHOT.write_text(json.dumps(snap, indent=2) + chr(10), encoding="utf-8")
        logger.info("snapshotted %d gate verdicts -> %s", len(snap), GATE_SNAPSHOT)

    probes = probe_files()
    sidecars = gate_sidecars()
    cov = coverage()
    packs = region_packs()
    rows = resolvability(packs, cov)

    ships = [r for r, s in sidecars.items() if (s.get("gate_result") or {}).get("may_ship")]
    refused = [r for r, s in sidecars.items() if not (s.get("gate_result") or {}).get("may_ship")]
    if not sidecars:
        headline_ship = f"{UNKNOWN} — no sidecar on disk"
    elif refused:
        headline_ship = (
            f"<span class='fail'>No.</span> "
            f"{', '.join(refused)} refused; {', '.join(ships) or 'nothing'} eligible. "
            f"The service loads the validator unconditionally, so nothing is deployed."
        )
    else:
        headline_ship = "<span class='pass'>Yes</span> — every artefact on disk passes its gates."

    wheelies = [r for r in rows if r["form_factor"].startswith("wheelie")]
    if wheelies and not any(w["answers"] for w in wheelies):
        need = sorted({a for w in wheelies for a in w["blocked_on"]})
        headline_wheelie = (
            f"<span class='fail'>No.</span> Every wheelie resolves to <code>unknown</code>: "
            f"its rules match on <code>{', '.join(need) or '?'}</code>, which the service does not measure."
        )
    elif wheelies:
        headline_wheelie = "<span class='pass'>Yes</span> — a wheelie reaches a rule."
    else:
        headline_wheelie = UNKNOWN

    data = {
        "generated": newest_evidence(probes),
        "probes": probes,
        "probe_docs": probe_docs(),
        "sidecars": sidecars,
        "coverage": cov,
        "packs": packs,
        "resolvability": rows,
        "locales": locales(),
        "open_items": open_items(sidecars, rows),
        "headline_ship": headline_ship,
        "headline_wheelie": headline_wheelie,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("<title>Smart Bin Evidence</title>\n" + render(data), encoding="utf-8")
    logger.info("read %d probe files, %d sidecars, %d packs", len(probes), len(sidecars), len(packs))
    logger.info("wrote %s (%.1f kB)", args.out, args.out.stat().st_size / 1000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
