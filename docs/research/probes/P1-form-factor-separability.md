# P1 – Are the form factors separable from a crop?

*Run 2026-08-21. `ml/kaggle/probe_separability/`, kernel
`hlexnc/sbr-probe-separability`, Kaggle T4. Raw data:
[`data/P1-form-factor-separability.json`](data/P1-form-factor-separability.json).
Estimator frozen in [docs/12](../../12-validation-protocol.md#p1--form-factor-separability)
at `3093c54`, **one commit before the kernel that uses it was written**.*

**Question.** Are the form factors separable from a 320 px crop — specifically,
is `wheelie_small` vs `wheelie_large` a *size* distinction that resizing
destroys?

**Data.** All **403 blind adjudications**, reviewer `alex`, every verdict
`authored`, from `arudaev/smart-bin-identify@cda374c9`. The crop contract was
asserted before the GPU was requested.

---

## The verdict: the first row fires

| | embedding alone | + relative box area |
|---|---:|---:|
| **pairwise `wheelie_small`/`wheelie_large`** | **0.9834** | **0.9834** |
| majority-class baseline | 0.6823 | 0.6823 |
| balanced accuracy | 0.9809 | 0.9809 |
| three-class accuracy | 0.9851 | 0.9851 |
| three-class balanced accuracy | 0.9873 | 0.9873 |

Against a threshold of **0.75**, on a baseline of **0.6823**. The rule's first
row reads *"separable at ≥ 0.75 pairwise → **B is a three-class model**:
`wheelie_small`, `wheelie_large`, `igloo`"*, and it fires on the **embedding
alone** — so the second row, which would have made box area a service
requirement, does not.

**The class list is still the maintainer's decision.** This probe brings the
number; it does not edit `waste-streams.json`.

## The confusion, 3×3, out-of-fold

Rows are truth, columns prediction, over 402 crops (`street_basket` excluded —
see below). Identical for both variants.

| | igloo | wheelie_large | wheelie_small |
|---|---:|---:|---:|
| **igloo** (40) | **40** | 0 | 0 |
| **wheelie_large** (115) | 0 | **112** | 3 |
| **wheelie_small** (247) | 0 | 3 | **244** |

**Six errors in 402**, all of them between the two wheelie sizes. Not one crop
crossed between a wheelie and an igloo in either direction.

**`igloo`'s 40/40 must not be quoted clean.** It has **17 capture clusters**, so
`GroupKFold(5)` leaves 3–4 clusters per fold and the whole class rests on 17
independent scenes. A perfect score over 17 scenes is a small number of
observations agreeing with each other, not a strong estimate.

## Relative box area changed nothing, and the reason matters

The two variants produced **byte-identical confusion matrices** — the same six
crops wrong. That was checked rather than assumed, because an appended feature
that changes nothing at all looks like a feature that never arrived:

| | |
|---|---|
| distinct area values over 403 crops | **400** |
| variance | 0.0298 |
| median area, `wheelie_small` | **0.504** |
| median area, `wheelie_large` | **0.668** |

The feature is real and it does carry signal on its own. It changed no
prediction because the embedding alone already leaves only six errors, and one
standardised feature against 768 under an L2 penalty does not move a margin far
enough to flip any of them.

**But the honest reading is that this variant was weakly posed on this data, by
construction.** Every legacy crop comes from a photograph somebody deliberately
took *of a bin*, so the bin fills the frame whatever its physical size — 0.504
against 0.668 is a large overlap, not a separation. In deployment, relative box
area depends mostly on how far away the user is standing. **This probe should
not be read as "box area is useless to an identifier"**; it establishes only
that the crop alone is sufficient here, which is what the decision rule asked.

## What was excluded, and why it is recorded rather than merged

`street_basket`: **1 crop, 1 capture cluster.** It cannot appear in a training
fold and a test fold, so it can be neither fitted nor evaluated. It is dropped
from every number above and **recorded as a coverage gap** — not merged into
anything on the strength of one photograph.

The six form factors with no data at all — `underground`, `textile_bank`,
`sack`, `crate`, `wall_unit`, `container_bank` — keep their ids. An id with no
training data is a coverage gap, not a deletion.
[research/11](../11-open-images-form-factors.md) establishes that Open Images
cannot close it: zero `underground`, zero `textile_bank`, zero `wall_unit` in a
384-box sample.

## What this measured, and what it did not

**It measured the representation, not the model.** A linear probe on frozen
DINOv2-base CLS features at 224 px says the *information* is present in the
crop. Model B is `yolo11s-cls` fine-tuned at 320 px on 403 crops, which is a
different architecture, a different resolution and a much smaller effective
training set. **0.9834 here is not a prediction of B's top-1**, and B's own
number will be measured on its own split.

**It measured generalisation across capture clusters, not across cities.** Every
crop is Deggendorf, one week. `GroupKFold` on `capture_cluster` stops two
photographs of the same physical bin straddling a fold — which is the
predecessor's failure — but it cannot say anything about another city. The
project still has no geographic holdout.

## Two corrections, recorded where they stand

**The pre-registration said "~138 capture clusters". It is 100.** Measured:
`wheelie_small` 65, `wheelie_large` 56, `igloo` 17, `street_basket` 1, and 100
distinct clusters over the 403 crops. `default.yaml` already documented 100 and
the figure in docs/12 was simply wrong. Nothing about the estimator depended on
it — `GroupKFold(5)` over 100 clusters is ~20 per fold — but the number is
corrected rather than quietly left.

**Fold sizes are reported rather than assumed.** Across the five pairwise folds
the test half held 72–73 crops over 18–19 clusters, with 16–29 `wheelie_large`
in each. The class balance moves fold to fold, which is why balanced accuracy is
quoted beside accuracy everywhere.

## What this changes

- **docs/12 P1 — closed.** First row fires; box area is not needed.
- **B's class list** — the evidence is `wheelie_small`, `wheelie_large`, `igloo`,
  three classes, with `street_basket` dropped and recorded and six ids empty.
  **The decision is the maintainer's.**
- **docs/02's form-factor list** — unchanged. Nothing merged, nothing renamed.
- **docs/04 § 5's "seven of ten have no data"** — measured: six at zero, a
  seventh at one.
