# P5 – Validator architecture

*Run 2026-08-16. Kernel `hlexnc/sbr-probe-latency`, versions 1 and 2.*

**Question.** Does RF-DETR-nano or D-FINE-N fit 50 ms at 448 on two pinned vCPUs?
Research note 01 § 3 reports DETR backbones generalising better from small data,
which is our regime – but the published comparisons are on GPU.

**Method.** Latency first, on stock weights, through the same `bench_latency`
path as P4. Only a candidate that fits the budget makes accuracy a question worth
a GPU hour.

**Hardware.** Kaggle CPU kernel, Intel Xeon @ 2.20 GHz, onnxruntime pinned to 2 of
4 vCPU. A proxy, and about 25 % noisy run to run (see P4).

---

## Result

| candidate | p50 @ 448 | budget | verdict |
|---|---:|---:|---|
| **YOLO11n** (incumbent) | **26.6 – 33.0 ms** | 50 ms | fits, with ~40 % headroom |
| **RF-DETR-nano** | **475.3 ms** | 50 ms | **9.5× over** |
| D-FINE-N | – | 50 ms | **not evaluated** |

### RF-DETR-nano

475 ms is not a near miss. It is an order of magnitude outside a budget that the
whole free-tier thesis rests on, and no amount of quantisation or input-size
tuning closes a 9.5× gap. Research note 01 § 3's generalisation argument may well
be right; it is simply unaffordable on 2 vCPU.

### D-FINE-N – not evaluated, which is not the same as not fitting

Two attempts, two tooling failures rather than two answers:

1. `torch.onnx.export` needed `onnxscript` for its dynamo path. Fixed in run 2.
2. The exported graph then failed to load: `NOT_IMPLEMENTED: Could not find an
   implementation for Cos(7)`. The transformer's positional encoding emits a
   `Cos` op that this onnxruntime build has no CPU kernel for at that opset.

docs/12's rule for P5 turns on whether a candidate **fits**. A candidate that
never ran has not answered that, and recording it as "did not fit" would be
manufacturing evidence for a conclusion that happens to be convenient. It is
recorded as a gap.

Fixing it is a higher opset or a different export path, and it is cheap. It is
not urgent: D-FINE-N is the same class of architecture as RF-DETR-nano, which
missed by 9.5×, so the prior is poor.

---

## Decision rule, as docs/12 stated it in advance

> **No candidate fits 50 ms on 2 vCPU** → YOLO11n stays. Close the question and
> record the numbers so it is not reopened on a blog post.

**Fires, with one candidate outstanding.** RF-DETR-nano was measured and is 9.5×
over. D-FINE-N is unevaluated. **YOLO11n stays**, and this is the number to quote
when the question is reopened: *a nano DETR costs 475 ms per frame on the CPU this
service runs on.*

The other two branches – "fits with ≥ 20 % headroom" and "fits marginally" – did
not arise.

## Resolves

**docs/04 § 6's architecture choice**, with evidence rather than inheritance from
the predecessor. Reopen only with (a) a D-FINE-N number, or (b) a candidate
measured under 50 ms on 2 vCPU – not with a paper reporting GPU throughput.
