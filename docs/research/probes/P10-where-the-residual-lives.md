# P10 – Where the residual 0.0252 lives

*Run 2026-08-21. `ml/kaggle/probe_residual/`, kernel `hlexnc/sbr-probe-residual`.
Raw data: [`data/P10-residual.json`](data/P10-residual.json) (authoritative).
Pre-registered at `a2eebac`, **before the kernel was written**.*

**Question.** [P9](P9-int8-quantisation.md) established that quantising the
detection head is what collapses the validator: excluding `/model.23/` recovers
it from 0.015 to 0.7481 on `val`. It did **not** establish that nothing outside
the head matters — that graph still carries **619 QDQ nodes** and still loses
**0.0252** against a 0.02 budget. Where does the residual live, and can it be
recovered for free?

**Hardware.** Kaggle CPU kernel, onnxruntime pinned to 2 threads, **AMD EPYC
7B12**. `representative: false` — a free x86 proxy, not the service container.
**Latency here may not be compared with P9's**, which ran its final block on an
Intel Xeon @ 2.20 GHz. See the note at the bottom; the gap is larger than
anything this probe measured.

**Toolchain.** ultralytics 8.4.121, onnx 1.22.0, onnxruntime 1.29.0,
torch 2.10.0+cpu, numpy 2.0.2.

**Partitioning.** Calibrated from `train` (200 frames, 16 positive / 184
background, sha `70227d89…`), every variant scored on `val`. **`test` was never
touched** — `test_evaluations: []` in the raw report, because nothing became
eligible and an unspent split is the point of holding one back.

---

## The verdict: the middle row fires, and so does the fourth

Two of the four pre-registered outcomes fired, which is worth saying plainly
because only one of them is about the number.

**The middle row.** The best configuration lands **0.0254 below** the PyTorch
fp32 reference against a budget of 0.02. It misses by **0.0054**. Per the rule:
the gate is missed, the model is real, **the gate does not move**, and the
decision about what to do instead is the maintainer's. No `test` confirmation,
no v2, nothing published.

**The fourth row — *"the SQNR ranking and the exclusion sweep disagree → believe
the sweep"*.** They did disagree, and the disagreement is the finding. It is
recorded here rather than resolved quietly, as the rule requires.

## The table

All rows scored on `val`, against the PyTorch fp32 reference **0.7733835**.

| variant | val mAP@0.5 | drop | QDQ nodes outside head | p50 (EPYC proxy) | bytes |
|---|---:|---:|---:|---:|---:|
| `00-head-fp32-anchor` | 0.747107 | 0.026277 | 619 | 25.36 ms | 4 365 875 |
| **`10-head-plus-model10`** | **0.748021** | **0.025363** | 544 | 25.55 ms | 5 062 739 |
| `11-head-plus-model1` | 0.746465 | 0.026918 | 613 | 26.33 ms | 4 377 459 |
| `12-head-plus-model2` | 0.745748 | 0.027636 | 581 | 28.05 ms | 4 371 310 |

`winner: null`. Only one module improved on the anchor at all, so the
pre-registered combined run was correctly not called for.

## The anchor reproduced, which is what made the rest admissible

The kernel refuses to attribute a residual it cannot first reproduce. P9
measured the head-fp32 graph at **0.7481** on `val`; this run measured
**0.747107**, a difference of **0.00099** — inside the 0.02 tolerance the kernel
enforces, and consistent with P9's own observation that every meaningful row
replicates to within 0.001 while the collapsed rows swap freely.

## Finding 1 — the diagnostic named a suspect, and the suspect was already named

The corrected SQNR diagnostic ran for the first time here. P9 never executed it:
`quantisation_error` only fires on a winner, and P9 had none, so its
`tensor_error` was empty. **Its direction is a trap and P9 got it backwards
once** — `qdq_err` is SQNR in decibels, `20·log10(‖x‖/‖x−y‖)`, so higher is
better and the damaged tensors are at the *bottom*. These are the bottom, over
246 tensors compared on 8 frames:

| tensor | qdq SQNR dB | xmodel SQNR dB |
|---|---:|---:|
| **`/model.10/m/m.0/attn/Softmax_output_0`** | **23.90** | **11.16** |
| `/model.1/conv/Conv_output_0` | 25.56 | 21.95 |
| `/model.2/cv1/conv/Conv_output_0` | 25.98 | 18.58 |
| `/model.2/cv2/conv/Conv_output_0` | 29.32 | 16.11 |
| `/model.1/act/Mul_output_0` | 29.33 | 21.16 |
| `/model.0/conv/Conv_output_0` | 31.54 | 31.07 |
| …the remaining 240 cluster at 32–34 dB | | |

The worst tensor in the graph is the **C2PSA attention softmax in `/model.10/`**,
1.65 dB clear of the next and with an `xmodel` error of 11.16 dB against a next
worst of 14.02. That is the same module the standing hypothesis pointed at — a
1517× weight-scale increase on `model.10.m.0.attn.qkv.conv.weight`, seen in a
local smoke test on a stock YOLO11n.

**So the hint and the instrument agree.** That is a real result and it is the
last good news in this document.

## Finding 2 — and excluding it bought almost nothing

`/model.10/` was swept because the ranking pointed at it *and* because the
pre-registration required it to be swept regardless, precisely so that "no other
culprit found" could not be unfalsifiable. Excluding it:

- removes **75 QDQ nodes**, 619 → 544, i.e. **12 %** of everything still
  quantised in the anchor graph, **including the single most damaged tensor**;
- costs **+0.193 ms** median and **+696 864 bytes**;
- buys **+0.000914 mAP@0.5**.

**0.000914 is below `MAP_NOISE = 0.005`**, the threshold `sbr/export/selection.py`
uses for "these are the same candidate as far as accuracy goes". By the project's
own measuring stick this is not a distinguishable improvement, and it recovers
about **3.6 %** of the 0.0254 residual.

The other two ranked modules made it **worse** — `/model.1/` by 0.0006 and
`/model.2/` by 0.0014, both also inside the noise band, so the honest reading of
all three is *no effect* rather than *a small harmful effect*.

## Finding 3 — the residual is still unattributed, and now that is a measurement

This is the conclusion, and it is a negative one:

> **No module outside the detection head accounts for the residual by a
> distinguishable amount.** The three modules the corrected diagnostic ranks as
> most damaged, one of which was independently predicted by a weight-scale
> anomaly, together explain none of the 0.0254 the head-fp32 graph loses.

That is stronger than P9's "the residual is unattributed", which was an absence
of evidence. This is evidence of absence for the obvious hypothesis: **a low-SQNR
activation does not imply a task-metric cost.** The most damaged tensor in the
graph can be repaired for free and the mAP does not move. Whatever the 0.0254 is,
it is distributed across the remaining 544 QDQ nodes rather than concentrated in
a module a sweep of this shape can find.

The pre-registered rule anticipated exactly this shape of disagreement and said
which to believe: *"A ranking is a pointer; an exclusion that changes mAP is a
measurement."* The sweep is believed. The ranking is recorded, not deleted — it
is a correct answer to a different question.

## What the alternative costs, since the rule says to state it

**The gate stays at 0.02.** It has now fired three times on this artefact and
been right three times. What is on the other side of it:

| option | cost | what it buys |
|---|---|---|
| **Ship the 0.0254 trade** | a product decision, not a probe's | a validator 3.3 % relatively worse at finding bins than the fp32 model. It needs a `test` measurement that deliberately does not exist |
| **Quantisation-aware training** | a GPU run, new code, a new artefact version | the only remaining route to a *post-training-free* int8 graph. **The maintainer's decision — explicitly not attempted here** |
| **Serve fp32** | violates the latency budget by construction; unmeasured at 448 in this run | not evaluated |
| **A different architecture** | reopens P5 | D-FINE-N remains unevaluated, recorded as a gap |

Nothing here recommends one. The probe's job ended when the rule fired.

## Things that went wrong, recorded rather than tidied away

**The report recorded the wrong revision.** `dataset.revision` reads `"main"` —
the config literal, not the sha `download_dataset` actually resolved. The
`composition` block matches the pinned `8666aa23…` exactly (370 / 1 110 / 17 474,
splits 13 265 / 2 823 / 2 866), so the **data is right and the record of it was
not**. Fixed so the resolved revision is what gets written down; a report that
names its pin as "main" is a report nobody can reproduce from.

**A first reading of this file said every `qdq_err` was `None`.** It was not —
the keys are `qdq_sqnr_db` and `xmodel_sqnr_db`, deliberately renamed away from
anything that could be misread as an error magnitude, and the reader looked for
the old name. Recorded because the near-miss was a conclusion ("the diagnostic
produced no values") that would have been wrong in the same direction P9's
sort-order bug was wrong.

## A note on latency that is bigger than anything measured here

The anchor graph — same bytes, same onnxruntime 1.29.0 — measured **36.6 ms**
in P9 on a Kaggle Xeon and **25.36 ms** here on a Kaggle EPYC 7B12. That is
**31 % apart on identical work**, entirely from which machine Kaggle happened to
allocate.

Both are `representative: false`. This is the clearest evidence yet for why a
proxy cannot close the latency half of the phase-2 gate, and it is larger than
every latency difference this probe found between configurations. The p50 column
above is usable for ranking variants *within this run* and for nothing else.

## What this changes

- **docs/07 phase 2** — the last model blocker on the validator is diagnosed as
  far as post-training quantisation can diagnose it, and is **not cleared**.
- **docs/11** — validator v1 cannot ship as a post-training int8 export. Best
  known configuration, `val`, proxy hardware: **0.7480 against 0.7734, missing
  the gate by 0.0054**.
- **docs/12 P10** — closed. Two rows fired: the 0.02–0.10 miss, and the
  ranking-versus-sweep disagreement.
- **`sbr.export.QuantSettings`** — `exclude_head=True` remains the best known
  configuration for any YOLO11 export here. `exclude_prefixes` has no
  evidence-backed value to recommend.
