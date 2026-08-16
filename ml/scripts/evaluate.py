#!/usr/bin/env python3
"""Render the phase-2 results doc from measured artefacts. Invents nothing.

    python ml/scripts/evaluate.py --version 1 --out docs/11-phase2-results.md

The measurements happen where the data is – accuracy in the training kernel,
latency on the 2-vCPU bench Space – and this pulls them together and writes them
down with **the split they came from and the hardware they ran on** attached to
every number. That attachment is the entire point: the predecessor's 95.2 % was
not wrong so much as unlabelled, and an unlabelled number is not a result.

A metric that has not been measured is written as "not measured" and says why.
It is never interpolated, never carried over from another split, and never
quietly omitted so the table looks complete.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.config import load_config  # noqa: E402
from sbr.export.onnx_export import Gates, check_gates, load_sidecar  # noqa: E402

logger = logging.getLogger("evaluate")

NOT_MEASURED = "_not measured_"
ROLES = ("validator", "identifier")


def fetch(repo: str, version: int, role: str, name: str, out_dir: Path) -> Path | None:
    """Pull one artefact file, or return None if the run never produced it."""
    from huggingface_hub import hf_hub_download

    from sbr.utils.hub import configure_hf_runtime, load_hf_token

    configure_hf_runtime()
    try:
        local = hf_hub_download(
            repo_id=repo, filename=f"v{version}/{name}", token=load_hf_token()
        )
    except Exception as error:  # noqa: BLE001 - a missing artefact is a reportable state
        logger.warning("%s v%d: no %s (%s)", role, version, name, type(error).__name__)
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{role}-v{version}-{name.replace('/', '-')}"
    target.write_bytes(Path(local).read_bytes())
    return target


def gather(version: int, artifacts: Path, local: Path | None) -> dict[str, dict[str, Any]]:
    """Collect history + sidecar for both roles."""
    collected: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        config = load_config(role)
        repo = config["hub"]["model_repo"]
        entry: dict[str, Any] = {"config": config, "repo": repo}

        if local:
            history_path = local / f"{role}-history.json"
            sidecar_path = local / f"{role}-v{version}.json"
        else:
            history_path = fetch(repo, version, role, "history.json", artifacts)
            sidecar_path = fetch(repo, version, role, f"{role}-v{version}.json", artifacts)

        if history_path and Path(history_path).exists():
            entry["history"] = json.loads(Path(history_path).read_text(encoding="utf-8"))
        if sidecar_path and Path(sidecar_path).exists():
            entry["report"] = load_sidecar(Path(sidecar_path))
        collected[role] = entry
    return collected


def number(value: Any, digits: int = 4) -> str:
    if value is None:
        return NOT_MEASURED
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def gate_table(role: str, entry: dict[str, Any]) -> str:
    report = entry.get("report")
    gates = Gates.from_config(role, entry["config"])
    if report is None:
        return (
            f"| {role} | {NOT_MEASURED} | ≤ {gates.max_median_latency_ms:.0f} ms | "
            "**no artefact** – the run has not completed |\n"
        )

    result = check_gates(report, gates)
    if report.median_latency_ms is None:
        verdict = "**unmeasured** – bench not yet run"
    elif result.may_ship:
        verdict = "**met**"
    else:
        verdict = "**MISSED** – " + "; ".join(result.failures)

    return (
        f"| {role} | {number(report.median_latency_ms, 1)} ms | "
        f"≤ {gates.max_median_latency_ms:.0f} ms | {verdict} |\n"
    )


def buckets_table(history: dict[str, Any]) -> str:
    buckets = (history or {}).get("recall_by_bins_per_frame") or {}
    if not buckets:
        return (
            "Not measured – the validator run has not completed.\n\n"
            "Note that the legacy subset alone cannot fill the `4+` row: it has "
            "**no frame with four or more bins**.\n"
        )

    rows = "| bins in frame | frames | boxes | detected | recall |\n|---|---|---|---|---|\n"
    for key in sorted(buckets, key=lambda k: (k == "4+", k)):
        bucket = buckets[key]
        rows += (
            f"| {key} | {bucket['frames']} | {bucket['truth_boxes']} | "
            f"{bucket['detected']} | {number(bucket.get('recall'))} |\n"
        )
    if "4+" not in buckets:
        rows += (
            "| **4+** | **0** | – | – | **no data** |\n\n"
            "The `4+` row is empty because the test split contains no such frame. "
            "The PRD calls a bank of six containers *a normal input, not an edge "
            "case*, so this is a gap in the evidence, not a passing grade.\n"
        )
    return rows


def render(version: int, collected: dict[str, dict[str, Any]]) -> str:
    validator = collected["validator"]
    identifier = collected["identifier"]
    v_history = validator.get("history") or {}
    i_history = identifier.get("history") or {}
    # Either role's sidecar names the bench; the validator's is the one quoted
    # because its budget is the one the concurrency arithmetic rests on.
    v_report = validator.get("report")
    hardware = (v_report.latency_hardware if v_report else None) or NOT_MEASURED

    lines = [
        f"# 11 – Phase 2 results (v{version})",
        "",
        "> Every number here names the split it was measured on and the hardware it",
        "> ran on. A metric that was not measured says so; nothing is interpolated,",
        "> carried over from another split, or omitted to make a table look full.",
        "",
        f"Generated {date.today().isoformat()} by `ml/scripts/evaluate.py`.",
        "",
        "## The phase-2 gate",
        "",
        "docs/07 states it: **validator ≤ 50 ms @ 448 and identifier ≤ 25 ms per crop",
        "on service CPU, and ≥ 10 concurrent scanners on the free tier.**",
        "",
        "| model | measured p50 | budget | verdict |",
        "|---|---|---|---|",
        gate_table("validator", validator).rstrip("\n"),
        gate_table("identifier", identifier).rstrip("\n"),
        "",
        f"Latency hardware: {hardware}",
        "",
        "The concurrency half of the gate is **not answered here**: it needs the",
        "inference service, which is phase 3. Latency is the half that can be",
        "answered now, and it is the half the cost model's arithmetic rests on",
        "(docs/05 § 3).",
        "",
        "## What the models were trained on",
        "",
    ]

    composition = (v_history.get("dataset") or {}).get("composition") or {}
    if composition:
        lines += [
            f"- subsets: `{composition.get('per_pool')}`",
            f"- splits: `{composition.get('per_split')}`",
            f"- positives: {composition.get('positives')}, "
            f"background images: {composition.get('background_images')} "
            f"({composition.get('negative_ratio')}:1)",
            f"- dataset revision: `{(v_history.get('dataset') or {}).get('revision')}`",
            "",
        ]
    else:
        lines += ["_The validator run has not completed._", ""]

    lines += [
        "The split is **group-aware by capture cluster** – frames of one bin in one",
        "visit share a split – and never random. docs/08 § 7.3's 0.9873 came from a",
        "random 20 % of one capture session and is not comparable to anything below.",
        "",
        "## Validator",
        "",
        "| metric | split | value |",
        "|---|---|---|",
        f"| mAP@0.5 | test (group-aware) | {number((v_history.get('test') or {}).get('map50'))} |",
        f"| mAP@0.5:0.95 | test | {number((v_history.get('test') or {}).get('map50_95'))} |",
        f"| precision | test | {number((v_history.get('test') or {}).get('precision'))} |",
        f"| recall | test | {number((v_history.get('test') or {}).get('recall'))} |",
        f"| mAP@0.5 | **held-out region** | "
        f"{number((v_history.get('holdout_region') or {}).get('map50'))} |",
        f"| recall | **held-out region** | "
        f"{number((v_history.get('holdout_region') or {}).get('recall'))} |",
        "",
        "### Recall by bins per frame",
        "",
        "docs/04 § 5 commits to this so a model that only works on one big centred",
        "bin cannot hide behind an aggregate.",
        "",
        buckets_table(v_history),
        "",
        "### Precision on the negative corpus",
        "",
    ]

    negatives = v_history.get("precision_on_negatives") or {}
    if negatives:
        lines += [
            f"- negative frames in the test split: {negatives.get('negative_frames')}",
            f"- frames with at least one false positive: "
            f"{negatives.get('frames_with_a_false_positive')}",
            f"- frame-level specificity: {number(negatives.get('frame_level_specificity'))}",
            "",
            "This is the number that says whether the predecessor's failure is fixed:",
            "it hallucinated a glass container on a slide of plain black text",
            "(docs/08 § 7.5) because it had never been shown a negative.",
        ]
    else:
        lines += ["Not measured – the validator run has not completed.", ""]

    lines += [
        "",
        "## Identifier",
        "",
        "| metric | split | value |",
        "|---|---|---|",
        f"| top-1 | test (group-aware) | {number((i_history.get('test') or {}).get('top1'))} |",
        f"| top-5 | test | {number((i_history.get('test') or {}).get('top5'))} |",
        f"| unknown rate | test | "
        f"{number((i_history.get('unknown') or {}).get('unknown_rate'))} |",
        f"| accuracy when answering | test | "
        f"{number((i_history.get('unknown') or {}).get('accuracy_when_answering'))} |",
        "",
    ]

    absent = i_history.get("classes_without_data")
    if absent:
        lines += [
            "**The identifier does not support all ten form factors.** No training",
            f"data exists for: `{absent}`.",
            "",
        ]
    elif not i_history:
        lines += [
            "_The identifier run has not completed._ It is blocked on the human",
            "adjudication pass: the legacy labels are waste **streams**, and a stream",
            "does not determine a shape, so `ml/scripts/adjudicate.py` has to run",
            "before there is anything to train on.",
            "",
        ]

    lines += [
        "## Novelty precision",
        "",
        "The kill criterion in docs/07 is **< 0.5**, and the whole improvement loop",
        "rests on the validator/identifier disagreement being a trustworthy signal.",
        "",
        f"**{NOT_MEASURED}.** It needs both models plus a human verdict on whether each",
        "flagged frame was genuinely a new bin type, so it cannot be computed until",
        "the identifier exists and its flags have been adjudicated.",
        "",
        "## Numbers this project does not quote",
        "",
        "- the predecessor's **95.2 % mAP@0.5** – a random split of one week of",
        "  photographs in one city;",
        "- the **0.9873** independent re-validation (docs/08 § 7.3) – same split, so",
        "  it reproduces the memorisation rather than refuting it.",
        "",
        "Both are in-distribution. Neither is this project's baseline.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "11-phase2-results.md")
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--local", type=Path, default=None, help="read artefacts from here instead of the Hub")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    collected = gather(args.version, args.artifacts, args.local)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(args.version, collected), encoding="utf-8")

    have = [role for role, entry in collected.items() if entry.get("history")]
    print(f"wrote {args.out}")
    print(f"runs with results: {have or 'none - nothing has completed yet'}")


if __name__ == "__main__":
    main()
