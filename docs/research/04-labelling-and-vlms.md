# 04 – Labelling and VLMs

*2026-08-16. Feeds docs/04 § 3 (step 4) and docs/05 § 5 (the paid path).*

---

## 1. The paid path can become free

docs/05 § 5 calls the VLM labelling step "the paid path", capped at ~€6/month.
Two properties make it safe today: it runs offline in batch, and it is capped by
a hard integer.

It can also simply stop costing money. The open-weight VLM field as of 2026:

| Model | Licence | Note |
|---|---|---|
| **InternVL3** | MIT | the best *permissively* licensed option — matters for a project that wants no lock-in |
| **Qwen3-VL** | Qwen | leads open-weight general vision benchmarks alongside Llama 4 |
| Molmo, Pixtral | Apache-2.0 | strong permissive alternatives |
| Phi-4 multimodal | MIT | the efficient small option |

Quality on MMMU / OCRBench / ChartQA / DocVQA is reported as competitive with
frontier hosted models at meaningfully lower deployment cost. For our task —
"name the form factor in this crop from a closed vocabulary and emit strict
JSON" — we are nowhere near the frontier of what these models can do. The task is
constrained classification with a schema, not open reasoning.

**And we already have free GPU**: 30 h/week of Kaggle, the same dispatch path as
everything else (`ml/scripts/dispatch.py`). A batch labelling kernel is the same
shape as `build_negatives`.

## 2. If a hosted model is still wanted

Batch APIs give a flat **50% discount** on input and output tokens across models,
and stack with prompt caching. That is the right mode for us regardless of
provider: docs/05 § 5's two safety properties (offline, capped) are exactly the
conditions a batch API is designed for. Nothing about the current design needs to
change to take the discount.

The hosted case rests on one real advantage: **schema reliability**. Constrained
decoding and structured-output modes on hosted models are mature; an open-weight
model may need retries or a repair pass to satisfy
`ml/src/sbr/escalation/schema.py`. That is measurable, and it is what probe P6
measures.

## 3. How accurate will auto-labelling be?

Honestly: **unknown, and no published number transfers.** But the question
decomposes into four tasks that are usually run together and should not be:

| Sub-task | Difficulty | What decides it |
|---|---|---|
| **Boxes** — is there a bin, where | moderate | bins are well represented in web-scale corpora; failure mode is planters, postboxes, utility cabinets — our hard-negative list exactly |
| **Per-location categorisation** | *not a model at all* | geohash → jurisdiction → pack is a deterministic lookup. The risk is a wrong pack entry, a human-verification problem |
| **Form factor** | hardest, possibly ill-posed | `wheelie_small` vs `wheelie_large` is a *size* distinction asked of a resized crop — see probe P1 |
| **Colour** | a measurement | note 06, probe P3 |

Two consequences worth stating in the design docs:

**Accuracy is the wrong headline metric, because no auto-label ever reaches a
user.** It is a proposal to a human reviewer. The metric that matters is *time
saved per human decision*. A 70%-correct proposal that is confirmable with one
keystroke is a large win; the reviewer was going to look anyway.

**Accuracy matters enormously the moment auto-*accept* is on the table.** At 85%
accuracy, auto-accepting puts 15% wrong labels into training. Label noise hurts
small datasets far more than large ones, and with ~1 480 positives we cannot
absorb it. This is the concrete argument behind the guardrail in AGENTS.md.

## 4. The circularity in the agreement gate

docs/04 § 3 accepts a machine label when GroundingDINO and SAM agree *and* the
VLM's form factor matches model B's guess.

That gate systematically **auto-accepts what B already knows and routes
disagreements to a human**. Which is correct for safety — it is the conservative
direction — but it means auto-labelling saves the least effort exactly where the
value is highest, and the efficiency claim in docs/04 § 3 should not stand
unqualified.

It also interacts badly with the acquisition function: the collection queue is
prioritised by *A-confident + B-unknown* (docs/04 § 2), which is precisely the
population the agreement gate cannot auto-accept. At pilot volume the honest
expectation is that **most of the queue reaches a human regardless**, and the
elaborate pipeline earns its keep only once the queue is large.

## 5. What this changes for us

| Change | Where |
|---|---|
| Open-weight VLM on the free Kaggle GPU becomes the **documented default**; hosted API retained behind the same interface as fallback | docs/04 § 3, docs/05 § 5 |
| The €0 constraint becomes literally true rather than "capped at ~€6/month" — state both, and which is in force | docs/05 § 5, § 2 |
| If hosted is used, use the batch API's 50% discount — the design already satisfies its preconditions | docs/05 § 5 |
| Split the four sub-tasks in the doc instead of one "auto-labelling accuracy" | docs/04 § 3 |
| Mark every auto-labelling accuracy claim a **prior** until P1/P6 report | docs/04 § 3 |
| Name the agreement-gate circularity and the small-dataset noise argument | docs/04 § 3, § 4 |
| Add probe **P6**: schema-valid rate + form-factor agreement for InternVL3 / Qwen3-VL over ~200 crops | docs/12 |

## Sources

- [Best open-source VLMs 2026 (BentoML)](https://www.bentoml.com/blog/multimodal-ai-a-guide-to-open-source-vision-language-models)
- [Best open-weight VLMs 2026 (Presenc)](https://presenc.ai/research/best-open-weight-vision-language-models-2026)
- [Top open-source VLMs (Labellerr)](https://www.labellerr.com/blog/top-open-source-vision-language-models/)
- [Batch API pricing and the 50% discount](https://tokenmix.ai/blog/openai-batch-api-pricing)
