# 12 – Validation protocol

> How a claim gets tested before it gets hard-coded. Six probes, each with its
> question, its cost, and a **decision rule written before the result**.

The design docs contain claims of three kinds: things measured (docs/08 § 7),
things decided (docs/01 § 1), and things assumed. This document is about the
third kind. Each probe converts one assumption into a number, and each is cheap
enough that finding out costs less than being wrong.

**A probe with no decision rule stated in advance does not run.** Otherwise the
result gets read in whatever direction the week wants.

Results land in [`research/probes/`](research/probes/), one file per probe,
dated, and the outcome edits the doc the probe was designed to resolve.

---

## The unlock: latency is answerable before training

ONNX inference cost depends on **architecture and input shape, not on learned
weights**. An untrained `yolo11n` at 448 and an untrained `yolo11s-cls` at 320,
exported and quantised, cost the same per frame as trained ones.

So the entire **latency half of the phase-2 gate** (docs/07) can be answered
today, before a single GPU hour is spent — and if the architecture misses budget,
that is far better learned now. P4 and P5 both depend on this and neither needs a
model.

---

## P1 – Form-factor separability

**Question.** Are the ten form factors separable from a 320 px crop? Specifically:
is `wheelie_small` vs `wheelie_large` a *size* distinction that resizing
destroys?

**Why it comes first.** It gates the human adjudication pass. Labelling 403 crops
against a class list that turns out to be wrong means labelling them twice.

**Method.** Adjudicate a 40-crop pilot spanning the legacy classes. Compute
DINOv2 embeddings over those plus the Open Images bin crops. Fit a linear probe
on frozen embeddings; report the confusion matrix and per-pair separability.
Include relative box area (box px ÷ frame px) as a second feature in a variant —
this is the signal resizing throws away.

**Decision rule, stated in advance.**

| Outcome | Action |
|---|---|
| `wheelie_small`/`wheelie_large` separable at ≥ 0.75 pairwise | proceed with ten classes; run the full 403-crop pass |
| separable only *with* relative box area | keep ten classes and **pass box area to the identifier as a feature** — this is a design change, not a tuning one |
| not separable either way | **merge into `wheelie`**, and recover the distinction in the product with a clarifying question |
| any other pair below 0.6 | record it; do not merge without the same analysis |

**Cost.** One pilot adjudication (~20 min) + one Kaggle GPU kernel. No training.

**Resolves.** docs/02's form-factor list · docs/04 § 5's "seven of ten have no
data" · the class list `adjudicate.py` presents.

---

## P2 – Novelty scoring bake-off

**Question.** Which score separates "new bin type" from "hard familiar bin", and
at what threshold? `unknown_threshold: 0.55` is currently an unjustified constant.

**What can be built now, before model B exists:** the frozen evaluation mixture.
Five buckets, per research note 02 § 2:

| Bucket | Source available today |
|---|---|
| familiar, correct | legacy + Open Images bins |
| familiar but hard — blur, dusk, occlusion, tiny crop | filter the existing corpus on box area and Laplacian variance |
| genuinely unseen form factor | the Open Images bins whose form factor has no legacy example |
| validator false positive | the 2 499 hard negatives |
| second city | **not available** — record the gap rather than substituting |

**Method, once model B exists.** Score every bucket member under MSP, energy,
max-logit and kNN-on-embeddings. Plot novelty precision against flag rate. Choose
the operating point first, then read off the threshold.

**Decision rule.**

| Outcome | Action |
|---|---|
| any score reaches novelty precision ≥ 0.70 at a flag rate ≤ 15% | adopt it; pin the threshold in `identifier.yaml` with the run that produced it |
| best is 0.5–0.7 | ship, flag the loop as degraded, and make the second-city capture the top priority |
| best < 0.5 | **the docs/07 kill criterion fires.** The disagreement signal is not trustworthy and the improvement loop does not close as designed |

**Cost.** Set construction now, ~2 h. Scoring: minutes once B exists.

**Resolves.** `identifier.yaml:unknown_threshold` · docs/04 § 7's novelty
precision target · docs/07's second kill criterion.

---

## P3 – Colour measurement

**Question.** Does illuminant normalisation beat naive sampling — and **is SAM
needed at all**?

**Method.** Hand-label body and lid colour on ~120 legacy crops (fast: it is
colour, one keystroke). Then compare four variants, all in CIELAB with ΔE to the
nearest named colour:

1. mean over the whole crop
2. mean over a centre-weighted region inside the box
3. (2) with Gray World normalisation
4. (2) with Shades of Gray, *p* = 6

**Decision rule.**

| Outcome | Action |
|---|---|
| (2) or (3) within 5 points of the best | **SAM leaves the critical path.** Remove the mask dependency from docs/04 § 1 |
| a mask variant clearly wins | keep SAM; state what it buys in points, not in principle |
| no variant exceeds ~0.75 agreement | colour is not reliably measurable outdoors at this quality; escalate — it is the second of the taxonomy's three axes |

Lid-vs-body separation is **explicitly out of scope for P3** and recorded as an
open problem (research note 06 § 3). Measure body colour first.

**Cost.** No GPU, no model, no SAM. Half a day, most of it labelling.

**Resolves.** docs/02 § 1's colour axis · docs/04 § 1's mask claim · docs/07's
mis-specified "validate against legacy class labels" task.

---

## P4 – Multi-bin cost curve

**Question.** What does a frame actually cost at 0, 1, 3 and 6 bins?

**Why.** docs/05 § 3 budgets 65 ms/frame = validator + **one** crop, while the
PRD calls a bank of six containers "a normal input, not an edge case". At six
crops the frame costs 40 + 6×25 = 190 ms, and the concurrency ceiling falls from
~10 to ~3.5. The cost model and the product spec currently describe different
products.

**Method.** Extend `ml/kaggle/bench_latency/` to time the validator plus *n*
identifier passes for n ∈ {0, 1, 3, 6}. Untrained weights are fine. Report the
curve, and whether batching the crops through one ONNX call beats *n* sequential
calls — it should, and that is a service design input.

**Decision rule.**

| Outcome | Action |
|---|---|
| 6-crop frame ≤ 100 ms | docs/05 § 3's ceiling stands roughly as written |
| 6-crop frame > 100 ms | **re-derive the ceiling on the curve** and state concurrency as a range over scene complexity, not a single number |
| crop batching gives ≥ 2× | make batched crop inference a service requirement in docs/01 § 2, not an optimisation |

**Cost.** One CPU kernel. No training.

**Resolves.** docs/05 § 3 · docs/04 § 1's "multi-bin scenes are free" · docs/00
§ 6's concurrency success criterion.

---

## P5 – Validator architecture

**Question.** Does RF-DETR-nano or D-FINE-N fit 50 ms at 448 on two pinned vCPUs?
Research note 01 § 3 reports DETR backbones generalising better from small data,
which is our regime — but the published comparisons are on GPU.

**Method.** Latency first, on untrained weights, through the same
`bench_latency` path as P4. Only if a candidate fits the budget does accuracy
become a question worth a GPU hour.

**Decision rule.**

| Outcome | Action |
|---|---|
| no candidate fits 50 ms on 2 vCPU | **YOLO11n stays.** Close the question and record the numbers so it is not reopened on a blog post |
| a candidate fits with ≥ 20% headroom | train it as a v1 alternative and compare on the frozen set |
| a candidate fits marginally | do not pursue during phase 2. Note it for phase 6, where cross-city generalisation is actually measurable |

**Cost.** One CPU kernel. No training.

**Resolves.** docs/04 § 6's architecture choice, with evidence rather than
inheritance from the predecessor.

---

## P6 – Open-weight VLM for batch labelling

**Question.** Can InternVL3 or Qwen3-VL satisfy
`ml/src/sbr/escalation/schema.py` reliably enough to replace the paid API?

**Method.** ~200 crops through a Kaggle GPU kernel. Report **schema-valid rate on
first attempt**, schema-valid after one repair pass, and form-factor agreement
against P1's adjudicated labels. Compare against a hosted batch-API run on the
same 200 crops.

**Decision rule.**

| Outcome | Action |
|---|---|
| first-attempt schema-valid ≥ 0.9 and agreement within 5 points of hosted | open-weight becomes the default; the paid path becomes fallback and the €0 constraint is literally true |
| schema-valid ≥ 0.9 only after a repair pass | still adopt — this is batch, offline, and retries are free on a GPU we already have |
| agreement materially worse | keep the hosted API with its batch discount; record what open-weight would need |

**Cost.** One Kaggle GPU kernel + a small hosted batch run.

**Resolves.** docs/04 § 3 step 4 · docs/05 § 5's paid path · docs/00 principle 5.

---

## Sequencing

| Order | Probe | Blocks |
|---|---|---|
| 1 | **P4, P5** | nothing — no model needed, run immediately |
| 2 | **P1** | the 403-crop adjudication pass, and therefore model B |
| 3 | **P3** | whether `autolabel/` needs SAM |
| 4 | **P6** | whether docs/05 § 5 keeps a paid path |
| 5 | **P2** (set construction) | nothing; scoring waits for model B |

P4 and P5 answer half the phase-2 gate without a training run. That is the
cheapest evidence available in this project right now, and it is available today.

## What this document is not

It is not a licence to keep probing instead of building. Each probe has a stated
cost and a decision rule; when the rule fires, the doc changes and the probe is
done. A probe that has run and not changed anything gets recorded as such — a
confirmed assumption is a result.
