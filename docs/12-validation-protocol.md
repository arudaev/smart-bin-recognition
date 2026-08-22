# 12 – Validation protocol

> How a claim gets tested before it gets hard-coded. Nine probes, each with its
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

> **RAN 2026-08-21 — [result](research/probes/P1-form-factor-separability.md).**
> The amended rule's **first row fires**: pairwise
> `wheelie_small`/`wheelie_large` **0.9834** out-of-fold against a 0.75
> threshold and a 0.6823 baseline, on the **embedding alone**, so box area
> is not needed as a service feature. The evidence points at a three-class
> B; **the class list itself is the maintainer's decision and the probe did
> not take it.**

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

### Amended 2026-08-21, before the probe ran

**The adjudication is finished — all 403 crops, not a 40-crop pilot** — and it
produced a result the rule above cannot fire on. Every row says "proceed with ten
classes" or "keep ten classes", and **ten classes is not available**:

| form factor | crops | capture clusters |
|---|---|---|
| `wheelie_small` | 247 | 65 |
| `wheelie_large` | 115 | 56 |
| `igloo` | 40 | 17 |
| `street_basket` | **1** | **1** |
| `underground`, `textile_bank`, `sack`, `crate`, `wall_unit`, `container_bank` | **0** | — |

docs/04 § 5 estimated "seven of ten have no data". Measured, it is **six at zero
and a seventh at one**. The remaining legacy crops cannot help: all 403 are
Glas/Biomüll/Papier/Restmüll, so the archive has no more form factors to give.

Run blind (`adjudicate.py --blind`), every verdict `authored`, none rejected.
That was necessary rather than fastidious: the pool's shipped proposals are a
stream→shape mapping, and against the finished pass **they are wrong on 116 of
403 crops — 28.8 %** — of which **111 are `wheelie_small` where the answer is
`wheelie_large`**, precisely the pair this probe tests. Primed, P1 would have
measured the mapping table and called the classes cleanly separable.

**What the probe still decides** (DINOv2 embeddings + linear probe over the 403
adjudicated crops, with and without relative box area):

| Outcome | Action |
|---|---|
| `wheelie_small`/`wheelie_large` separable at ≥ 0.75 pairwise | **B is a three-class model**: `wheelie_small`, `wheelie_large`, `igloo` |
| separable only *with* relative box area | three classes, and **box area is passed to the identifier as a feature** — a design change, not a tuning one. The crop alone is not enough and the service must send the box |
| not separable either way | **B is a two-class model**: `wheelie`, `igloo`. Merging two published ids is a taxonomy change and is the maintainer's decision, not the probe's — bring the number, do not edit `waste-streams.json` |
| `igloo` confuses with either wheelie below 0.6 | record it. `igloo` has 17 clusters, so a 70/15/15 group-aware split leaves ~2–3 in test and its per-class metrics will be noisy — say so wherever they are quoted, never quote them clean |

**What the probe does NOT decide, and must not.**

`street_basket` at **n=1 in one cluster** cannot be split across train/val/test at
all, so it cannot be trained and cannot be evaluated. It is **dropped from B's
class list and recorded as a known gap** — not silently omitted, and not merged
into anything on the strength of one photograph.

The **six form factors with no data keep their ids**. Ids are permanent; an id
with no training data is a *coverage gap*, not a deletion. B's sidecar carries
the classes it was actually trained on, the service reads the class list from the
sidecar, and everything B has never seen resolves to `unknown` — which is a
designed state with a real UI, and the honest answer.

Whether that coverage gap is acceptable for a Deggendorf pilot is a **product
decision and the maintainer's**: most bins there are wheelies and glass igloos,
but `sack` and `textile_bank` both carry Deggendorf pack rules and would go
unanswered. Bring the evidence; do not decide it.

**Whether Open Images can close the gap is a separate question** and is worth
asking before anyone labels anything again: the pinned dataset holds 1 110 Open
Images bin frames carrying 1 936 boxes from global street scenes, and nobody has
looked at what form factors are in them. Generate crops, sample, and **report
what is visibly present** — establish whether a second adjudication pass would
be worth a person's time before proposing one.

### The survey, frozen 2026-08-21, before a single crop was opened

A sample chosen after looking is not a sample, and a survey with no stated frame
becomes "I saw a few of those" by the time it is quoted. So:

| | |
|---|---|
| **Population** | all 1 936 boxes across 1 110 Open Images frames in `arudaev/smart-bin-detect@8666aa23` |
| **Sample** | **384 boxes, seed 20260821, without replacement.** Sampling unit is the **box**, not the frame — a frame with six bins contributes six chances, which is what "what form factors are in them" asks |
| **Categories** | the ten taxonomy form factors, plus **`uncertain`** (too small, too occluded, or genuinely ambiguous) and **`not_a_bin`** (the box is on something else) |
| **Output** | counts over the sample, by one observer, **reported as a visual survey and explicitly not as labels** |
| **Writes** | none. Nothing goes back into any manifest, and no crop acquires a `form_factor` |

**Why 384.** At n=384 a proportion is estimated to roughly ±5 points at 95 %
confidence in the worst case, which is the resolution the question actually
needs: *is there enough of form factor X to be worth a human pass?* is a
question about tens of percent, not about single crops.

**What this cannot do.** It cannot produce training labels — one observer, no
blind protocol, no adjudication record — and it cannot tell us whether a box is
correct, only what is inside it. It answers one question: whether a second human
pass over this corpus would find form factors the legacy archive does not have.

### The estimator, frozen 2026-08-21, before the kernel was written

The amendment above fixes the *rule* and not the *estimator*, and an unstated
estimator is one that can be chosen after seeing the number. There are enough
degrees of freedom here — which layer, which split, which regulariser — that
"0.75 pairwise" is not a fact until they are all nailed down. So:

| | |
|---|---|
| **Representation** | `facebook/dinov2-base`, revision recorded in the report. CLS token, 768-d. Resize shorter side to 256, centre-crop 224, ImageNet mean/std, fp32, `eval()`, no fine-tuning |
| **Estimator** | `LogisticRegression(penalty="l2", C=1.0, solver="lbfgs", max_iter=5000, class_weight="balanced", random_state=42)` |
| **Scoring** | `GroupKFold(n_splits=5)` on **`capture_cluster`**. A random split over 403 crops from **100** clusters measures memorisation, which is precisely the predecessor's mistake this project exists not to repeat. *(This row said "~138 clusters" when it was frozen; measured, it is 100 — `wheelie_small` 65, `wheelie_large` 56, `igloo` 17, `street_basket` 1. Nothing in the estimator depended on it, and the figure is corrected rather than quietly left.)* |
| **Scaling** | `StandardScaler` fitted **inside each fold**. It matters most in variant (b), where one feature has a wildly different scale from the other 768 |
| **Variants** | **(a)** embedding alone · **(b)** embedding ⧺ relative box area, `bbox_norm` w·h, appended as one feature |
| **Aggregation** | Out-of-fold predictions pooled across all five folds, then scored once |

**What gets reported, always together.** The decision rule reads the **pairwise
`wheelie_small`/`wheelie_large` OOF accuracy, fitted on those two classes only**.
It is quoted beside the **majority-class baseline** and the **balanced
accuracy**, because 0.75 on a 247/115 split is 0.68 of prevalence and a rule that
fires on the raw number alone would mistake the class imbalance for skill.

**The confusion matrix is 3×3, not 4×4.** `street_basket` at n=1 in one cluster
cannot be fitted and cannot be held out; it is recorded beside the matrix as
`n=1, not trainable, not evaluable` rather than occupying a row that would
suggest it was measured.

**`igloo` carries its caveat wherever it is quoted.** 17 clusters over 5 folds is
~3 per fold. Its per-class numbers will be noisy and are never quoted clean.

**Cost.** The adjudication is done. One Kaggle GPU kernel for the embeddings and
the probe. No training.

**Resolves.** docs/02's form-factor list · docs/04 § 5's "seven of ten have no
data", now measured · the class list `adjudicate.py` presents · **B's class list**.

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

*That scoping was reversed on 2026-08-22. The paragraph above is left standing
because it is what the probe was written against; the amendment below is what it
now runs under.*

### That scoping is now the binding constraint on the product — observed 2026-08-21

Both models exist, and a real Deggendorf frame was run through the real service.
The **glass path answers**: a legacy `Glas` frame returns
`form_factor: igloo`, `body_color: metal`, `stream: glass_mixed`,
`local_name: "Glascontainer"`.

**Every wheelie answers `unknown`**, and not because anything failed. The
validator finds it, the identifier names it correctly at 0.98–0.99 confidence,
colour measures its body — and then **all four wheelie rules in the Deggendorf
pack match on `lid_color`**, which the service does not measure:

| rule | matches on |
|---|---|
| `deg-residual-wheelie` | `lid_color: black, grey` |
| `deg-paper-wheelie` | `lid_color: blue` |
| `deg-bio-wheelie` | `lid_color: brown` |
| `deg-packaging-wheelie` | `lid_color: yellow` |

The sharpest case observed: a `Papier` bin came back with `body_color: blue` —
the exact colour `deg-paper-wheelie` looks for — and still resolved to
`unknown`, because the rule reads the *lid*.

**So lid-vs-body separation is no longer a tidy-up after P3; it is what stands
between a working two-model pipeline and an answer for the commonest bin in
Deggendorf.** `igloo` is 40 crops of the project's data and the only form factor
that currently resolves; `wheelie_small` and `wheelie_large` are 362 crops and
resolve to nothing. That reorders P3's own priorities and is recorded here
rather than acted on.

### Amended 2026-08-22 — the lid is in scope, and the labeller is disclosed

**Why the scoping is reversed.** The paragraph above says *"measure body colour
first"*, and the section above it records why that ordering no longer serves: the
glass path answers, and 362 of 403 crops resolve to nothing because the pack's
four wheelie rules match on `lid_color` and nothing measures a lid. Deferring the
lid to a second probe would cost a second labelling session for a field that is
free to record while the crop is already open. So P3 now records **both**, and
reports **two agreement numbers rather than one**.

The body half of P3 is unchanged: same four CIELAB variants, same decision rule,
same three outcomes. The lid is added beside it, with its own rule.

#### The sample, frozen before a label was written

| | |
|---|---|
| **Population** | the 403 adjudicated legacy crops in `data/legacy/pool` |
| **Sample** | **160 crops, seed 20260821**: all 40 `igloo`, the 1 `street_basket`, and 119 wheelies drawn across the **92 distinct wheelie capture clusters** |
| **Why cluster-stratified** | one bin photographed eighteen times is one bin. The largest capture cluster here holds 18 crops; a simple random sample would spend a sixth of its budget on a single object and report the agreement of one lid as if it were many |
| **Why 160 and not P3's "~120"** | the lid rule is scored on wheelies **with a visible lid**, which is a subset of a subset. 119 wheelies is the number that keeps that subset wide enough to estimate a proportion to roughly ±8 points at 95 % |
| **Measured from** | the **full frame plus the box**, never the crop alone — `service/colour.py` estimates the illuminant from the whole frame, and its own docstring records that estimating from a crop *"turns every bin grey"* |
| **Fields** | `body_color`, `lid_color`, and **`lid_visible`** |
| **Writes** | a new `colour-labels.json`. Nothing touches `adjudication.json`, and no crop acquires or loses a `form_factor` |

**`lid_visible` is not bookkeeping.** A wheelie photographed square-on from the
front shows no lid at all. Scoring those as measurement failures would blame the
sampler for the camera angle, and — more importantly — the fraction of crops with
no visible lid is *itself a product answer*: if most real scanning angles cannot
see a lid, then a lid-colour rule cannot answer most scans however well the
sampler works.

#### Who labelled, stated plainly

**`labeller: claude`.** P3 says "hand-label" and the maintainer was away for this
run. These labels are recorded as **`provisional_proposals`, not ground truth**,
and they are marked as such in the data file, in this document, and in the
report.

**So P3 does not close on this pass.** What this run delivers is the tooling, the
frozen sample, the sampler, and a scoring harness that fires the moment human
labels exist. The verdict rows below are evaluated against human labels; run
against the provisional set they produce a **PROVISIONAL** number that must carry
that word everywhere it is quoted.

The maintainer pre-registered a **25-crop random spot-check** on return. That is
the minimum; `ml/scripts/colour_labels.py --label` runs the full blinded pass over
the same 160 if the spot-check disagrees enough to warrant it. Which of the two
happens is the maintainer's call and this document does not presume it.

#### The lid decision rule, frozen before the measurement

Scored on **wheelies where `lid_visible` is true**, against human labels.

| Outcome | Action |
|---|---|
| lid agreement **≥ 0.75** | wire the sampler through `service/pipeline.py`; `lid_color` is populated and the wheelie rules become reachable |
| lid agreement **0.60 – 0.75** | wire it, but bounded by ΔE so a poor sample returns `None` rather than a guess. Report it as **marginal**, never as solved |
| lid agreement **< 0.60** | **do not wire it.** Report that the Deggendorf pack matches wheelies on an axis this geometry cannot measure — which is a pack question, and the maintainer's |
| `lid_visible` **< 0.5 of wheelies** | record it beside whatever the agreement is. A sampler that is accurate on a third of frames does not make the product answer |

**What the lid half must not do.** It must not edit the region pack, and it must
not be read as corroborating one. The Deggendorf pack's own verification note
says no source consulted states a single container colour, so **measuring a lid
does not make a wheelie rule true** — it only makes it reachable. Whether an
uncorroborated rule should be shown to a user is a separate decision and is the
maintainer's.

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

## P7 – Video as the capture format

**Question.** Does one walk-around video yield more usable training signal per
hour of human effort than photographing bins individually — and does SAM 3 track
bins reliably enough that a human can adjudicate a **track** instead of a frame?

**Why it matters more than it looks.** Video containers carry GPS, so
`region_id` becomes real and the **geographic holdout stops being impossible**.
That converts the phase-2 hypothesis — detection generalises across cities,
identification does not — from untestable into testable. See
[research/08](research/08-video-ingestion.md).

**Method.** Film **two locations, ten minutes each**: one bank of containers, one
kerbside row. Then:

1. keyframe selection — sharpness, pose change, embedding distance from what is
   already kept;
2. SAM 3 concept prompt over the kept frames, producing tracks with stable IDs;
3. adjudicate **per track**, timed;
4. compare against the same wall-clock time spent photographing individually.

**Decision rule, stated in advance.**

| Outcome | Action |
|---|---|
| ≥ 5× usable **tracks** per human hour vs individual capture, and track IDs stay stable through occlusion | video becomes the primary capture format for the second-city round |
| 2–5× | adopt for multi-bin banks specifically, where the density advantage is largest, and keep photographs elsewhere |
| < 2×, or tracks fragment badly | drop it. Record why, so it is not re-proposed on the strength of a demo |

**What must be true before any video data enters a dataset** — already enforced,
not left to discipline:

- grouping is by **track**, never by frame (`prepare.py`, `MIN_FRAMES_PER_GROUP`);
- a frame declaring `source: video` with no grouping key is **refused**;
- counts are reported as tracks / objects / videos / locations, never as a frame
  total, or every ratio in docs/04 § 1 silently becomes fiction.

**Cost.** Twenty minutes of filming, one Kaggle GPU kernel, one timed
adjudication session. No training.

**Resolves.** docs/07 phase 2's held-out-city gap · docs/04 § 5's multi-bin and
empty-form-factor gaps · whether the human pass is affordable at scale.

---

## P8 – The three recoveries, and whether the gate can be recovered

**Question.** docs/07's phase-2 kill criterion has two halves. The first was
*recorded as fired* on 2026-08-17 — **4 concurrent scanners at one bin per frame
against a gate of 10**, and 1 at the six-container bank — and this probe found
that the 4 is not a figure the measuring host can hold still, so **neither half
is established**. The second half — *"and cannot be recovered"* — was untested
when this probe was written, because the three cheap recoveries
[docs/05 § 7](05-cost-model.md#7-when-it-stops-being-free-and-what-to-do) named
in advance have never been measured. This probe measures them.

**Why it is a probe and not a fix.** Each recovery is a change to what the
service costs, and the whole point of this document is that a change of that
kind gets a decision rule before it gets a number. Two of the three also carry a
cost that is not latency — 384 px trades recall for speed, a crop cap trades
coverage for speed — so "it got faster" is not on its own an argument for
adopting it.

**Method.** One 2-vCPU container, one variable at a time, three repeats per
configuration, measured by `service/loadtest/run.py` through
`service/loadtest/matrix.py`. Four properties make the comparisons admissible
and each exists because its absence would have produced a plausible wrong answer:

- **contiguous concurrency levels 1…12**, because a +1 improvement from 6 to 7
  is invisible on a ladder that steps 6, 8, 10, 12;
- **the verdict is the largest monotonic passing prefix**, not the highest
  passing level — one level scraping under budget above a failed one is noise
  wearing capacity's clothes;
- **a baseline bracket**: each scene runs `baseline → candidates in randomised
  order → baseline`, so thermal drift on the measuring host appears as the
  baseline-to-baseline difference. **A candidate delta smaller than that drift is
  rejected, whatever its sign.** The earlier proxy host varied ~25 % between runs
  six minutes apart;
- **one repetition owner.** `run.py --repeats` repeats; nothing else does, so
  three means three.

**Amended 2026-08-18, after the bracket failed.** The bracket did its job and
the block did not survive it: the identical baseline measured **7 concurrent
scanners at 22:30 and 4 at 23:48**, a drift of three against candidate effects
of one. More repeats cannot fix that — they all sit on the same side of the
drift. The fix is to shrink the *gap between the things being compared*, so
`matrix.py --paired` alternates two configurations **ABBA**, four minutes apart
instead of eighty, and reports the **paired within-cycle difference** rather
than two absolute numbers. `run.py` still owns repetition; a cycle is a
separate, individually reported measurement.

The bracket stays, because it is what detects the condition that makes pairing
necessary. **A serial block whose two baselines disagree is not a result**, and
should be reported as one only in the sense that it says the host cannot answer.

---

### P8a – The validator at 384 px

**Question.** docs/05 § 7 calls dropping the validator to 384 the first response
to saturation, and the validator is about a third of a one-bin frame. What does
it buy?

**Decision rule, stated in advance.**

| Outcome | Action |
|---|---|
| ≥ +1 concurrent scanner at 1 bin, in all three repeats, **and** larger than the bracket's own drift | adopt as a candidate; carry into the combined run |
| within the drift, or not reproduced | record as measured and rejected; docs/05 § 7 stops calling it the first response |
| a regression | say so; a recovery that costs capacity is a finding |

**What the number does not say.** Latency on an untrained graph is sound —
cost follows architecture and input shape. **Recall is not measured and is not
claimed.** Adopting 384 means retraining at 384 (`validator.yaml` `data.imgsz`
and `export.imgsz`), and what it costs on small distant bins is **unmeasured**
until a model exists. That caveat ships with the number or the number does not
ship.

---

### P8b – The 15–40 ms that belongs to neither graph

**Question.** [P4](research/probes/P4-multi-bin-cost-curve.md) found a frame
costing 15–40 ms more than its two graphs. At one bin that is a third of the
frame and nothing had budgeted for it. Where does it go, and does one shared
thread pool recover it?

**Two different quantities, and they must not be conflated.** P4's gap was
measured inside `bench_frame`, whose inner loop is exactly `validator.run()`
then `identifier.run()` — no JPEG decode, no letterbox, no NMS. The *service's*
gap includes all three. Both get decomposed and they answer different questions.

**Method, cheapest first.**

1. **Decomposition, before any profiler.** The load test measures wall clock,
   the response carries server-side `ms`, and `debug` carries `validator_ms` and
   `identifier_ms` separately. Subtracting gives four buckets:
   `validator_ms`, `identifier_ms`,
   `other_server_ms = ms − validator_ms − identifier_ms`, and
   `transport_ms = wall − ms`. What each holds is stated rather than assumed:
   `_validate` includes letterbox and NMS, `_identify` times only `session.run`,
   so crop preprocessing, JPEG decode, colour and resolve land in
   `other_server_ms`.
2. **Isolate switching from two-graphs.** Three timings on the same host: one
   session called twice back-to-back; **two sessions of the same graph**
   alternating; the validator and identifier alternating. If the second carries
   the penalty, session switching itself is the cause and the second model is
   not the story.
3. **Config, one variable at a time.** Separate onnxruntime sessions get
   separate intra-op thread pools and spin by default, which on two cores means
   four spinning threads competing for two. `SBR_ORT_SPINNING=0`,
   `SBR_ORT_SHARED_POOL=1`, `SBR_IDENTIFIER_THREADS=1`.

**Decision rule, stated in advance.**

| Outcome | Action |
|---|---|
| `other_server_ms` < 10 ms at one bin | the gap was the **bench's** artefact, not the service's. Close the item and correct P4's "what would move it" list |
| one config change recovers ≥ 8 ms at p50, reproduced ×3 | adopt it; carry into the combined run |
| the gap is real and no config change moves it | record the single-graph merge as **scoped and not done**, with an estimated cost. Do not attempt it in the same pass as a measurement |

---

### P8c – Capping crops at three

**Question.** docs/05 § 7 names capping crops below the default six. What does
it buy at the six-container bank, which is the only place it can help?

**It cannot move the one-bin number, and the gate is stated at one bin.**
Reporting `SBR_MAX_CROPS=3` as progress against the headline figure is the same
error as quoting 10 was.

**What has to be fixed before it can be measured at all.** The test hook
replaced the crop list *after* the cap was applied, so a forced six-bin scene ran
six crops however the cap was set — the probe would have measured nothing and
reported a number. In forced mode the forced boxes are now the scene and the cap
applies to them. **The run is refused unless a debug frame at
`SBR_FORCE_CROPS=6, SBR_MAX_CROPS=3` reports exactly six detections and three
identifier crops.**

**What the cap actually costs.** docs/05 § 7 and `settings.py` both said the
remainder is *"deferred to the next frame"*. **It is not, and never was.**
`pipeline.py` truncates and never revisits; boxes past the cap are drawn but
carry `form_factor: null` and no colour. So at six bins a cap of three means
three containers in a bank are permanently unidentified, not identified a frame
later. Deferral is buildable — the client's result lock at three stable frames is
the natural place for it — and it is product work, not this probe's.

**Decision rule, stated in advance.**

| Outcome | Action |
|---|---|
| ≥ +1 concurrent scanner **at 6 bins**, ×3, outside the drift | adopt as a **saturation response**, not a default, and record the coverage it costs |
| no change | record as measured and rejected |
| reported against the one-bin figure | not an outcome. The gate is at one bin |

---

### The verdict, and what this host may not conclude

Read off the **combined** configuration — every adopted recovery at once.
Attribution comes from the singles; the verdict comes from the combination.

The measuring host is `docker run --cpus 2`, `linux/arm64` on a Snapdragon
X1E80100. **Cloud Run is x86_64.** A pinned proxy can screen candidates and
establish within-host deltas honestly; it cannot pronounce on the serving tier.

| Combined result at 1 bin | Conclusion |
|---|---|
| ≥ 10 | **"capacity recovery demonstrated on the ARM proxy; production gate pending x86 confirmation."** Not "the thesis survives" — that needs a controlled 2-vCPU x86 host, and until that run exists the gate stays open |
| 5–9 | the gate is **not met**. The free-tier serving thesis as written is dead |
| ≤ 4 | the same, more starkly; the recoveries are recorded as measured and insufficient |

In every branch the gate stays stated as **10**. It is never restated as its
measured value.

**And if it is not met, the alternative is named and costed, not gestured at.**
docs/05 § 7's *sustained saturation* row — more vCPU — is the relevant one.
**HF PRO's USD 9 `cpu-basic` is not**: it is still 2 vCPU, it answers *"streaming
becomes necessary"*, and it buys a persistent socket rather than compute. It
cannot close a compute gate.

**Cost.** No GPU, no model, no training. About three hours of unattended
container time.

**Resolves.** docs/07's kill criterion, second half · docs/05 § 3's ceiling and
§ 7's response ladder · docs/11's concurrency table.

**Ran 2026-08-17/18. [Result](research/probes/P8-recovery-measurements.md).**
P8b fired and is adopted — a shared onnxruntime thread pool, worth −105 ms at
p95. P8a and P8c are **not established**. The verdict rule above **did not
fire in either direction**, because it reads an absolute number and the host
could not supply one: the same baseline gave 7 and then 4 in a single evening,
on a laptop that was also running the development tooling, where
`docker run --cpus 2` is a ceiling and not a floor. **The gate has not passed**
— nothing was ever observed at ten — and neither has it been shown to fail,
because the measurement it would fail on is not admissible. What it waits on is
**a controlled 2-vCPU x86 host**, not another idea.

---

## P9 – Why int8 destroys the validator

> **ANSWERED 2026-08-21.** Quantising the detection head is what causes the
> collapse: excluding `/model.23/` moves the model from 0.015 to **0.7481** on
> `val`. Nothing else helps — the three remedies onnxruntime names for this
> failure mode (S8S8, `reduce_range`, U8U8) stay at collapse, as does
> per-tensor, and the pre-registered combined run made things *worse*. The best
> configuration is **0.0252 below** the PyTorch fp32 reference against a 0.02
> budget, so the middle row of the rule below fires: **the gate is missed, the
> model is real, and the gate does not move.** Where that residual 0.0252 lives
> is **not** established — the head-fp32 graph is still quantised everywhere
> else. Full result, including three things this probe got wrong before it got
> them right:
> [probes/P9-int8-quantisation.md](research/probes/P9-int8-quantisation.md).

**Question.** The first completed validator scores **mAP@0.5 = 0.7524389678079388 in
fp32 and 0.025 in int8**. Which part of the quantisation does that, and is there a
configuration that keeps the model inside the 0.02 budget?

**Why it is a probe and not a fix.** There are several plausible culprits and they imply
different remedies. onnxruntime's own guidance names the first two: **QDQ with S8S8 is
normally the right choice on CPU**, and a large accuracy loss under **U8S8 – which is
what this exporter uses – is a known symptom of x86 activation saturation**, whose
remedies are `reduce_range=True` or U8U8. Beyond the numeric format: per-channel weight
quantisation may be wrong for this graph; the detection head's box-regression outputs are
wide-range and quantise badly; and the calibration set is not what it should be, in a way
described below. Guessing costs a re-export and teaches nothing.

**The calibration set is not what the first draft of this probe claimed.** It was written
here as "`dataset/images/val`, which is 92 % background". That is the *split*; it is not
the *sample*. `quantise` takes the **first 200 lexicographically sorted files**, which is
a systematic sample and not a random one. Reconstructed against the pinned tree at
`8666aa23ff1a`, the 200 images actually used were:

| | |
|---|---|
| val split as a whole | 2 582 / 2 823 background = **91.46 %** |
| the 200 actually used | 149 background + 51 positive = **74.5 % background** |
| their provenance | 51 legacy, 149 negatives, **zero Open Images frames** |

So the real defect is not the background ratio. It is that the calibration set is drawn
by filename order, sees **no Open Images frame at all**, and therefore calibrates
activation ranges on a subset that does not resemble the data the model is scored on.
`first_lexicographic` is kept as a reproducible strategy precisely so this can be
measured rather than asserted.

**A second mismatch, in the same function.** The calibration reader **stretches** to
`(imgsz, imgsz)`, while `model.val()` and the inference service both **letterbox** –
aspect preserved, padded with 114-grey. The ranges were calibrated on a geometry that
never occurs at inference, and never on the grey bars that cover a third of a real frame.

### Data partitioning – the part that makes the answer usable

**Calibration draws from `train` only. Every variant is scored on `val`. No candidate
is ever selected on `test`.**

This is not pedantry. Selecting a winner on `test` and then reporting that winner's
`test` score as ship-gate evidence turns the test split into a tuning set, and the gate
into a number that was tuned against.

`test` is scored **at most** three times, and each is named so the count cannot drift:
the **historical reproduction** (which must use `test`, because the published 0.025 was
measured there) — always; then the **locked winner** and the **fp32 control** — *only if
a candidate is eligible*. When nothing qualifies there is nothing to confirm and the
split is spent once, which is what happened on 2026-08-21. An earlier version of this
section said `test` was "touched exactly once", and then said it was scored three times;
both were wrong in the same way — asserting a fixed count for something conditional. What
is invariant is that **nothing is ever selected on `test`**, and that is the property the
split has to be protected for. That historical row is also the only one calibrated from `val` - v1's
own first-200 list - because reproducing what happened is the whole point of it, and it
is never a candidate.

### The three drops, reported separately

The fp32 ONNX control is necessary – the 0.7524 came from PyTorch on a GPU and the 0.025
from onnxruntime on a CPU, so precision is not the only thing that changed between them.
But it **must not become the denominator**, or a lossy fp32 export would lower the
reference and let a bad int8 graph appear to pass:

```
export drop        = PyTorch fp32  −  ONNX fp32
quantisation drop  = ONNX fp32     −  ONNX int8
total served drop  = PyTorch fp32  −  ONNX int8      ← the only one the gate reads
```

Shipping requires `0.7524389678079388 − final_int8_test_map50 ≤ 0.02`. `check_gates`
already computes exactly this, provided `map50_fp32` in the sidecar holds the **frozen
PyTorch value**; a re-export that recomputed a friendlier reference would silently
redefine the gate, so it is pinned by a test.

### Method

**Gate 0 – reproduce before remedying.** Download `v1/validator-v1.onnx` and hash it.
Pin `ultralytics==8.4.121` (the version recorded inside `best.pt`) and record the
resolved `onnx` and `onnxruntime` versions. Re-export and re-quantise with the historical
settings and the historical calibration list, and compare SHA256. Dependencies in this
repo are lower-bounded rather than pinned and the Hub holds no fp32 ONNX, so a byte
mismatch is a **toolchain confound to record**, not a failure – but the *metric* must
reproduce. **If it does not land near 0.025, stop.** Every remedy below is meaningless
against a baseline that does not reproduce.

Then two axes, one variable at a time, from a single reference **R** – the shipped
settings calibrated on a seeded stratified 200 from `train`. All scored on `val`:

| Axis | Variants |
|---|---|
| numeric format | **S8S8** · **U8S8 + `reduce_range`** · **U8U8** · per-tensor · head (`/model.23/`) left in fp32 |
| calibration | historical first-200-of-`val` · **R**, stratified from `train` · positive-enriched 100/100 · letterboxed rather than stretched |
| informational only | fp32 ONNX control · fp16 |

If the best of each axis is a different knob, one combined confirmation run, also on
`val`. Every row carries a p50/p95 from the same instrument `bench_latency` uses, and
**the complete ordered calibration list is recorded** – written once per set under
`calibration_sets` and referenced from each row by SHA256, because a hash fingerprints a
set without ever saying what is in it.

**Which tensor, not just which knob.** onnxruntime's own QDQ debugger runs the float
and quantised graphs over the same frames and scores each activation, so the write-up can
name the layer instead of leaving nine variants to imply one. The score is **SQNR in
decibels and higher is better** - `20·log10(‖x‖ / ‖x−y‖)` - so the damaged tensors are
the ones at the *bottom*. Recorded because getting it backwards is easy and was: a first
pass sorted descending, called the result "the worst tensors", and drew a conclusion from
what were in fact the eight best-preserved tensors in the graph.

**A failed load is a valid result.** Each row requires either a metric or an **error**,
never a number invented to fill a column.

### The winner is chosen by a rule, not by inspection

Eligible = `val` mAP within 0.02 of the **PyTorch fp32** `val` mAP, measured from
`best.pt` in the same kernel. It must be the PyTorch score and not the fp32 ONNX one: a
lossy export would otherwise lower the bar its own candidates are judged against, which is
the same failure the three-drop accounting prevents, one split further up.

Among eligible variants the criteria apply **in sequence, filtering** – not as a scored
ranking: highest `val` mAP, then everything within **0.005** of it; of those the lowest
p50, then everything within **1 ms** of that; of those the *simpler, fully-int8*
configuration – fewest departures from the default, and no head left in fp32; and the
variant name last, so a tie surviving all four is still deterministic. Rounding the two
continuous quantities into buckets and sorting on the tuple is **not** the same rule and
picks a different winner near a bucket edge; the implementation lives in
`sbr.export.selection` where it can be tested, rather than inside a kernel that cannot be
imported.

**When the two axes disagree** – the best format is not the reference and the best
calibration is not the reference – the combination is built and scored on `val` too.
Without it the probe could conclude that post-training quantisation cannot recover the
model when two remedies are jointly necessary and neither suffices alone.

**fp16 is informational and may not decide shipping.** onnxruntime's CPU runtime does not
broadly support fp16 operations – it is a GPU optimisation – so an fp16 row measures a
configuration this service cannot serve. It is reported because it bounds what the
weights are capable of, not because it is an option.

**Decision rule, stated in advance.**

| Outcome | Action |
|---|---|
| a variant's **total served drop** on `test` is within **0.02** | adopt it; pin the export settings in `validator.yaml` with the run that produced it |
| the best is 0.02–0.10 | the gate is missed but the model is real. **Do not loosen the gate** - report it, and decide the trade explicitly against the latency the alternative costs |
| nothing recovers it | validator v1's weights cannot yield a shippable **post-training** int8 export. That points at quantisation-aware training or a different head, and P5 reopens with that question |

**What must not happen.** `export.gates.max_accuracy_drop` is 0.02 and it stays 0.02. It
was added on 2026-08-16 because int8 accuracy had no owner and `may_ship` was
unreachable; it fired on the first real run and caught a model that would have served
noise. **A gate that is widened the first time it fires was never a gate.**

**Cost.** One CPU kernel. An earlier version of this section said "minutes"; that was
wrong – the run pulls the 2.2 GB pool, rebuilds the tree, and scores roughly fourteen
passes over `val` plus two over `test`. Estimate **3–5 hours**, inside Kaggle's 12 h CPU
limit and still free. No GPU, no retraining.

**Resolves.** Whether validator v1 can ship at all · docs/04 § 6's export settings · the
third of docs/07 phase 2's remaining blockers.

---

## P10 – Where the residual 0.0252 lives

*Pre-registered 2026-08-21, before the probe ran.* **RAN 2026-08-21 —
[result](research/probes/P10-where-the-residual-lives.md). Two rows fired: the
0.02–0.10 miss, and the ranking-versus-sweep disagreement. No module outside the
detection head accounts for the residual by a distinguishable amount; the best
configuration misses the gate by 0.0054 and the gate did not move.**

**Question.** [P9](research/probes/P9-int8-quantisation.md) established that
quantising the detection head is what collapses the validator: excluding
`/model.23/` recovers it from 0.015 to 0.7481 on `val`. It did **not** establish
that nothing outside the head matters — that graph still carries **619 QDQ nodes**
and still loses **0.0252** against a 0.02 budget. Where does the residual live,
and can it be recovered for free?

**Why it is a probe and not a fix.** The obvious suspect is not evidence. A local
smoke test on a stock YOLO11n reported a **1517× weight-scale increase** on
`model.10.m.0.attn.qkv.conv.weight` — the C2PSA attention block in the backbone —
which is a hint and nothing more. onnxruntime's QDQ debugger can name the layer
instead of leaving a sweep to imply one, and **it has never been run**:
`quantisation_error` only fires on a winner and P9 had none, so `tensor_error` on
the head-fp32 graph is empty.

**The direction of that diagnostic is a trap and is written down here because it
already caught someone.** `qdq_err` is **SQNR in decibels** —
`20·log10(‖x‖/‖x−y‖)` — so **higher is better** and the damaged tensors are at the
*bottom*. P9's first pass sorted descending, called the result "the worst
tensors", and named the eight best-preserved tensors in the graph as suspects.

**Method.** One CPU kernel, no GPU, no retraining, all exports from the existing
`v1/best.pt`. Same partitioning as P9: calibrate from `train`, score on `val`,
touch `test` only to confirm a locked winner.

1. run the corrected SQNR diagnostic on the **head-fp32** graph and rank
   activations by *lowest* SQNR;
2. exclude, one at a time, the module the ranking actually points at — plus
   `/model.10/` regardless, because it is the standing hypothesis and leaving it
   untested would make the result unfalsifiable;
3. a combined exclusion if two modules independently help.

Every row carries its settings, its calibration hash, its QDQ boundary, its
latency, and **either a metric or an error** — never a number that was not
measured.

**Decision rule, stated in advance.**

| Outcome | Action |
|---|---|
| a configuration reaches **total served drop ≤ 0.02** on `val` | lock it, confirm **once** on `test`, pin the settings in `validator.yaml` with the run that produced them, publish as **v2**. v1 stays exactly as it is — it is the record docs/11 quotes |
| best is 0.02–0.10 | the gate is missed and the model is real. **Do not move the gate.** Record what the alternative costs and **stop** — whether to attempt quantisation-aware training is the maintainer's decision |
| nothing improves on head-fp32 | head-fp32 stands as the best known configuration, validator v1 cannot ship as a post-training int8 export, and P5 reopens with that question |
| the SQNR ranking and the exclusion sweep disagree | **believe the sweep.** A ranking is a pointer; an exclusion that changes mAP is a measurement. Record the disagreement rather than resolving it quietly |

**What must not happen.** `export.gates.max_accuracy_drop` is 0.02 and stays
0.02. It has fired twice on this artefact and been right twice. No variant is
invented after seeing results — a new question is a new probe.

**Cost.** One free CPU kernel, no GPU, no retraining.

**Resolves.** Whether validator v1 can ship at all · docs/04 § 6's export
settings · the last of docs/07 phase 2's model blockers.

---

## P11 – What int8 costs the identifier

> **RAN 2026-08-21 — [result](research/probes/P11-identifier-int8.md).** The
> first row fires, **on the first variant**: the shipped defaults cost
> **0.0000** top-1 on `val` and on `test`, so the sweep never ran. Consistent
> with P9's diagnosis and not proof of it — the task is saturated, and on 56
> `val` crops the measurement's resolution (0.018) is about the size of the gate
> (0.020). The accuracy gate passes; latency is the only blocker left.

*Pre-registered 2026-08-21, **before model B was trained**. B does not exist
yet; this exists so that whatever it scores is judged by a rule nobody could
have chosen with the number in front of them.*

**Why it needs its own entry.** [P9](research/probes/P9-int8-quantisation.md)
and [P10](research/probes/P10-where-the-residual-lives.md) diagnosed the
*validator*. It is tempting to carry the diagnosis across — "quantise everything
but the detection head" — and it does not transfer: **a `yolo11s-cls` has no DFL
detection head to exclude.** There is no `/model.23/` box-regression branch,
which is precisely the structure P9 identified as the cause. So the identifier's
int8 behaviour is *unknown*, not *predicted*, and must be established.

**Gates, unchanged.** int8 top-1 drop **≤ 0.02**, median **≤ 25 ms per crop** on
service CPU. `export.gates.max_accuracy_drop` stays 0.02. A missed gate is
reported; it is never widened.

### The partitioning, which is the part that goes wrong quietly

The kernel as written before this entry evaluated fp32 on `test`, calibrated on
`val`, then evaluated int8 on `test` — so any sweep would have selected on the
split it later reported. Corrected, and in this order:

1. **calibrate from `train`**;
2. score the fp32 baseline and **every** variant on **`val`**;
3. lock exactly one candidate, by `sbr.export.selection.choose_winner`;
4. score that candidate **once, on `test`**. That is the only ship-gate number.

If nothing is eligible, **`test` is not touched at all** and the split stays
unspent — as it did for P9 and P10.

### The sweep, enumerated here rather than deferred

If int8 costs more than 0.02 top-1 on `val`, these variants run — **this list and
no other.** "The same sweep P9 used" is not a specification, and inventing an
extra variant after seeing a result is the failure this whole document exists to
prevent.

| variant | what it changes |
|---|---|
| `10-reference` | the shipped defaults: U8S8, per-channel, minmax, stretched calibration |
| `11-s8s8` | onnxruntime's named "normal CPU choice" |
| `12-reduce-range` | its documented remedy for x86 activation saturation |
| `13-u8u8` | the other documented remedy |
| `14-per-tensor` | per-channel off |
| `15-preprocessed` | `quant_pre_process` on |
| `16-letterboxed` | calibration fitted the way inference fits |

**`exclude_head` is deliberately absent.** There is no head to exclude. A variant
named for a structure the graph does not have would measure the reference under
a different label.

### The decision rule, stated in advance

| Outcome | Action |
|---|---|
| a variant is within **0.02** top-1 of the PyTorch fp32 reference on `val` | lock it, confirm **once** on `test`, pin the settings in `identifier.yaml` with the run that produced them |
| best is **0.02–0.10** | the gate is missed and the model is real. **Do not move the gate.** Record it and stop; what to do instead is the maintainer's decision |
| nothing improves on the reference | post-training int8 is not viable for this architecture either, and that is a finding about the export path rather than about B |

### Two numbers that are not gates, and are labelled as such wherever quoted

- **top-5 is meaningless at three classes.** It is reported because the harness
  computes it, and it must never be read as accuracy.
- **`unknown_threshold: 0.55` is provisional and uncalibrated.** It is a guess,
  max-softmax is a baseline rather than a principled score, and P2 replaces it
  with an operating point chosen at a stated novelty precision. Any `unknown`
  rate B reports is a property of that guess as much as of the model.

**Cost.** No extra kernel: the sweep runs inside the training kernel, on a graph
it has already exported.

**Resolves.** Whether model B can ship · docs/04 § 6's export settings for the
classification path.

---

## P12 – The controlled host

*Not pre-registered, because it is not a probe: it is the phase-2 gate, measured
where the gate says to measure it. It is numbered here so the result has a home
beside the probes that predicted it.*

**RAN 2026-08-21 — [result](research/probes/P12-the-controlled-host.md).**
Latency **passes** on `representative: true` hardware — validator 18.3 ms
against 50, identifier 9.9 ms against 25. Concurrency **fails**: **5** scanners
at one bin against a gate of 10, and **2** at six bins.

The first admissible absolute concurrency figure the project has had. It
supersedes the withdrawn 4 and 1, and it lands inside P4's corrected prediction
of 4.3–5.1 and 1.8–2.2.

**One methodological lesson worth carrying.** The first pass reported 10 and 10.
`run.py --bins N` is a report label; `SBR_FORCE_CROPS` is what makes it true,
and it was unset, so the client's synthetic noise produced no detections and the
identifier never ran. Both halves measured a validator-only frame — and returned
curves identical to within 2 ms at every one of fourteen levels, which is what
exposed it. **Two configurations that agree exactly are not confirming each
other; they are the same configuration.**

---

## Sequencing

| Order | Probe | Blocks |
|---|---|---|
| 1 | **P4, P5** | nothing — no model needed, run immediately |
| 1 | **P8** | docs/07's kill criterion. No model needed either, and it is the only thing standing between "the gate failed" and a decision |
| 1 | **P9** | whether validator v1 can ship at all. One CPU kernel against weights that already exist |
| 2 | **P1** | the 403-crop adjudication pass, and therefore model B |
| 3 | **P3** | whether `autolabel/` needs SAM |
| 4 | **P6** | whether docs/05 § 5 keeps a paid path |
| 5 | **P2** (set construction) | nothing; scoring waits for model B |
| 6 | **P7** | whether the second-city round is filmed or photographed — and therefore whether the geographic holdout ever exists |

P4 and P5 answer half the phase-2 gate without a training run. That is the
cheapest evidence available in this project right now, and it is available today.

P7 is the highest-*ceiling* probe: it is the only one that can unblock the
generalisation question, which is the thing phase 2 exists to answer and
currently cannot.

## Dataset contracts – what a pinned revision is asserted to contain

A pin says *which* data. It does not say *what is in it*, and the difference
cost a GPU hour once already: the 2026-08-16 validator run built its dataset,
reported `background_images: 0` over a pool that is 92 % background, and started
training anyway. The counting bug is fixed; what was missing is anything that
would have **refused**.

So the composition is asserted against the pinned revision, before the expensive
work rather than after it:

| Role | Repo | Pinned | Contract |
|---|---|---|---|
| **validator** | `arudaev/smart-bin-detect` | `8666aa23ff1a…` | 18 954 frames = 17 474 background + 1 480 positive (370 legacy + 1 110 Open Images); 403 legacy boxes, 1 936 Open Images boxes |
| **identifier** | `arudaev/smart-bin-identify` | `cda374c9a55d…` | 370 frames, 403 boxes, **403 crops, all 403 adjudicated, 0 pending, 0 rejected** — and the per-class counts: `wheelie_small` 247, `wheelie_large` 115, `igloo` 40, `street_basket` 1 |

The two roles do not share a dataset, a builder or a shape — the validator gets
a YOLO detection tree from `build_yolo_tree`, the identifier a classification
tree from `build_classification_tree` over **adjudicated crops**.

**The identifier's contract landed 2026-08-21, in the same commit as its pin**,
which is what this section promised it would wait for. Until then it asserted
nothing, because the crops did not exist and describing them would have been
inventing evidence.

**It asserts labels, not just arithmetic**, and that is the whole reason it is a
separate check from `check_composition`. 403 crops can remain 403 crops, all 403
still adjudicated, while every form factor underneath them changes — a re-run of
`adjudicate.py`, a half-applied decision file, a merged class — and the
identifier would train on the difference without a word. So
`check_crop_composition` compares the **per-form-factor counts** and refuses on a
single crop moving between classes. `street_basket` is asserted at n=1 because it
*exists*: keeping it out of a class list is a coverage-gap decision, and
forgetting it is a different thing entirely.

A crop's `form_factor` is only counted once a human has decided it. The pool
ships a stream → shape *proposal* on every crop, and counting that would let the
guess satisfy a contract about the human pass — the proposal is wrong on 116 of
403.

**On the two negative ratios.** Both are correct and they answer different
questions: **15.7:1** within the Open Images subset (17 474 backgrounds against
that subset's 1 110 bin frames) and **11.8:1** against all positives (against
1 480). Neither may be quoted without saying which it is.

## What this document is not

It is not a licence to keep probing instead of building. Each probe has a stated
cost and a decision rule; when the rule fires, the doc changes and the probe is
done. A probe that has run and not changed anything gets recorded as such — a
confirmed assumption is a result.
