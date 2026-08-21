# P11 – What int8 costs the identifier

*Run 2026-08-21. `ml/kaggle/train_identifier/`, kernel
`hlexnc/sbr-train-identifier`, Kaggle T4. Raw data:
[`data/P11-identifier-int8.json`](data/P11-identifier-int8.json). Protocol
pre-registered in [docs/12 P11](../../12-validation-protocol.md) at `5ecb718`,
**before model B was trained**.*

**Question.** P9 and P10 established that post-training int8 destroys the
*validator* and that the detection head is why. A `yolo11s-cls` has no DFL
detection head, so the diagnosis cannot transfer. What does int8 cost the
identifier?

---

## The verdict: the first row fires, on the first variant

| | `val` (n=56) | `test` (n=47) |
|---|---:|---:|
| PyTorch fp32 top-1 | 0.9821 | 1.0000 |
| int8 top-1 | 0.9821 | 1.0000 |
| **drop** | **0.0000** | **0.0000** |
| budget | 0.02 | 0.02 |

**The shipped defaults were eligible immediately** — U8S8, per-channel, minmax,
stretched calibration, the exact configuration that cost the validator 0.727
mAP. So the pre-registered sweep **never ran**, and no other configuration was
tried. That is the rule working: a sweep is what you do when the reference
misses.

**The accuracy gate passes. The artefact still may not ship**, because latency
is unmeasured — `may_ship: false` in the sidecar, with `unmeasured` naming the
bench. That is the correct verdict and not a failure.

## This is consistent with P9's diagnosis, and it is not proof of it

The natural reading is *"there is no detection head, so int8 is harmless"*, and
it is probably right. It is worth being exact about how much this run actually
establishes, because the answer is: less than it looks.

**The task is saturated.** fp32 scores 0.9821 on `val` and 1.0000 on `test`.
When the reference is already at ceiling, a measurement cannot show int8
*failing to hurt* very precisely — there is almost no headroom for it to lose.

**And the resolution is about the size of the gate.** On 56 `val` crops, one
extra misclassification is **0.018** against a budget of **0.020**. So this
measurement can distinguish *"int8 and fp32 differ by at most one crop"* from
*"they differ by two or more"*, and not much finer than that. The gate passed
honestly; it did not pass by a margin the data can resolve.

## What "top-1 = 1.0000" is actually measured on

**47 crops.** That number should never be quoted without this table beside it:

| class | crops in `test` | capture clusters in `test` |
|---|---:|---:|
| `wheelie_small` | 25 | 9 |
| `wheelie_large` | 19 | 8 |
| **`igloo`** | **3** | **2** |

- **47 correct out of 47 is not certainty.** By the rule of three, the 95 %
  lower bound on accuracy is **0.936**, not 1.000.
- **`igloo`'s contribution is three crops from two scenes.** AGENTS.md and
  docs/12 both said in advance that a 70/15/15 group-aware split over 17 igloo
  clusters would leave 2–3 in test and that its per-class metrics would be
  noisy. Measured, it is 2 clusters. **A perfect igloo score here says
  essentially nothing** and must never be quoted clean.
- Every crop is **one city, one week**. The split is group-aware by capture
  cluster, so no physical bin appears on both sides — but there is still no
  geographic holdout, and `min_formfactor_acc_heldout_city` reports
  **unmeasurable**, not met.

**The honest summary is "B separates three visually distinct form factors on
in-distribution data, and the test split is too small to say more."** That
agrees with [P1](P1-form-factor-separability.md), which got 0.9834 out-of-fold
from a frozen DINOv2 probe over all 403 crops — a much larger evaluation, and
the better estimate of the two.

## The served class order is alphabetical, and the sidecar carries it

```
config  data.classes : ["wheelie_small", "wheelie_large", "igloo"]
sidecar classes      : ["igloo", "wheelie_large", "wheelie_small"]
```

Ultralytics builds a classification dataset from directory names, so the head is
indexed **alphabetically over the classes that actually had crops** — not in
taxonomy order and not in config order. The kernel reads it back from
`model.names` and writes it into the sidecar, and the service reads the sidecar
rather than guessing. The form-factor **ids** stay canonical and permanent; only
their position in this particular head is incidental.

## Two numbers here that are not gates

- **top-5 = 1.0 is arithmetic**, not accuracy. There are three classes.
- **unknown rate = 0.0, accuracy-when-answering = 1.0.** The threshold is
  `0.55`, which is an uncalibrated guess, and max-softmax is a baseline rather
  than a principled score — the literature is explicit that it can be
  arbitrarily confident on out-of-distribution input, which is exactly the input
  the threshold exists to catch. **An unknown rate of zero over 47
  in-distribution crops is a property of that guess as much as of the model.**
  docs/12 P2 replaces it with an operating point chosen at a stated novelty
  precision.

## The coverage gap, stated because it does not go away

B is trained on three of ten form factors.

| | |
|---|---|
| trained | `wheelie_small`, `wheelie_large`, `igloo` |
| dropped, n=1 | `street_basket` — one crop in one capture cluster, so it cannot be split across train/val/test and can be neither trained nor evaluated |
| no data at all | `underground`, `textile_bank`, `sack`, `crate`, `wall_unit`, `container_bank` |

Those six **keep their ids**. Everything B has never seen resolves to `unknown`,
which is a designed state with real UI, and the honest answer.
[research/11](../11-open-images-form-factors.md) established that Open Images
cannot close the gap — zero `underground`, zero `textile_bank`, zero `wall_unit`
in a 384-box sample — so closing it needs a capture round.

**`sack` and `textile_bank` both carry Deggendorf pack rules**, so a pilot there
will meet bins B cannot name. That is a product consequence, recorded here.

## What this changes

- **docs/12 P11 — closed.** First row, on the first variant, no sweep.
- **docs/11** gets B's numbers, with the 47-crop caveat attached wherever they
  are quoted.
- **`identifier.yaml`** keeps its shipped export defaults; nothing needed pinning
  because nothing was changed.
- **The identifier's remaining blocker is latency**, and only that.
