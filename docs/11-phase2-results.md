# 11 – Phase 2 results (v1)

> Every number here names the split it was measured on and the hardware it
> ran on. A metric that was not measured says so; nothing is interpolated,
> carried over from another split, or omitted to make a table look full.

Generated 2026-08-13 by `ml/scripts/evaluate.py`.

## The phase-2 gate

docs/07 states it: **validator ≤ 50 ms @ 448 and identifier ≤ 25 ms per crop
on service CPU, and ≥ 10 concurrent scanners on the free tier.**

| model | measured p50 | budget | verdict |
|---|---|---|---|
| validator @ 448 | **26.6 – 33.0 ms** | ≤ 50 ms | **within budget**, ~40 % headroom |
| identifier @ 320, per crop | **17.4 – 21.7 ms** | ≤ 25 ms | **within budget** |
| concurrent scanners, 1 bin | **4.3 – 5.1** (predicted) | ≥ 10 | **not met** |

Latency hardware: **Kaggle CPU kernel, Intel Xeon @ 2.20 GHz, onnxruntime
pinned to 2 of 4 vCPU, onnxruntime 1.28.0.** `representative: false` – a
proxy for a service container, not one, and about **25 % noisy** between
two runs six minutes apart. Both runs are reported as a range for that
reason.

Measured 2026-08-16 by
[probe P4](research/probes/P4-multi-bin-cost-curve.md), on **stock COCO
architectures untrained on this project's data**. That is sound for
latency, which depends on architecture and input shape, and meaningless
for accuracy, which is not measured there.

**The two model budgets pass and the thing they were supposed to buy does
not.** The concurrency figure is derived from the measured frame cost, and
it is out by a factor of two against the gate. Two contributing findings,
both in P4:

- docs/05 § 3's arithmetic **double-counted the vCPUs** – it divided 2 vCPU
  by a latency that had already been measured on both of them. Capacity is
  ~13–15 frames/second, not 30.
- a frame costs **15–40 ms more than its two graphs**, most likely from
  alternating between two onnxruntime sessions. At one bin that is a third
  of the frame and nothing had budgeted for it.

The concurrency number above is still a **prediction from single-stream
latency**. The load test against a pinned 2-vCPU container measures it.

Two notes on how this page should be read:

- **Latency did not need a trained model**, and that is why the table
  above is no longer empty. ONNX cost depends on architecture and input
  shape rather than on weights, so P4 and P5 filled it from stock
  exports while the identifier is still blocked on the human pass.
- **The concurrency figure is a range over scene complexity.** One bin per
  frame is the easy end; a bank of six — which the PRD calls a normal
  input — costs about two and a half times as much and drops the ceiling
  to roughly two scanners.

## Architecture

[Probe P5](research/probes/P5-validator-architecture.md), same hardware.

| candidate | p50 @ 448 | budget | verdict |
|---|---|---|---|
| YOLO11n (incumbent) | 26.6 – 33.0 ms | ≤ 50 ms | fits |
| RF-DETR-nano | **475.3 ms** | ≤ 50 ms | **9.5× over** |
| D-FINE-N | – | ≤ 50 ms | **not evaluated** – export failed |

**YOLO11n stays.** 475 ms is not a near miss and no amount of tuning
closes a 9.5× gap. D-FINE-N is recorded as *not evaluated* rather than
*did not fit*, because a candidate that never ran has not answered the
question and writing it down as a failure would be manufacturing evidence
for a convenient conclusion.

### Targets, as distinct from gates

A gate is arithmetic the free tier depends on and it fails the build. A
target is how good the model is and it is reported. The sidecar now
carries both, in three categories — met, missed, and **unmeasurable**:

| target | role | status |
|---|---|---|
| `min_recall_heldout_city` ≥ 0.97 | validator | **unmeasurable** – no subset carries a second `region_id` |
| `min_precision_on_negatives` ≥ 0.97 | validator | _not measured_ – the run has not completed |
| `min_formfactor_acc_heldout_city` ≥ 0.85 | identifier | **unmeasurable** – same reason |

*Unmeasurable* is not *missed*. It means the evidence does not exist,
and it is reported rather than omitted so that the generalisation
question this phase exists to answer cannot be quietly dropped.

## What the models were trained on

_The validator run has not completed._

The split is **group-aware by capture cluster** – frames of one bin in one
visit share a split – and never random. docs/08 § 7.3's 0.9873 came from a
random 20 % of one capture session and is not comparable to anything below.

## Validator

| metric | split | value |
|---|---|---|
| mAP@0.5 | test (group-aware) | _not measured_ |
| mAP@0.5:0.95 | test | _not measured_ |
| precision | test | _not measured_ |
| recall | test | _not measured_ |
| mAP@0.5 | **held-out region** | _not measured_ |
| recall | **held-out region** | _not measured_ |

### Recall by bins per frame

docs/04 § 5 commits to this so a model that only works on one big centred
bin cannot hide behind an aggregate.

Not measured – the validator run has not completed.

Note that the legacy subset alone cannot fill the `4+` row: it has **no frame with four or more bins**.


### Precision on the negative corpus

Not measured – the validator run has not completed.


## Identifier

| metric | split | value |
|---|---|---|
| top-1 | test (group-aware) | _not measured_ |
| top-5 | test | _not measured_ |
| unknown rate | test | _not measured_ |
| accuracy when answering | test | _not measured_ |

_The identifier run has not completed._ It is blocked on the human
adjudication pass: the legacy labels are waste **streams**, and a stream
does not determine a shape, so `ml/scripts/adjudicate.py` has to run
before there is anything to train on.

## Novelty precision

The kill criterion in docs/07 is **< 0.5**, and the whole improvement loop
rests on the validator/identifier disagreement being a trustworthy signal.

**_not measured_.** It needs both models plus a human verdict on whether each
flagged frame was genuinely a new bin type, so it cannot be computed until
the identifier exists and its flags have been adjudicated.

## Numbers this project does not quote

- the predecessor's **95.2 % mAP@0.5** – a random split of one week of
  photographs in one city;
- the **0.9873** independent re-validation (docs/08 § 7.3) – same split, so
  it reproduces the memorisation rather than refuting it.

Both are in-distribution. Neither is this project's baseline.

