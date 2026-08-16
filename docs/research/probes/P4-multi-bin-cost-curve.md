# P4 – Multi-bin cost curve

*Run 2026-08-16. Kernel `hlexnc/sbr-probe-latency`, versions 1 and 2.*

**Question.** What does a frame actually cost at 0, 1, 3 and 6 bins, and does
batching the crops through one ONNX call beat *n* sequential ones?

**Hardware.** Kaggle CPU kernel, Intel Xeon @ 2.20 GHz, onnxruntime pinned to
**2 of 4 vCPU**, onnxruntime 1.28.0. `Hardware.representative` is **false** – this
is a proxy for a service container, not one.

**Weights.** Stock COCO checkpoints for `yolo11n` @ 448 and `yolo11s-cls` @ 320,
untrained on this project's data, int8-quantised on synthetic calibration.
Sound for latency, which depends on architecture and input shape; meaningless
for accuracy, which is not measured here.

---

## The measurement

Two runs, because the first raised a question the second was built to answer.
Both are reported, because the gap between them is itself a result.

| | run 1 | run 2 |
|---|---:|---:|
| validator alone @ 448 | 26.6 ms | 33.0 ms |
| identifier alone @ 320, batch 1 | 17.4 ms | 21.7 ms |

**Run-to-run variance is about 25 %.** Same kernel, same pinning, same code, six
minutes apart. A Kaggle kernel is a shared box and it shows. Every number below
is therefore a range, not a value, and the ship gate should not be decided on
this host without saying so – which `gate.py` already refuses to do.

### The frame

p50 milliseconds for one whole frame: the validator once, then the identifier
over *n* crops.

| bins | run 1 batched | run 1 sequential | run 2 batched | run 2 sequential |
|---:|---:|---:|---:|---:|
| 0 | 26.7 | – | 32.8 | – |
| 1 | 65.7 | 65.6 | 77.3 | 77.5 |
| 3 | 88.6 | 110.7 | 107.7 | 134.0 |
| 6 | 154.2 | 162.6 | 188.4 | 206.3 |

### Where the milliseconds go

Run 2 also timed the identifier alone at each batch size, so the frame
decomposes:

| bins | identifier alone | validator + identifier | frame measured | unaccounted |
|---:|---:|---:|---:|---:|
| 1 | 21.4 | 54.4 | 77.3 | 22.9 |
| 3 | 60.2 | 93.2 | 107.7 | 14.5 |
| 6 | 117.2 | 150.2 | 188.4 | 38.2 |

There is **15–40 ms per frame that belongs to neither graph**. The likely cause is
alternating between two onnxruntime sessions, each with its own thread pool, on
two cores. It is not separable from this host's own variance, and it is one of
the things the load test on a pinned container will settle.

---

## Decision rules, as docs/12 stated them in advance

### "6-crop frame ≤ 100 ms → docs/05 § 3's ceiling stands roughly as written"

**Missed, by a lot.** 154–188 ms. The rule's other branch fires:

> **6-crop frame > 100 ms** → re-derive the ceiling on the curve and state
> concurrency as a range over scene complexity, not a single number.

### "Crop batching gives ≥ 2× → make batched crop inference a service requirement"

**It does not.**

| bins | run 1 | run 2 |
|---:|---:|---:|
| 3 | 1.25× | 1.24× |
| 6 | 1.05× | 1.10× |

Consistent across runs and nowhere near 2×. The decomposition says why: the
identifier costs 21.4 ms at batch 1, 60.2 at batch 3 and 117.2 at batch 6 – that
is 21.4, 20.1 and 19.5 ms **per crop**. Batching saves about 9 % per crop and no
more, because on two pinned threads the graph is already arithmetic-bound. There
is no per-call overhead left to amortise. Batching is a GPU technique and this is
a CPU.

**So the rule does not fire, and docs/01 § 4 is wrong where it says batching is
"a service requirement, not an optimisation".** It is an optimisation, worth
10–25 %, and it is implemented and kept – but the cost model must not be built on
it and the docs must stop calling it load-bearing.

---

## What this does to the concurrency ceiling

docs/05 § 3 derives its headline like this:

```
2 vCPU ÷ 0.065 s  ≈  30 frames/second of total capacity   (ONE bin per frame)
```

**That arithmetic double-counts the vCPUs.** The 65 ms is a latency measured with
onnxruntime *pinned to both cores*; it is not one core-second of work that two
cores can do twice over. Total capacity is `1 ÷ 0.065 ≈ 15` frames/second, not 30.
Running two single-threaded workers instead would roughly double each frame's
latency and land on the same total, because throughput is bounded by the CPU work
either way.

Re-derived on the measured curve, at the 3 fps a scanner achieves:

| bins in frame | frame (batched) | frames/s total | concurrent scanners |
|---:|---:|---:|---:|
| 1 | 65.7 – 77.3 ms | 12.9 – 15.2 | **4.3 – 5.1** |
| 3 | 88.6 – 107.7 ms | 9.3 – 11.3 | 3.1 – 3.8 |
| 6 | 154.2 – 188.4 ms | 5.3 – 6.5 | **1.8 – 2.2** |

docs/05 § 3 currently says *"3 to 10 concurrent scanners depending on scene
complexity"*. On this evidence it is **roughly 2 to 5**, and the phase-2 gate's
"≥ 10 concurrent scanners at one bin per frame" is **not met** – it is out by a
factor of two before scene complexity is considered at all.

Two caveats, and neither rescues the number:

- This is a **prediction from single-stream latency**, not a measurement of
  concurrency. The load test against a pinned container is what settles it.
- This host is a **proxy** and it is ~25 % noisy. Cloud Run's CPU may be faster.
  It would have to be about twice as fast to reach ten.

---

## Resolves

- **docs/05 § 3** – the ceiling, the arithmetic error in it, and the range.
- **docs/01 § 4** – "batching … is a service requirement, not an optimisation" is
  withdrawn; the latency budget table is replaced with measured numbers.
- **docs/00 § 6** – the concurrency success criterion is not met on this evidence.
- **docs/07** – the phase-2 gate's concurrency half. The latency half *passes*:
  validator 26.6–33.0 ms against a 50 ms budget, identifier 17.4–21.7 ms against
  25 ms per crop.

## What would move it

Cheap, in order:

1. **Drop the validator to 384 px.** Already listed in docs/05 § 7 as the first
   response to saturation, and the validator is a third of a one-bin frame.
2. **Find the 15–40 ms that belongs to neither graph.** If it is session
   switching, one session holding both graphs, or a warm pool, may recover it.
   At one bin it is a third of the frame.
3. **Cap crops harder.** `SBR_MAX_CROPS` already defaults to 6; 3 would halve the
   worst case, with the remainder deferred to the next frame.
4. Accept a lower ceiling and plan the pilot around 4 concurrent scanners rather
   than 10. The client-side gates make this less alarming than it sounds – a scan
   is ~5 s and then the result lock stops it – but docs/05 § 3's "tens of
   thousands of monthly users" needs recomputing on the real number.
