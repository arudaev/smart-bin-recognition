#!/usr/bin/env python3
"""docs/12 P3, second act: which axis should the pack match wheelies on?

    python ml/scripts/probe_rule_axis.py --out docs/research/probes/data/P3-rule-axis.json

**The question P3 did not ask.** P3 asked *"can the service measure a lid?"* and
answered no - 0.1966 against a 0.60 floor. That is a correct answer to a question
nobody should have asked first. The prior question is *"what does the pack need
to know, and what is the cheapest measurable thing that supplies it?"*

Two facts arrived after P3 was scoped, and together they invert it:

1. ``research/12`` found the municipality naming the containers - *"die graue
   Restmuelltonne, die braune Biotonne und die blaue Papiertonne"*. That is a
   statement about the **bin**, not about its lid.
2. P3's own labels say body and lid agree on 62 % of wheelies, and where they
   disagree the **body is the better discriminator**: Restmuell is black on 96 %
   of bodies against a lid that is grey on only 74 %.

So this scores the whole chain - real frame, real crop, the shipping sampler, a
candidate rule - against the legacy archive's **own stream label**, which is
human and entirely independent of the colour labels. That independence is the
point: if the provisional colour labels were badly wrong, centroids fitted to
them could not predict an unrelated variable this well.

Leave-one-capture-cluster-out for the recalibrated arm, so no bin helps classify
itself.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "service"))
sys.path.insert(0, str(REPO_ROOT / "ml/src"))

logger = logging.getLogger("rule_axis")

#: The candidate rule set. The SAME streams and the SAME colours the Deggendorf
#: pack already carries - only the axis moves, from lid_color to body_color.
RULE = {"black": "residual", "grey": "residual", "blue": "paper", "brown": "bio", "green": "glass_mixed"}

#: The archive's own stream label, which is the independent ground truth here.
TRUTH = {"Restmüll": "residual", "Papier": "paper", "Biomüll": "bio", "Glas": "glass_mixed"}


def _axis_purity(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """How cleanly each axis separates the streams, on the labels alone.

    This is the part that says the axis choice was wrong on its own terms, before
    measurability enters the argument at all.
    """
    out: dict[str, Any] = {}
    for axis in ("label_body", "label_lid"):
        by: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for s in samples:
            if s["truth_stream"] and s[axis] not in ("not_visible", "unsure"):
                by[s["truth_stream"]][s[axis]] += 1
        out[axis.replace("label_", "") + "_color"] = {
            stream: {
                "n": sum(c.values()),
                "dominant": c.most_common(1)[0][0],
                "purity": round(c.most_common(1)[0][1] / sum(c.values()), 4),
            }
            for stream, c in sorted(by.items())
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", type=Path, default=REPO_ROOT / "data/legacy/pool")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    import colour as colour_mod
    import cv2
    import numpy as np

    pool = args.pool
    man = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    recs = {r["file"]: r for r in man["crop_records"]}
    frames = {r["file"]: r for r in man["records"]}
    adj = json.loads((pool / "adjudication.json").read_text(encoding="utf-8"))
    factors = {d["file"]: d["form_factor"] for d in adj["decisions"] if d.get("form_factor")}
    labels = json.loads((pool / "colour-labels.json").read_text(encoding="utf-8"))
    rows = [
        r
        for r in labels["labels"]
        if r["labeller"] == "claude" and factors.get(r["file"], "").startswith("wheelie")
    ]

    samples: list[dict[str, Any]] = []
    for r in rows:
        rec = recs[r["file"]]
        frame = cv2.imread(str(pool / "images" / rec["frame"]))
        if frame is None:
            continue
        frgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        x0, y0, x1, y1 = rec["crop_px"]
        crop = frgb[y0:y1, x0:x1]
        gain = colour_mod.estimate_illuminant(frgb)
        shipped, _ = colour_mod.measure_body_colour(crop, gain)
        lab = colour_mod.srgb_to_lab(
            colour_mod.apply_illuminant(colour_mod.centre_sample(crop), gain).mean(axis=0)
        )
        samples.append(
            {
                "cluster": str(frames[rec["frame"]].get("capture_cluster")),
                "truth_stream": TRUTH.get(rec["legacy_class"]),
                "label_body": r["body_color"],
                "label_lid": r["lid_color"],
                "shipped_body": shipped,
                "lab": lab,
            }
        )

    n = len(samples)

    def score(got: list[str | None]) -> dict[str, Any]:
        resolved = sum(1 for g in got if RULE.get(g) is not None)
        correct = sum(1 for g, s in zip(got, samples, strict=True) if RULE.get(g) == s["truth_stream"])
        errs: collections.Counter = collections.Counter()
        for g, s in zip(got, samples, strict=True):
            if RULE.get(g) != s["truth_stream"]:
                errs[f"{s['truth_stream']} measured {g} -> {RULE.get(g)}"] += 1
        return {
            "n": n,
            "resolved": resolved,
            "resolved_fraction": round(resolved / n, 4),
            "correct_stream": correct,
            "correct_fraction": round(correct / n, 4),
            "errors": dict(errs.most_common()),
        }

    # Recalibrated references, held out by capture cluster.
    recal: list[str | None] = []
    for s in samples:
        train = [t for t in samples if t["cluster"] != s["cluster"]]
        cent = {}
        for name in {t["label_body"] for t in train}:
            cent[name] = np.mean(np.array([t["lab"] for t in train if t["label_body"] == name]), axis=0)
        recal.append(min(cent, key=lambda k: colour_mod.delta_e_2000(s["lab"], cent[k])) if cent else None)

    report = {
        "probe": "P3",
        "act": "second - which axis should the pack match on?",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "PROVISIONAL": True,
        "provisional_note": (
            "the colour labels are an agent's (labeller: claude). The STREAM truth is not - it is "
            "the legacy archive's own class label, independent of those labels. So correct_fraction "
            "is measured against independent ground truth even though the recalibration is fitted "
            "to provisional ones"
        ),
        "candidate_rule": RULE,
        "truth_source": "legacy_class in the pool manifest, from the predecessor's archive",
        "matching_on_lid_color": {
            "n": n,
            "resolved": 0,
            "resolved_fraction": 0.0,
            "correct_stream": 0,
            "correct_fraction": 0.0,
            "why": (
                "service/pipeline.py sets lid_color=None; docs/12 P3 scored the sampler at 0.1966 "
                "and its rule says do not wire it in"
            ),
        },
        "matching_on_body_color": {
            "ceiling_perfect_colour": score([s["label_body"] for s in samples]),
            "shipped_sampler_hex_ref_as_is": score([s["shipped_body"] for s in samples]),
            "shipped_sampler_recalibrated": score(recal),
        },
        "discriminative_power_of_each_axis": _axis_purity(samples),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(json.dumps(report["matching_on_body_color"], indent=2))
    logger.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
