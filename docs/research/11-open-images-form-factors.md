# 09 – What is actually in the Open Images bin frames

*Surveyed 2026-08-21. Protocol frozen in [docs/12 P1](../12-validation-protocol.md)
**before a single crop was opened**. Raw counts:
[`data/open-images-form-factor-survey.json`](data/open-images-form-factor-survey.json);
the sample's provenance, cell by cell, is in the run's `index.json`.*

**This is a visual survey and not a labelling pass.** One observer, one sitting,
not blind, no adjudication record. Nothing was written back to any manifest and
no crop acquired a `form_factor`. What follows is *counts of what was visibly
present in a sample* — the weakest claim that still answers the question, which
is: **would a second human pass over this corpus be worth a person's time?**

**Method.** 384 of the 1 936 Open Images boxes in
`arudaev/smart-bin-detect@8666aa23`, sampled without replacement at seed
20260821, unit = the box. Cropped at the identifier's own padding (0.12) so what
was inspected looks like what the model would get, tiled 48 to a contact sheet,
and looked at. `ml/scripts/survey_open_images.py` regenerates it exactly.

---

## The counts

| form factor | n | % of 384 |
|---|---:|---:|
| **`street_basket`** | **135** | **35.2 %** |
| `wheelie_small` | 76 | 19.8 % |
| `wheelie_large` | 16 | 4.2 % |
| `container_bank` | 7 | 1.8 % |
| `crate` | 3 | 0.8 % |
| `igloo` | 2 | 0.5 % |
| `sack` | 1 | 0.3 % |
| `underground` | **0** | — |
| `textile_bank` | **0** | — |
| `wall_unit` | **0** | — |
| *no matching form factor* | 11 | 2.9 % |
| *not a bin* | 4 | 1.0 % |
| ***uncertain*** | **129** | **33.6 %** |

At n=384 a proportion carries roughly ±5 points at 95 %, so read these as tens
of percent and not as decimals.

## Four findings

### 1. Open Images is a street-litter corpus, and that is the opportunity

`street_basket` is **the single largest category at 35 %** — public litter
baskets, round dustbins, metal slatted bins, concrete columns, the things bolted
to lamp posts. The legacy archive has **exactly one** `street_basket` crop, in
one capture cluster, which is why docs/12 P1 has to drop the class entirely.

**This is the one class where a second human pass would clearly pay.** A 35 %
prevalence over 1 936 boxes projects to roughly 600–700 street baskets in the
corpus, against a current total of one.

Whether that is *worth wanting* is a separate question and it is the
maintainer's: the taxonomy's own note says `street_basket` is *"almost always
residual; never a sorting target"*. A class the product answers with one fixed
sentence may not need 600 training crops. The data is there; the demand for it
is a product judgement.

### 2. It does **not** close the coverage gap, and that is the more useful answer

Of the six form factors with no legacy data at all:

| | found in 384 |
|---|---|
| `underground` | **0** |
| `textile_bank` | **0** |
| `wall_unit` | **0** |
| `sack` | 1 |
| `crate` | 3 |
| `container_bank` | 7 |

**Five of the six stay empty or near-empty.** Open Images' `Waste container`
vocabulary simply does not contain underground drop columns, clothing banks or
in-store battery boxes in any quantity, and no amount of adjudication over this
corpus will produce them. If those classes are wanted, they need a capture round
— which is the argument [P7](../12-validation-protocol.md#p7--video-as-the-capture-format)
already makes for other reasons.

`igloo` at 2 is worth its own line: the legacy archive's 40 igloo crops in 17
clusters remain **the project's entire glass-bank corpus**, and Open Images does
not help.

### 3. A third of the sample cannot be read, and the reason is measurable

**129 crops (33.6 %) were too small, too occluded or too ambiguous to call.**
That is not a soft impression — it tracks a hard number in the pool:

| | |
|---|---|
| median shorter side of a sampled crop | **94 px** |
| crops below **64 px**, which is `identifier.yaml`'s own `crops.min_box_px` | **112 (29.2 %)** |

Open Images frames were resized to 448 px on ingest, so a small bin in a wide
street scene survives as a 20–40 px smear. **The pipeline would reject most of
these before a human ever saw them**, so the effective yield of an adjudication
pass over this corpus is closer to two thirds of the boxes than to all of them.

That is a fact about this pool and not about Open Images: the boxes are fine, the
448 px ingest is what threw the pixels away. Re-harvesting at a larger size would
recover them, and is a cost nobody has priced.

### 4. The taxonomy has no id for a skip, and 11 of 384 were skips

**A recorded deviation from the frozen protocol.** The pre-registered category
list was "the ten form factors, plus `uncertain`, plus `not_a_bin`", and it turned
out to lack a bucket for *"clearly a waste container, and no taxonomy id fits"* —
front-load dumpsters, roll-off skips, builder's containers. There were **11**.

They are counted under `no_matching_form_factor` and broken out rather than
folded into `uncertain`, because *"I cannot tell what this is"* and *"I can tell,
and the taxonomy has no id for it"* are different facts, and only the second one
is a finding about the taxonomy. Folding them together would have hidden it.

At ~3 % this is not urgent, and **adding a form-factor id is a taxonomy change
and the maintainer's decision** — recorded here, not proposed. Worth noting that
a skip is also not a *sorting* target, so it may belong with `street_basket` in
the category of "things the product recognises in order to say something short
and true about".

## One thing the survey confirmed by accident

Cell 274 is a **yellow La Poste postbox**, boxed as a waste container.
`validator.yaml` names `postbox` first in its hard-negative list. The corpus
contains the confusion the negative corpus was built to defend against, which is
mild evidence that the hard-negative choice was the right one — and a reminder
that these boxes are Open Images' annotations, not ours, and that this survey
says nothing about whether any given box is *correct*.

## What this changes

- **docs/12 P1's open question is answered.** A second adjudication pass over
  Open Images is worth it **for `street_basket` and for reinforcing the wheelies,
  and for nothing else.** It cannot produce `underground`, `textile_bank` or
  `wall_unit` at all.
- **The identifier's coverage gap is not closable from data on hand.** Six ids
  have no data; this corpus supplies a seventh class's worth and leaves five
  empty.
- **A re-harvest at a larger frame size is now a costed-in-principle option**
  for recovering the 29 % of boxes that fall under `min_box_px`.
- **Nothing in the taxonomy changed**, and nothing in any manifest changed.
