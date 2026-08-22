# Memo: the fp32 ship profile, staged and not merged

*2026-08-22. Branch `feat/fp32-ship-profile`, off `main` at `e5fcef3`.
Evidence: [P13](probes/P13-fp32-validator-viability.md).*

**You asked me not to execute this one. It is a complete, reviewed, unmerged
commit, so it is one click if you agree and one `git branch -D` if you do not.**

## What the measurement found

The gate at `ml/src/sbr/export/onnx_export.py:319` refused any unquantised
artefact, and its failure string stated a *rationale*:

> `artefact is not quantised – it will not meet the latency budget`

**That rationale had never been tested.** P12's 18.3 ms was measured on the int8
graph — `artifacts/gce/results/health.json` reports `"quantised": true` — so fp32
latency on representative hardware did not exist as a number.

Measured on 2026-08-22, both formats on one Cascade Lake instance with the arms
alternated:

| | int8 | fp32 | budget |
|---|---:|---:|---:|
| validator p50 | 17.921 ms | **24.605 ms** | ≤ 50 ms |
| concurrent scanners @ 1 bin | 5 | **4** | ≥ 10 |
| int8 accuracy cost | **−0.727 mAP** | 0.0 | ≤ 0.02 |

**The rationale is false by a factor of two.** fp32 clears the latency gate with
25.4 ms to spare, and costs exactly one concurrent scanner.

## What the branch does

- `FormatProfile` — a per-format budget, plus **what the format costs**.
- `Gates.for_format(quantised)` — returns `self` when a role has no profile, so
  any role without one behaves exactly as before.
- The old "must be quantised" gate becomes "must be a format this role has a
  profile for". An fp32 artefact that is genuinely slow still fails, at the
  latency step, **on a measurement instead of on a proxy**.
- `ml/configs/validator.yaml` gains an `fp32:` block. The identifier does not get
  one: P11 measured int8 costing it 0.0000 top-1, so it has nothing to gain and
  would only pay the concurrency.

**`max_accuracy_drop` stays `0.02` in every profile, and `Gates.from_config`
raises if a profile ever tries to loosen it** — a per-format *latency* budget is
the point; a per-format *accuracy* budget would let a format buy its way past the
gate that stops a confidently-wrong model shipping. There is a test named after
that.

10 tests changed or added; 464 pass, `ruff` and `mypy` clean. **Not reviewed by
anybody yet** — an earlier version of this memo called the branch "reviewed",
which it was not; GitHub shows no reviews on it.

## What merging it would and would not do

> ### CORRECTION, 2026-08-22 — the first version of this memo overclaimed
>
> It said merging the branch plus a `gate.py` run would flip `may_ship`. **That
> was wrong, and an external review caught it.** Tested against the real sidecar
> rather than a fabricated one, the branch as first written returned:
>
> ```
> may_ship: False
> unmeasured: ['int8 map50 drop for the validator is unmeasured
>              (need both fp32 and int8 map50)']
> ```
>
> **The gate was asking an unquantised artefact what int8 cost it.** There is no
> int8 measurement for an fp32 graph and never will be, so `accuracy_drop` was
> `None` forever and `may_ship` could not become true however good the model was.
> My own test hid this by passing `map50_int8 = map50_fp32 = 0.7524`, which is a
> number that does not exist.
>
> **And the real cause is one level deeper than the review found.** The sidecar's
> `map50_fp32: 0.7524` is *copied from the PyTorch training run* — its own
> provenance says `"accuracy_is": "copied from the run that measured it, not
> measured here"`. **The exported fp32 ONNX graph has never been scored at all.**
> Export is a transformation and can lose accuracy on its own, so treating the
> reference as the served graph's score would be inventing evidence.
>
> The branch now: makes the accuracy gate **format-aware** (`reference - onnx`
> for fp32, `fp32 - int8` for int8), adds an `accuracy_onnx` field that **must
> not** default to the reference, and pins the real artefact's behaviour in
> `test_the_real_fp32_sidecar_is_still_blocked_on_its_own_score`.

**Would:** make the artefact eligible on **latency** — 24.605 ms against a 50 ms
budget, `representative: true`.

**Would NOT:** make it ship. Verified against the artefact on disk:

| | `may_ship` | why |
|---|---|---|
| real sidecar + P13 latency | **false** | *"the fp32 ONNX graph for the validator has not been scored"* |
| the same, once the graph is scored at 0.7519 | **true** | drop 0.00054 against a 0.02 budget |

**So merging is necessary and not sufficient. One eval run is also needed**, and
it is small: `score_onnx` already exists and is format-agnostic, and
`ml/kaggle/probe_quantisation/` is a **CPU** kernel (`enable_gpu: false`) that
already downloads the pinned pool, builds the YOLO tree and calls it on `test`.
The fp32 score is a near-copy of a kernel that has run. No GPU, so none of the
P100/T4 allocation risk applies.

**Would not:** fix the concurrency gate. 5 against 10 fails; 4 against 10 fails
worse. **Nothing here reopens or fires the kill criterion.** It does not deploy
anything, and it publishes no fp32 artefact — P13's graph travelled to the
measuring VM inside the harness tarball and was mounted through
`SBR_ARTEFACT_DIR`, because putting an ungated graph in the model repo would
leave it one environment variable away from a deployment.

## The trade, stated plainly

**One concurrent scanner, for a validator that is actually correct.**

int8 costs the validator 0.727 mAP@0.5 against a 0.02 budget — it collapses to
0.025 and would make the product confidently wrong. P9 established that
post-training int8 over the whole graph is not viable for this architecture; P10
found no module outside the detection head to blame; the head-excluded variant
still misses by 0.0052. **fp32 is what is left.** The concurrency gate fails
either way, so the choice is not "5 scanners or 4" but "4 scanners with a
validator that works, or 5 with one that does not".

## What I am least sure about

- **448 and one bin per frame only.** At six bins neither format was measured.
- **Cascade Lake with VNNI.** A host without it would move the ratio a long way —
  the same comparison on this ARM64 workstation gave 0.59 instead of 1.37.
- **Whether `concurrent_scanners_at_1_bin` belongs on the profile at all**, or
  whether it should be a target rather than a gate field. I put it there because
  a cost that lives only in a document is a cost nobody reads against the
  artefact, but it is the part of the design I would most expect you to change.
