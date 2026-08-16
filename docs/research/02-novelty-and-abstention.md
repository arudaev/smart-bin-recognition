# 02 – Novelty and abstention

*2026-08-16. Feeds docs/04 § 7, docs/07's kill criteria, and
`ml/configs/identifier.yaml`.*

---

## 1. `0.55` is a baseline, not a principle

`identifier.yaml` says:

> `unknown` … is a max-softmax below `unknown_threshold`, not a box score below a
> confidence floor.

The first half of that is a real architectural improvement over a detector
confidence floor and should stay. The word **"principled"** should not, because
max-softmax probability (MSP) is explicitly framed in the literature as a
*baseline*.

From the [2025 task-oriented OOD survey](https://arxiv.org/html/2409.11884):

- MSP "is the most widely used baseline … it still serves as a general-purpose
  baseline that is nontrivial to surpass";
- but softmax confidence "can produce arbitrarily high values for OOD inputs,
  making it suboptimal";
- [energy scores](https://dl.acm.org/doi/10.5555/3495724.3497526) are
  "theoretically aligned with the probability density of the inputs and are less
  susceptible to the overconfidence issue".

Both halves matter. MSP is not embarrassing — it is hard to beat and it is one
line of code. But calling a specific threshold on it "principled" without a
calibration set is the part that does not hold, and the threshold value itself
was never derived from data.

## 2. What actually decides the threshold

Not top-1 accuracy. **Novelty precision** — of the frames the system flags as
novel, how many were genuinely a bin type we had not seen. docs/04 § 7 already
targets ≥ 0.70 and docs/07 kills the design below 0.5, so the metric is chosen;
what is missing is the set it is measured on.

The calibration set has to contain all five things the flag must separate, or
the threshold is tuned against a fiction:

| Bucket | Why it must be present |
|---|---|
| familiar form factor, correct | the true negatives of the flag |
| familiar but hard — blur, dusk, rain, occlusion, tiny crop | **the dominant confound**; a low-confidence familiar bin is not novelty |
| genuinely unseen form factor | the true positives |
| validator false positive (planter, postbox) | flags here are wasted adjudication |
| real second-city data | the case the product exists for |

The fourth row is the one usually forgotten and the one our design most needs:
docs/01 § 3 claims a high-precision validator makes "B is wrong" trustworthy. If
A's false positives reach B, they arrive as low-confidence crops and are
indistinguishable from novelty by any score.

## 3. Selective prediction is the honest frame for `unknown`

[Conformal prediction](https://arxiv.org/pdf/2107.07511) gives distribution-free
coverage guarantees under exchangeability, and is "frequently paired with
selective prediction or abstention to trade coverage for risk". 2025 work such as
[Selective Conformal Risk Control](https://arxiv.org/abs/2512.12844) addresses
the practical objection — that conformal sets get uselessly large — by selecting
confident samples first and applying risk control on that subset.

This is a good conceptual fit: `unknown` is already a designed product state, so
we are *already* building a selective classifier, just without the vocabulary or
the guarantee.

**But it is not a v1 dependency.** Exchangeability is precisely what
cross-city deployment breaks, which is the one thing conformal guarantees assume
and our product cannot promise. The honest position: adopt the *framing* (state a
target abstention rate and a target risk-when-answering, report both), and treat
formal conformal guarantees as a v2 question once there is a second city to
calibrate on.

## 4. What this changes for us

| Change | Where |
|---|---|
| Drop "principled" for `0.55`; mark the value **provisional**, and say it is an MSP baseline pending calibration | `identifier.yaml`, docs/04 § 7 |
| Define novelty precision's measurement procedure and its five-bucket frozen set | docs/12 (probe **P2**) |
| Score MSP vs energy vs max-logit vs kNN-on-embeddings; pick the operating point, not the score, first | docs/12 |
| Report abstention rate and accuracy-when-answering as a pair, never top-1 alone | docs/11 |
| Record conformal prediction as a v2 candidate with the exchangeability caveat stated | this note |

## Sources

- [OOD detection: a task-oriented survey (ACM CSUR 2025)](https://arxiv.org/html/2409.11884) · [reading list](https://github.com/shuolucs/Awesome-Out-Of-Distribution-Detection)
- [Energy-based out-of-distribution detection (NeurIPS 2020)](https://dl.acm.org/doi/10.5555/3495724.3497526)
- [A gentle introduction to conformal prediction](https://arxiv.org/pdf/2107.07511)
- [Selective Conformal Risk Control](https://arxiv.org/abs/2512.12844)
- [Know when to abstain: optimal selective classification](https://arxiv.org/pdf/2505.15008)
