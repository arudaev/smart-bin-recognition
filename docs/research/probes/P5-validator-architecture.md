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
| D-FINE-N | – | 50 ms | **not evaluated** – the session will not open |

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

#### Re-attempted 2026-08-17, and it is the graph, not the kernel

The exported graph survived — `artifacts/probe2/probe/dfine-nano.onnx`,
15 421 442 bytes, written by run 2 — so the load was retried on a **different
machine and a different runtime** to find out whether the failure belonged to
Kaggle or to the artefact. It belongs to the artefact:

```
NotImplemented: [ONNXRuntimeError] : 9 : NOT_IMPLEMENTED :
Could not find an implementation for Cos(7) node with name
'/model/encoder/aifi.0/position_embedding/Cos'
```

- onnxruntime **1.26.0**, `CPUExecutionProvider`, local x86-64 Python 3.13
- the same op, the same node, at **session creation** — before any input is fed
- constant folding also declines it first:
  *"Could not find a CPU kernel and hence can't constant fold Cos node"*

So there is **no latency to measure**, on any host: the session cannot be
created. The node is in the AIFI encoder's sinusoidal positional embedding,
where `Cos` is emitted at a type this build has no CPU kernel for — which is an
export-time type choice, fixable by re-exporting at a higher opset or by casting
the embedding to float32 before the trig ops.

**Still `not evaluated`, and still not `did not fit`.** The distinction is the
whole point of this section and it now has a precise reason attached rather than
a summary of one.

**And it is not a docs/12 P8 candidate.** P8 is measuring what can recover the
concurrency gate; a validator that cannot open a session is not a recovery. Even
a working latency number would not make it one — the service's decoder reads a
YOLO head shape from the sidecar (`4 + len(classes)`, deliberately, so a
transposed head raises rather than producing plausible boxes in the wrong
places), and a DETR head is a different output contract. Adopting D-FINE-N means
pipeline integration, and that is separate work with its own reasons, not
something to fold into a concurrency verdict.

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
