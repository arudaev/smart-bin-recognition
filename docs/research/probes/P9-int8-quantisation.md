# P9 – Why int8 destroys the validator

*Run 2026-08-20 and 2026-08-21. `ml/kaggle/probe_quantisation/`, kernel
`hlexnc/sbr-probe-quantisation`. Raw data:
[`data/P9-int8-quantisation.json`](data/P9-int8-quantisation.json) (authoritative)
and [`data/P9-run1-exploratory.json`](data/P9-run1-exploratory.json).*

**Question.** Validator v1 scores **mAP@0.5 = 0.7524 in fp32 and 0.025 in int8** on
test, so `may_ship` is false and nothing can be deployed. Which part of the
quantisation does that, and is there a configuration inside the 0.02 budget?

**Decision rule, quoted from [docs/12](../../12-validation-protocol.md) before the
result:**

| Outcome | Action |
|---|---|
| a variant's total served drop on `test` is within **0.02** | adopt it; pin the export settings in `validator.yaml` |
| the best is 0.02–0.10 | the gate is missed but the model is real. **Do not loosen the gate** - report it, and decide the trade explicitly against the latency the alternative costs |
| nothing recovers it | validator v1's weights cannot yield a shippable post-training int8 export; P5 reopens |

**Hardware.** Kaggle CPU kernel, onnxruntime pinned to 2 threads. Run 1 landed on
an AMD EPYC 7B12, run 2 on an Intel Xeon @ 2.20 GHz. **`representative: false`** —
this is a free x86 proxy, not the service container. Latency may be compared
*within* a run and **never across the two**, because the silicon changed.

**Toolchain.** ultralytics pinned to **8.4.121**, the version recorded inside
`best.pt`; onnx 1.22.0, onnxruntime 1.29.0, torch 2.10.0+cpu, numpy 2.0.2.

---

## The verdict: the middle row fires

**Nothing is eligible.** The best configuration leaves the detection head in fp32
and lands **0.0252 below** the reference, against a budget of 0.02. It misses by
**0.0052**, and where that remaining 0.0052 lives is **not established** — the
head-fp32 graph is still quantised everywhere else.

Per the rule: the gate is missed, the model is real, and **the gate does not
move**. What the trade costs is set out at the bottom; taking it is not this
document's decision.

## What the loss actually is

The three drops decompose cleanly, on `val`:

| | |
|---|---|
| PyTorch fp32 (the reference eligibility reads) | **0.7734** |
| fp32 ONNX control | 0.7748 |
| **export drop** | **−0.0014** — none. The ONNX graph is marginally *better*, well inside noise |
| best int8 (`15-head-fp32`) | 0.7481 |
| **quantisation drop** | 0.0267 |
| **total served drop** | **0.0252** |

**The export is innocent.** Every point lost is lost to quantisation. Almost all
of it is recovered by protecting the head; the remaining 0.0252 is not
attributed to anywhere.

## The table

All rows scored on `val`. `test` was never spent on a candidate.

| variant | val mAP@0.5 | drop vs PyTorch fp32 | p50 (Xeon proxy) |
|---|---|---|---|
| `01-fp32-onnx-control` | 0.7748 | −0.0014 | 38.7 ms |
| **`15-head-fp32`** | **0.7481** | **+0.0252** | **36.6 ms** |
| `30-combined` (head fp32 + letterboxed) | 0.7350 | +0.0384 | 36.9 ms |
| `21-letterboxed` | 0.0847 | +0.6887 | 30.3 ms |
| `11-s8s8` | 0.0250 | +0.7484 | 76.3 ms |
| `12-u8s8-reduce-range` | 0.0250 | +0.7484 | 30.3 ms |
| `14-per-tensor` | 0.0250 | +0.7484 | 30.4 ms |
| `20-positive-enriched` | 0.0250 | +0.7484 | 30.6 ms |
| `13-u8u8` | 0.0240 | +0.7494 | 40.5 ms |
| `10-reference-u8s8` | 0.0150 | +0.7584 | 30.9 ms |
| `16-preprocessed` | 0.0150 | +0.7584 | 30.4 ms |
| `02-fp16-informational` | **error** | — | — |

## Four findings, in order of how much they change

**1. Quantising the detection head is what causes the collapse.** Excluding
`/model.23/` moves the model from noise to 0.7481 — a **50-fold** recovery. The
boundary is verified rather than assumed: `qdq_nodes_in_head: 0`,
`qdq_nodes_outside_head: 619`.

**What this does *not* establish is that nothing outside the head matters.** The
head-fp32 graph still has 619 QDQ nodes in it and still loses **0.0252**, and
that residual is **unattributed**: it may sit in the backbone or the neck, and
this probe did not test that. "The head, and only the head" would be the claim
that the remaining 0.0052 cannot be recovered elsewhere, and no row here supports
it. The collapse is explained; the miss is not.

**2. The three remedies onnxruntime names for this failure mode all fail.**
Its guidance names S8S8 as the normal CPU choice and identifies large U8S8 loss
on x86 as activation saturation, with `reduce_range` and U8U8 as the remedies.
That was the best-supported hypothesis going in. **All three do nothing here** —
each stays at collapse — and S8S8 is additionally **2.5× slower** (76.3 ms
against 30.3 ms), which would have missed the latency budget on its own.
Per-channel versus per-tensor makes no difference either. **This is not the x86
saturation case it resembled.** Narrower than "every remedy onnxruntime names":
these four plus `quant_pre_process` are what was tested, and the guidance also
describes options — QAT among them — that this probe did not touch.

**3. The combined variant made it worse — which is why it was pre-registered.**
docs/12 promised a combined run when the two axes disagree, and they did:
`15-head-fp32` on format, `21-letterboxed` on calibration. Combining them scores
**0.7350**, worse than head-fp32 alone by 0.0131. Letterboxed calibration helps a
collapsed graph (0.025 → 0.0847) and *hurts* a working one. Without this run the
probe would have left an untested "maybe the two together" hanging over the
verdict.

**4. The calibration hypotheses were both wrong.** Neither the sampling defect nor
the geometry mismatch is what breaks the model:

- `20-positive-enriched` — 100 positive frames instead of 51 — scores **0.0250**.
  No effect.
- `21-letterboxed` reaches 0.0847, a real 3.4× on a collapsed graph, and is still
  two orders of magnitude short of usable.
- The `stratified` sample from `train` is itself **92 % background** (184 of 200),
  because `train` is. What it fixed was *pool* coverage — 12 Open Images frames,
  against **zero** in the historical lexicographic sample.

The 74.5 %-background finding was a real defect in the exporter and worth fixing.
It was not the cause of this failure.

## Things that went wrong, recorded rather than tidied away

**The published figure did not reproduce; the collapse did.** The historical
baseline — v1's own settings and v1's own calibration list — scores **0.0150** on
test in both runs, against the published **0.025**. The re-quantised graph is also
**not byte-identical** to the artefact on the Hub (`a8c0b541…`). Dependencies in
this repo are lower-bounded rather than pinned and the Hub holds no fp32 ONNX, so
the two graphs genuinely are not the same graph. Both figures are collapse and the
conclusion is unaffected, but **0.025 and 0.0150 are 40 % apart and that is part
of the record.** The first version of the check accepted anything within 0.05 of
0.025 — which accepts every collapsed number there is, including negative ones —
and then printed "reproduces". It now asserts the collapse and reports the delta.

**The QDQ tensor diagnostic was read backwards, and a conclusion was drawn from
it.** onnxruntime's `qdq_err` is **SQNR in decibels**, `20·log10(‖x‖/‖x−y‖)`, so
higher means better preserved. The first implementation sorted descending and
reported the result as "the worst tensors", naming `/model.23/Div_1`,
`dfl/Reshape` and `dfl/Transpose` at ~390 dB as the suspects. **Those were the
eight best-preserved tensors in the graph.** The head *is* the culprit — but that
is established by variant `15-head-fp32`, an independent experiment, and the
agreement between a broken diagnostic and a correct experiment is a coincidence,
not corroboration. Fixed, and pinned by a test asserting the direction against
onnxruntime's own function.

**The raw record over-declares its own test evaluations.** In
`P9-int8-quantisation.json`, `partitioning.test_evaluations` lists three entries —
the baseline, a locked winner and an fp32 control. **Only the first ran.**
`winner` in the same file is `null`, and no `90-` or `91-` row exists, because
nothing was eligible. The list was a hard-coded plan rather than a reading of the
rows, so it described what the kernel *would* do rather than what it did.

The JSON is left exactly as the kernel wrote it — it is the raw record, and
editing it after the fact would cost the one property that makes it worth
keeping. The defect is fixed in the kernel (`test_evaluations` is now derived
from the rows and labelled *what ran, not what was planned*) and noted here, so
anyone reading that file sees the correction beside it. **The row data itself is
unaffected**; only that summary field was wrong.

**The collapsed rows are noise and must not be read as a ranking.** Across the two
runs the collapsed variants swap places freely — `10-reference` was 0.0250 then
0.0150; `11-s8s8` was 0.0150 then 0.0250; `14-per-tensor` likewise. **Only the
rows that mean something replicate**: `15-head-fp32` 0.7471 → 0.7481,
`21-letterboxed` 0.0847 → 0.0847, `13-u8u8` 0.0239 → 0.0240. Anything below ~0.1
here is one number, not several.

**fp16 does not load at all.** `Type (tensor(float)) of output arg
(/model.11/Resize_output_0) … does not match expected type (tensor(float16))` —
a conversion defect, before any question of whether the CPU provider would run it.
Recorded as an `error` rather than as a missing number, which is what the row
format exists for. It was never a shipping option: the CPU execution provider does
not broadly support fp16.

## The trade, since the rule says to state it

Leaving the head in fp32 is **cheap in every way except the gate**:

| | int8 everywhere | head in fp32 | gate |
|---|---|---|---|
| val mAP@0.5 | 0.0150 | **0.7481** | — |
| drop vs PyTorch fp32 | 0.7584 | **0.0252** | ≤ 0.02 (**missed by 0.0052**) |
| p50, Kaggle 2-thread x86 proxy | 30.9 ms | **36.6 ms** | 50 ms, but stated on *service* CPU |
| p95, same proxy | — | 37.3 ms | — |
| artefact size | 3.19 MB | 4.37 MB | **not gated** |

Leaving the head in fp32 costs **+5.7 ms on the Kaggle proxy** and **+1.2 MB**.

Neither of those is a budget clearance and neither may be written up as one. The
latency budget is stated **on service CPU**, and this measurement carries
`representative: false` — 36.6 ms on a Kaggle Xeon is *encouraging* against a
50 ms service budget and **does not close the latency gate**, which only
`ml/scripts/gate.py` against a real bench can do. Size is not gated at all, so
"+1.2 MB, within budget" names a budget that does not exist.

**There is no `test` measurement of this configuration, deliberately.** Nothing was
eligible, so nothing was confirmed, so the test split is unspent. Quoting 0.0252 as
a ship-gate number would be quoting a `val` number at a `test` gate. If the trade
is taken, spending the test split on it is a separate, deliberate act.

## What this changes for us

- **docs/04 § 6 and `validator.yaml`**: post-training int8 over the whole graph is
  not viable for this architecture. Any future export of a YOLO11 detector here
  starts from `exclude_head=True` — which is necessary and, on this evidence, not
  sufficient.
- **docs/07 phase 2**: the int8 blocker is *diagnosed* and *not cleared*. v1 still
  cannot ship, and the reason is now specific rather than mysterious.
- **docs/12**: P9 is answered. Two things it does **not** answer: where the
  residual 0.0252 lives, given that the head-fp32 graph is still quantised
  everywhere else; and whether a model *trained* to be quantised would clear the
  gate — that is quantisation-aware
  training, and it is a new probe with its own pre-registration, not a continuation
  of this one. Inventing further variants after seeing these results is exactly
  what the protocol forbids.
- **The gate stays at 0.02.** It has now fired twice on the same artefact and been
  right both times.
