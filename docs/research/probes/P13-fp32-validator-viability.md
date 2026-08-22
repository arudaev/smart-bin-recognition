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

## Result

*Not yet run. This section is filled in after the measurement, and the rule
above is not edited when it is.*
