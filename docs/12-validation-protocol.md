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

`test` is *scored* three times, and each is named so the count cannot drift: the
**historical reproduction** (which must use `test`, because the published 0.025 was
measured there), the **locked winner**, and the **fp32 control**. An earlier version of
this section said `test` was "touched exactly once", which was false - three evaluations
that select nothing is the honest description, and it is the *selecting* the split has to
be protected from. That historical row is also the only one calibrated from `val` - v1's
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
| **identifier** | `arudaev/smart-bin-identify` | **unpinned** | **none yet, deliberately** |

The two roles do not share a dataset, a builder or a shape — the validator gets
a YOLO detection tree from `build_yolo_tree`, the identifier a classification
tree from `build_classification_tree` over **adjudicated crops**, of which there
are currently none. Writing the identifier a contract today would be asserting a
composition nobody has produced. It gets one when its dataset exists, pinned in
the same commit as the pin.

**On the two negative ratios.** Both are correct and they answer different
questions: **15.7:1** within the Open Images subset (17 474 backgrounds against
that subset's 1 110 bin frames) and **11.8:1** against all positives (against
1 480). Neither may be quoted without saying which it is.

## What this document is not

It is not a licence to keep probing instead of building. Each probe has a stated
cost and a decision rule; when the rule fires, the doc changes and the probe is
done. A probe that has run and not changed anything gets recorded as such — a
confirmed assumption is a result.
