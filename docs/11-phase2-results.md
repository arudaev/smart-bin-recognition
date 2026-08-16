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
| validator | _not measured_ | ≤ 50 ms | **no artefact** – the run has not completed |
| identifier | _not measured_ | ≤ 25 ms | **no artefact** – the run has not completed |

Latency hardware: _not measured_

The concurrency half of the gate is **not answered here**: it needs the
inference service, which is phase 3. Latency is the half that can be
answered now, and it is the half the cost model's arithmetic rests on
(docs/05 § 3).

Two corrections to how this page should be read, from the 2026-08-16
hardening pass:

- **Latency does not need a trained model.** ONNX cost depends on
  architecture and input shape, not on weights, so
  [probes P4 and P5](12-validation-protocol.md) can fill the table above
  from untrained exports. This page reports *not measured* because
  nobody has run them yet, not because it is blocked.
- **The concurrency figure is a range.** Ten concurrent scanners assumes
  one bin per frame; a bank of six costs roughly three times as much
  (docs/05 § 3). Whatever lands here names the scene complexity it was
  measured at.

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

