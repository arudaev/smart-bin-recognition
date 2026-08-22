# P13 – Is an fp32 validator ship profile viable?

*Pre-registered 2026-08-22, **before any measurement**, per this repository's
rule that a probe with no decision rule stated in advance does not run. Raw data
will land at [`data/P13-fp32-viability.json`](data/P13-fp32-viability.json).*

**Question.** The ship gate refuses any artefact that is not quantised
([`ml/src/sbr/export/onnx_export.py:319`](../../../ml/src/sbr/export/onnx_export.py)),
and its failure string states a *rationale*:

> `artefact is not quantised – it will not meet the latency budget`

A second opinion argued that this rationale is now empirically false and that
the gate should be split into per-format profiles, so an fp32 validator could
ship. **Should it?**

---

## The premise the argument rested on is not true

The second opinion held that *"the assumption an unquantised validator cannot
meet latency is now empirically false"*. It is not false. It is **unmeasured**.

[P12](P12-the-controlled-host.md) measured the validator at 18.252 ms p50 on
representative hardware, and it measured it **on the int8 graph**. The proof is
in the run's own health report:

```
$ python -c "import json; print(json.load(open('artifacts/gce/results/health.json'))['artefacts']['validator']['quantised'])"
True
```

**fp32 validator latency on representative hardware has never been measured by
this project.** The gate's rationale is therefore neither confirmed nor refuted
today, and the argument for splitting the gate was made against a number that
does not exist. That is what this probe is for.

*The idea may still be right.* `artifacts/local/validator-v1.onnx` is fp32
(md5 `542b79cca224236a84943628484cb54e`, byte-identical to `model-fp32.onnx`),
scores 0.7524 mAP@0.5 on `test`, and fails **exactly one** gate — the
not-quantised one. Its int8 sibling fails on accuracy instead, by 0.727 mAP.
Neither can ship. If fp32 turns out to fit the latency budget, the project has a
shippable validator and does not have one today.

---

## What is measured

**Arm A – free local triage, `representative: false`.** The fp32 graph against
the int8 graph on this workstation: same onnxruntime 1.29.0, same 448 input,
same thread count, 5 repeats × 50 iterations, warmup 10, medians reported.
The output that matters is the **ratio** `R = fp32_p50 / int8_p50`, not either
absolute figure — a laptop cannot hold an absolute still
([P8](P8-recovery-measurements.md)), but a ratio taken back-to-back on one box
in one session is a far more robust quantity than either of its terms.

**Arm B – the concurrency arithmetic, a projection and labelled as one.**
P12 measured a **49 ms** frame at one bin yielding **5** concurrent scanners,
and 2 at six bins. The validator is 18.252 ms of that frame. So

```
frame_fp32  =  49  +  18.252 × (R − 1)
```

and the ceiling scales roughly as `49 / frame_fp32 × 5`. This is a projection
over a measured baseline, not a measurement.

**Arm C – the paired GCE run, `representative: true`, only if the rule below
fires.** Both formats on **one instance, alternating** (int8, fp32, int8, fp32)
rather than fp32 here against P12's numbers from a different VM. Commit
`8fe1450` is the reason: two VMs of identical spec reproduced p50 to 0.05 ms and
moved p95 by up to 3.9 ms, so an unpaired comparison would be measuring the
instance as much as the format.

---

## Decision rule, stated before the measurement

### Whether to spend the money

The latency gate for the validator is **50 ms**. Against P12's 18.252 ms int8
p50, fp32 clears that gate only if

```
18.252 × R  ≤  50      ⟺      R  ≤  2.74
```

| Arm A result | Action |
|---|---|
| **R ≥ 2.74** | fp32 misses the latency gate on the projection. **Do not spend the GCE money.** Recommend against the split, and say the gate's rationale is now supported by evidence rather than merely asserted |
| **R < 2.74** | fp32 is live. **Spend the one pre-approved run** and convert the projection into a paired measurement |

### What the result means for the gate

| Arm C result | Recommendation |
|---|---|
| fp32 p50 > 50 ms | **No profile.** The gate's rationale is correct as written; leave line 319 alone |
| fp32 p50 ≤ 50 ms **and** concurrency at 1 bin equals the int8 arm within repeat noise | **Recommend the split.** fp32 costs nothing that matters and unlocks a shippable validator |
| fp32 p50 ≤ 50 ms **but** concurrency at 1 bin is below the int8 arm | **Recommend the split with the price named in scanners**, and require the fp32 profile to carry its concurrency cost in the sidecar. A gate that hides what a format costs is the kind of number this project forbids |

**`max_accuracy_drop` stays `0.02` in every profile, in every branch of this
rule.** Nothing here is a route to loosening an accuracy gate; the only question
on the table is whether "must be quantised" is a proxy for "must be fast" that
has outlived its accuracy.

### What this probe does not decide

Whether to *merge* the split. The implementation is staged on its own branch,
unmerged, for the maintainer. Phase 2's concurrency gate already fails at 5
against 10 and an fp32 validator cannot fix that — at best it does not make it
worse. **Nothing here reopens or fires the kill criterion.**

---

## Result — ran 2026-08-22

**The rule's third row fires: recommend the split, with the price named in
scanners.** The gate's stated rationale is empirically false on this
architecture, and the cost of acting on that is exactly one concurrent scanner.

### Arm A — the free triage, and why it was nearly a trap

| | fp32 | int8 | ratio |
|---|---:|---:|---:|
| p50, 5 alternating cycles | 39.2 ms | 65.9 ms | **0.5917** |

fp32 measured **41 % faster** than int8, R = 0.59 against a 2.74 spend
threshold, so the rule said spend. **That number is not transferable and the
report says so in the file.** The development workstation is a **Snapdragon X
Elite — ARM64, no AVX-512 VNNI**; the service host is Cascade Lake, which has
it. A ratio cancels host *noise*, because the noise moves both arms together. It
does not cancel a systematic per-*format* difference between hosts, and
instruction-set support for int8 convolution is exactly that.

Measured on the real host the ratio is **1.3664**, not 0.5917 — the two hosts
disagree about which format is faster. Arm A was still worth running: it cost
nothing and it correctly said "fp32 is live, go and measure it". It would have
been worth very little as an answer.

*(Arm A also found a bug on the way: `sbr.bench.hardware()` labelled this
Windows box a **Kaggle CPU kernel**, because `Path("/kaggle")` is
absolute-from-the-drive-root on Windows and the machine happens to have that
directory. A latency figure stamped with silicon it never ran on is the exact
failure this project's discipline exists to prevent. Fixed at `ff60b8e`, with
tests.)*

### Arm C — paired, on the service host, `representative: true`

GCE `n2-standard-4`, `europe-west3-a`, CPU platform pinned to Intel Cascade
Lake, service on CPUs 0–1 and the client on 2–3, **both formats on one
instance, arms alternated cycle by cycle**. Host flags confirmed
`avx512f`, `avx512_vnni`, `avx2`. VM and disk destroyed on exit and verified
gone. About **USD 0.29**.

| | int8 | **fp32** | budget |
|---|---:|---:|---:|
| validator p50 | 17.921 ms | **24.605 ms** | ≤ 50 ms |
| p50 per cycle | 17.66 – 17.92 | 24.10 – 24.61 | – |
| **ratio, paired median** | – | **1.3664** | – |
| clears the latency gate | yes | **yes, by 25.4 ms** | – |
| frame server cost @ 1 bin | 48.0 ms | 56.0 ms | – |
| **concurrent scanners @ 1 bin** | **5** | **4** | ≥ 10 |

The p95 curve, worst repeat at each level, against the 250 ms budget:

| scanners | 1 | 2 | 3 | 4 | **5** | 6 |
|---|---:|---:|---:|---:|---:|---:|
| int8 p95 ms | 54.9 | 104.9 | 149.9 | 199.2 | **247.7** | 289.1 |
| fp32 p95 ms | 66.2 | 126.0 | 182.2 | **239.1** | 296.6 | 368.0 |

int8 clears 250 ms at five scanners with 2.3 ms to spare; fp32 clears it at four
with 10.9 ms and misses at five. **The int8 arm reproduced P12 exactly — 5
scanners, and 17.92 ms against P12's 18.252 on a different VM of the same
spec — which is what makes the fp32 arm beside it worth believing.**

Arm B projected 4.4 scanners from arm A's ratio. Measured: 4.

## Recommendation

**Split the gate, and make the fp32 profile carry its cost.**

The gate at `onnx_export.py:319` refuses an unquantised artefact with the
rationale *"it will not meet the latency budget"*. **On this architecture, at
448, that is false by a factor of two: 24.6 ms against 50 ms.** The gate is
enforcing a proxy that has outlived the fact it stood for.

What acting on it buys and costs:

| | int8 validator | fp32 validator |
|---|---|---|
| accuracy vs fp32 reference | **−0.727 mAP@0.5** (P9) | 0.0 by construction |
| `may_ship` today | **false** — fails accuracy | **false** — fails "must be quantised" |
| latency | 17.9 ms | 24.6 ms, **passes** |
| concurrency @ 1 bin | 5 | **4** |
| size | 3.1 MB | 10.5 MB |

**The trade is one concurrent scanner for a validator that is actually
correct.** The concurrency gate already fails — 5 against 10 — so the honest
framing is not "fp32 costs us the gate" but "fp32 costs one scanner in a gate
that is failing either way, and is the only route to a validator that can ship
on accuracy at all". P9 established that post-training int8 over the whole graph
is not viable for this architecture; P10 found no module outside the detection
head to blame. fp32 is what is left.

**Three conditions on the recommendation, and they are not negotiable:**

1. **`max_accuracy_drop` stays `0.02` in every profile.** Nothing here loosens an
   accuracy gate; the only question on the table was whether *"must be
   quantised"* is a proxy for *"must be fast"*.
2. **The fp32 profile must carry its concurrency cost in the sidecar.** A gate
   that hides what a format costs is the kind of number AGENTS.md forbids. 4, not
   5, and it should be readable from the artefact.
3. **This is measured at 448, on Cascade Lake, at one bin per frame.** A different
   input size, a host without VNNI, or a six-bin scene are all separate
   questions. At six bins neither format was measured here.

## What this probe does not do

**It does not merge anything.** The implementation is staged on
`feat/fp32-ship-profile`, unmerged, for the maintainer. Phase 2's concurrency
gate fails at 5 against 10 and an fp32 validator cannot fix that — at best it
does not make it much worse. **Nothing here reopens or fires the kill
criterion**, and nothing here publishes an fp32 artefact: the graph travelled to
the measuring VM in the harness tarball and was mounted through
`SBR_ARTEFACT_DIR`, because putting an ungated graph in the model repo would
leave it one environment variable away from a deployment.
