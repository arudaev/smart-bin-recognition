# 00 – Hardening register

*2026-08-16. The audit trail for the contradiction pass. Closed out and frozen —
this file records what was wrong and how it was resolved, and is not maintained
as a living document.*

The design was not rewritten. Nineteen items below are places where documents
that were each true when written had come to disagree with each other, or where a
number was stated without the procedure that would produce it. Every one was
verified against source before being listed.

---

## Blocking — these made phase 2 undecidable

### C1 · The ship gate was unreachable

`check_gates` requires `accuracy_drop` for `may_ship`; both training kernels wrote
`map50_int8=None` / `top1_int8=None` deferring to `gate.py`; `gate.py` measures
only latency. **No artefact could ever pass its own gate.** Dispatching the
validator would have burnt a GPU hour to produce something permanently
*unmeasured*.

`check_gates` itself was correct and tested. What nothing tested was whether any
*producer* fills the fields it needs.

**Resolved** `aaf0883` — `evaluate_int8` scores the quantised graph in the kernel,
which is the only place holding both the artefact and the split the fp32 number
came from. `gate.py` keeps latency, the one thing a training kernel genuinely
cannot measure. `test_kernels.py::test_the_kernel_measures_int8_accuracy` pins it.

### C2 · Held-out-city recall had two targets

docs/00 § 6 said ≥ 0.80; docs/04 § 7 and `validator.yaml` said ≥ 0.97. The PRD
number predates the two-model split, when one detector did both jobs.

**Resolved** `6324376` — 0.97 everywhere, and the row now says it is **not
measurable yet**.

### C3 · `export.targets` was read by nothing

`Gates.from_config` reads only `export.gates`, so docs/04 § 7's accuracy targets
were decorative and a fast but useless model produced a sidecar indistinguishable
from a good one.

**Resolved** `aaf0883` — `Targets` / `check_targets`, reported beside the gates
and never blocking. Three categories: met, missed, and **unmeasurable** — the
last so the held-out-city targets show as missing evidence rather than being
silently skipped.

### C4 · The negative ratio was stated three ways

"Roughly 30:1" (docs/04 § 1), "~15.7:1" (§ 5), actual **11.8:1**. The 15.7
divided negatives by the Open Images bins alone and dropped the legacy 370.

**Resolved** `ef52f95` — defined once as background frames : frames with ≥ 1 bin,
with the designed and realised figures side by side. The ratio fell because the
harvest *added positives*, and the asymmetry rather than the specific figure was
always the point.

---

## Structural — the docs disagreed about what the product is

### C5 · The PRD contradicted the architecture, and itself

§ 3.6 "frames are processed locally", § 4 "on-device detection; no image ever
uploaded", § 3.4 "the core loop must not care" about signal — against docs/01 § 1
(server-side) and the PRD's **own § 7** ("scanning may require a connection").

**Resolved** `6324376` — a dated correction note, and § 3.4 / § 3.6 / § 4
rewritten. Principle 6 becomes "nothing is *kept* unless the user chooses":
retention, not transmission, is the explicit act.

### C6 · Free HF CPU is gone, but only docs/05 § 3 knew

docs/01 § 2's host table still said "Free, persistent process"; docs/05 § 7
offered an upgrade from a tier that does not exist; § 8 costed "a cold Space".

**Resolved** `6324376` — propagated, and the hole closed with a host chosen for a
reason (see [research/05](05-serving-economics.md)).

### C7 · "Multi-bin is free" was false in the cost model

docs/04 § 1 said N crops are free; docs/05 § 3 budgeted 65 ms = validator + *one*
crop. Six bins — which the PRD calls a normal input — is 190 ms, dropping the
ceiling from ~10 to ~3.5.

**Resolved** `6324376` — "free" split into **free in accuracy, linear in cost**.
docs/05 § 3 carries a curve and states 3–10 as a range. [Probe P4](../12-validation-protocol.md#p4--multi-bin-cost-curve)
measures the real one, without a trained model.

### C8 · Auto-accept contradicted the guardrail

AGENTS.md: "never let user input reach training data without human label review."
docs/04 § 3–4 permitted high-agreement auto-accept; `identifier.yaml` lists
`machine_agreed` as trainable.

**Resolved** `ef52f95` — the rule turns on **image provenance, not label
confidence**. Public corpus: may auto-accept. User-contributed frame: never. New
form factor: never, because there is no prior for "agreement" to mean anything.

### C9 · 3 fps or 4 fps

docs/01 § 4 caps at 4; docs/05 § 3's capacity arithmetic used 3, and the "10
concurrent scanners" figure depends on which.

**Resolved** `6324376` — 4 is the cap and the guarantee, ~3 is the achieved
average once the motion gate works. Both stated, once.

---

## Vagueness with consequences

### C10 · `0.55` was called "principled"

A guess, on a score the literature explicitly frames as a *baseline* that can be
arbitrarily confident on exactly the out-of-distribution inputs it exists to
catch.

**Resolved** `ef52f95` — marked **provisional** in `identifier.yaml` with the
calibration procedure named. [Probe P2](../12-validation-protocol.md#p2--novelty-scoring-bake-off)
replaces it with an operating point.

### C11 · Novelty precision had a target, a kill criterion, and no procedure

**Resolved** — [probe P2](../12-validation-protocol.md#p2--novelty-scoring-bake-off)
defines the frozen five-bucket set and the counting rule. Four of the five
buckets can be built today; the second-city bucket cannot, and that is recorded
rather than substituted.

### C12 · Consent was "per-session and visible" and nothing else

No retention period, no deletion path, no contributor-visible outcome. docs/03
§ 4 additionally assumed face/plate auto-rejection — an unscoped ML component
sitting inside a privacy guarantee.

**Resolved** `ef52f95` — a specified lifecycle in docs/03 § 4: per-**frame**
consent asked at the moment, a local receipt that gives deletion a mechanism
without an identity, a stated retention window, and the face/plate guarantee
restated as human moderation until something is built and measured. EU AI Act
Art. 50 has been in force since 2026-08-02, so this stopped being future work.

### C13 · Two HF repos were documented as existing

`smart-bin-identify` and `smart-bin-raw`. Neither does; `identifier.yaml` points
at the first.

**Resolved** `ef52f95` — an "Exists?" column, plus a note that the dataset and
model repos deliberately share an id because the Hub namespaces them separately.

### C14 · "Self-improvement loop" / "flywheel"

Overstated the automation. Nothing promotes a model automatically, and nothing
should.

**Resolved** `ef52f95` — **human-reviewed improvement loop**, with a paragraph on
what is and is not automated. docs/07 phase 5 renamed.

### C18 · Coverage growth and concurrency growth were conflated

"Adding a city is a data change" is true of *meaning* and says nothing about
*recognition* or *load*. Stated as one property, it invites the conclusion that
the whole system scales for free.

**Resolved** `ef52f95` — docs/02 § 1 names three axes with three rates: meaning
(free), recognition (**unmeasured**, `holdout_region` is empty), concurrency (a
hard vCPU ceiling that does not move with coverage). Fifty towns is fine; one
town going viral is not.

### C19 · Auto-labelling accuracy was claimed but never measured

And the efficiency argument is circular: the agreement gate accepts what model B
already knows and routes novel cases to a human — saving least effort exactly
where value is highest, over precisely the population the acquisition function
prioritises.

**Resolved** `ef52f95` — docs/04 § 3 splits the four sub-tasks, marks every
accuracy claim a prior pending [P1](../12-validation-protocol.md#p1--form-factor-separability)
and [P6](../12-validation-protocol.md#p6--open-weight-vlm-for-batch-labelling),
states that accuracy is the wrong headline metric while auto-*accept* makes it
critical, and names the circularity.

---

## Stale references

| # | Issue | Resolved |
|---|---|---|
| C15 | `docs/README.md` and AGENTS.md's map both stopped at 08 | `ef52f95` — through 12, plus research |
| C16 | docs/04 § 8 listed `autolabel/`, `kaggle/autolabel_batch/`, `scripts/benchmark.py` — none of which exist — and omitted eight things that do | `ef52f95` — split into "exists today" and "planned, deliberately not built yet" |
| C17 | docs/00 § 6 linked to "04 § 5 Evaluation protocol"; § 5 is Datasets and evaluation is § 7 | `6324376` |

---

## What this pass deliberately did not do

- **Rewrite the design.** The three decisions in AGENTS.md stand unchanged.
- **Build `autolabel/`.** Blocked on P1, P3 and P6 by choice — building it around
  unmeasured assumptions is the mistake the sequencing exists to avoid.
- **Add the regression gate.** Named in docs/04 § 7 and
  [research/03](03-data-engine-patterns.md); it belongs with the second training
  run, since v1 has nothing to regress against.
- **Answer the generalisation question.** It needs a second-city capture. Every
  place that depends on it now says so instead of implying an answer.
