# P8 – The three recoveries, and whether the gate can be recovered

*Run 2026-08-17. `service/loadtest/matrix.py`, `service/loadtest/session_switch.py`.*

**Question.** docs/07's phase-2 kill criterion fired on its first half — 4
concurrent scanners at one bin against a gate of 10 — and its second half,
*"and cannot be recovered"*, was never tested. docs/05 § 7 named three cheap
recoveries in advance and none had been measured. This probe measures them.

**Hardware.** `docker run --cpus 2` (cgroup quota 2.0), `linux/arm64` native,
Snapdragon X1E80100 @ 3.40 GHz, onnxruntime 1.28.0, Python 3.11.
**`representative: false`** — Cloud Run is x86_64, so this is a pinned proxy and
not the serving tier. Every figure below is a *within-host* comparison.

**Artefacts.** Stock COCO YOLO11n @ 448 (and @ 384) and YOLO11s-cls @ 320, int8,
**untrained on this project's data**, served with `SBR_ALLOW_UNGATED=1`. Sound
for cost, which depends on architecture and input shape; meaningless for
accuracy, which is not measured here. They are now reproducible:
`ml/scripts/probe_artefact.py` builds them, including the eighty-class
relabelling that lets the service's decoder run against a stock head.

---

## Nought: the measurement itself had to be repaired first

Three defects, each of which would have produced a plausible number that was
wrong. They are listed before the results because each one was found by running
the thing rather than by reading it.

**The crop cap was not applied to the scene being measured.** `SBR_FORCE_CROPS`
replaced the crop list *after* `SBR_MAX_CROPS` had truncated it, so a forced
six-bin frame ran six crops however the cap was set. P8c would have measured an
uncapped service and reported the result as evidence about a cap. Fixed in
`pipeline.py`; the matrix now sends a debug frame first and **refuses to
measure** unless the service reports exactly six detections and three crops.

**The ladder could not resolve the win it was looking for.** The old levels
stepped 1…6, 8, 10, 12, so a recovery moving the ceiling from 6 to 7 was
invisible. Levels are now contiguous 1…12, a level counts as passed only if it
passed in **every** repeat, and the verdict is the largest **monotonic passing
prefix** — one level scraping under budget above a failed one is noise, not
capacity.

**The host was not quiet, and it mattered more than anything else here.** The
first matrix run was taken while Kaggle artefact downloads ran on the same
laptop. Its baseline measured **4** concurrent scanners; the identical
configuration on a quiet host measures **7**, with p95 at four scanners falling
from 229/211/195 ms to 148/147/142 ms. **This is the single largest effect in
the whole probe, and it is not a property of the service.** It is why each scene
is now bracketed by a baseline at both ends and why the ARM laptop cannot be
allowed to pronounce on Cloud Run.

---

## P8b – Where the 15–40 ms goes

Answered first because it turned out to be the one that moves.

### The decomposition

One scanner, `--debug`, p50 of three repeats. `_validate` includes letterbox and
NMS; `_identify` times only `session.run`; so crop preprocessing, JPEG decode,
colour and the resolver all land in `other_server`.

| bins | validator | identifier | other_server | server total | wall |
|---:|---:|---:|---:|---:|---:|
| 1 | 28.3 | 13.3 | **15.3** | 55.0 | 73.5 |
| 3 | 38.1 | 38.1 | **21.8** | 98.0 | 120.0 |
| 6 | 38.8 | 67.7 | **27.6** | 134.0 | 156.9 |

`other_server` is **15.3 ms at one bin**, over the 10 ms threshold docs/12 set
for calling the gap a bench artefact, so the item stays open. It grows about
2.5 ms per additional crop over a fixed floor of roughly 13 ms — which is crop
letterboxing and normalisation, work `_identify` deliberately excludes from its
own timing, plus one JPEG decode and one illuminant estimate per frame.

### The session-switch experiment

The decomposition cannot separate *"two graphs cost more than one"* from
*"alternating between two sessions is itself expensive"*, and those call for
completely different responses. So the number of **sessions** was varied while
holding the graph and the arithmetic fixed:

- **A** one session, called twice
- **B** two sessions of the **same graph**, alternating
- **C** the validator then the identifier

**B − A is the cost of switching**, because only the session count changed.

| configuration | A | B | C | switching (B−A) |
|---|---:|---:|---:|---:|
| **default** | 29.60 | 66.52 | 57.08 | **+36.92 ms** |
| `SBR_ORT_SPINNING=0` | 44.17 | 44.04 | 34.54 | −0.13 ms |
| `SBR_ORT_SHARED_POOL=1` | 33.03 | 33.00 | **26.28** | −0.03 ms |

p50 over 40 iterations, 10 warm-up, inside the same 2-vCPU container.

**The hypothesis is confirmed and the cause is exact.** Two onnxruntime sessions
get two intra-op thread pools by default, and both spin while idle — four
threads contending for two cores, so the idle model's pool burns the running
model's cycles. Sharing one pool collapses switching to nothing and takes the
two-graph case from **57.08 ms to 26.28 ms**.

Note what A does under `no_spinning`: it gets *worse*, 29.60 → 44.17. Spinning
genuinely helps a single hot session, which is why it is onnxruntime's default
and why this service — which is never a single hot session — is the wrong shape
for that default. The shared pool keeps A at 33.03 and still fixes C, which is
why it is the configuration carried forward rather than `no_spinning`.

---

## P8a – The validator at 384 px

Exported by `probe_artefact.py` at 384, everything else identical.

A control was necessary and is worth naming: `val384` would otherwise have
differed from the baseline in **two** ways — input size *and* which machine
exported the graph, since the baseline's validator came from the Kaggle probe
kernel. `val448local` is the same architecture at the same 448, exported by the
same local toolchain, so `baseline → val448local` measures the toolchain and
`val448local → val384` measures the input size.

**The accuracy cost of 384 is UNMEASURED and is not claimed.** Latency on an
untrained graph is sound; recall on small distant bins is a different question,
it needs a trained model, and adopting 384 means retraining at 384.

---

## P8c – Capping crops at three

Reported at six bins only. It cannot move the one-bin number — there is nothing
to cap — and the gate is stated at one bin.

**What the cap actually costs has to travel with it.** docs/05 § 7 and
`settings.py` both said the remainder is *"deferred to the next frame"*. **It is
not, and never was.** `pipeline.run` truncates and never revisits, so a box past
the cap is drawn with `form_factor: null` and no colour: at the six-container
bank the PRD calls a normal input, a cap of three leaves three containers
permanently unidentified. Both documents are corrected. Deferral is buildable —
the client's result lock at three stable frames is the natural place for it —
and it is product work, not this probe's.

---

## Results, part one: the serial matrix, and why it is not admissible

Seven configurations at one bin, three repeats each, bracketed by a baseline at
both ends, in a randomised order. p95 in milliseconds, median of three repeats.

| run | started | verdict | L4 | L5 | L6 | L7 | L8 | L9 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| baseline-a | 22:30 | **7** | 147 | 177 | 203 | 226 | 255 | 287 |
| val384 | 22:43 | 7 | 137 | 166 | 198 | 211 | 248 | 268 |
| sharedpool | 22:56 | 8 | 148 | 180 | 197 | 228 | 245 | 277 |
| combined | 23:08 | 8 | 139 | 169 | 187 | 214 | 238 | 253 |
| nospin | 23:21 | 7 | 158 | 188 | 228 | 240 | 276 | 317 |
| val448local | 23:35 | 4 | 221 | 251 | 297 | 418 | 470 | 524 |
| **baseline-b** | 23:48 | **4** | 227 | 260 | 296 | 406 | 474 | 511 |

**The bracket failed the block, and that is the result.** The identical baseline
configuration measured **7 at 22:30 and 4 at 23:48**. The curve is flat for five
runs and then steps ~50 % worse between 23:21 and 23:35 and stays there; the last
two runs agree closely with each other and disagree with everything before.

docs/12 stated the rule in advance: *a candidate delta smaller than the
baseline-to-baseline drift is rejected, whatever its sign.* The drift is **3
concurrent scanners** and every candidate effect on offer is **1**. So **no row
of that table is admissible**, including the ones that look favourable.

Two things follow that are worth more than the table.

**`val448local`'s 4 is not a toolchain effect.** It ran immediately before
`baseline-b` and matches it almost exactly, so it measures the disturbance and
not the graph. An earlier reading of it as evidence that the export toolchain
costs three scanners is **withdrawn**; nothing here says anything about the
toolchain either way.

**The disturbance was the machine this was run from.** Host CPU sat at ~50 %
with the agent tooling as the largest consumer. `docker run --cpus 2` is a cgroup
**ceiling, not a floor** — under host contention the container gets less than its
quota — and the service's own `ms` rose from a flat 33 ms in the quiet window to
46–55 ms in the noisy one, which is the container being starved rather than
anything about the service.

**So the absolute concurrency ceiling is not measurable on this host**, and that
applies backwards as well as forwards: the **4** recorded on 2026-08-17 comes
from the same protocol on the same laptop and is not a measured ceiling either.

Two baselines is an **observed spread of three**, not an error bar. This probe
was not designed to estimate the variance of the measurement and does not; it
was designed to detect whether the block was admissible, and it detected that
it was not.

## Results, part two: the paired comparison, which is admissible

The fix for drift larger than the effect is not more repeats — they all sit on
the same side of the drift. It is to shrink the gap between the things being
compared. `matrix.py --paired` alternates two configurations **ABBA**, so each
arm is measured about four minutes from its partner instead of eighty, and any
ordering effect cancels between cycles.

Four cycles, `baseline` against `sharedpool`, one bin, deliberately run while the
host was still in its degraded state — because a comparison that only works on a
quiet machine is not much of a comparison.

Median paired difference in p95, `sharedpool − baseline`:

| level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Δ p95 (ms)** | −130 | −54 | −78 | −96 | −123 | −122 | −127 | −115 |
| favouring sharedpool | 4/4 | 3/4 | 4/4 | 4/4 | 4/4 | 4/4 | 3/4 | 3/4 |

**Every one of the four cycles favours the shared pool at most levels, median
−105 ms**, and the direction holds in both ABBA orderings. The right unit of
replication is the **cycle, of which there are four** — the twelve levels
inside one cycle share a container and a moment, so they are correlated and
the raw 41-of-48 count overstates the independent evidence. This is a
consistent direction and an indicative magnitude, not a production-sized
effect estimate. The absolute numbers in these cycles are
poor — the host was busy — and that is exactly the point: the *difference*
survives conditions that destroy the *level*.

## The verdict

**P8a — the validator at 384: not established.** It sat inside the drift in the
serial block and was never given a paired run. Its accuracy cost remains
unmeasured regardless, so nothing about it is adoptable today.

**P8b — the missing milliseconds: found, explained and fixed.** `other_server` is
15.3 ms at one bin, over the 10 ms threshold, so the gap is real in the service
and not only in the bench. Its cause is **two onnxruntime sessions with two
spinning intra-op thread pools on two cores**: switching costs **+36.9 ms**, and
one shared pool removes it, taking the two-graph call from **57.1 ms to 26.3 ms**
and p95 under load down by a median of **105 ms**. This is the recovery of the
three, and it is a one-line configuration change.

**P8c — capping crops at three: not measured.** The six-bin scene was abandoned
when the one-bin block's own control showed the design could not resolve it. The
hook that made it measurable at all is fixed and tested, so the run is cheap
whenever there is a host worth running it on. What is already established without
a measurement is that the cap **costs coverage** — the remainder is not deferred,
it is simply unidentified.

**The gate: not established, in either direction.**

| | |
|---|---|
| gate | **≥ 10 concurrent scanners at one bin** |
| highest figure observed, any configuration | **8** |
| the same baseline, twice in one evening | **7, then 4** |
| verdict | **not established either way** — nothing was observed at 10, and no admissible absolute measurement exists |

docs/12's combined-run rule reads an absolute number off this host, and **this
host cannot supply one**. So the rule does not fire in either direction: the
recoveries are real and their size is established at the graph level, and whether
they reach ten is **unresolved**.

That is not a stalemate, it is a requirement: **a controlled 2-vCPU x86 host
that is not also running the tooling.** The earlier plan treated that as
something to do only if the ARM result reached ten. It is now the only way to get
any absolute number at all, which makes it the next step rather than a
contingency.

---

## Corrections after review

Four claims in the first draft of this probe were wrong or overstated, and they
are listed rather than quietly edited, because a probe that hides its own
corrections is worth less than one that has none.

**"No metadata field can request a GPU type" — wrong.** `machine_shape` is read
by `kernels_push`, and `kaggle kernels push --accelerator` sets the same field;
the accepted values are `NvidiaTeslaT4` and `NvidiaTeslaP100`. So the remedy for
the torch/GPU mismatch is to **ask for the T4**, not to re-dispatch until lucky.
Every GPU kernel here now does, and a test pins it.

**"Refuses in seconds before any data is pulled" — not yet true when written,
and "seconds" was wrong anyway.** `require_usable_gpu()` sat *after*
`download_dataset` and `build_yolo_tree` in both training kernels, so a P100
allocation still cost the 37 913-file pull before anything said so. Moved, and
a test now asserts the guard precedes the pull. It still follows dependency
installation, so the claim is now *before the pool is pulled* with no duration
attached to it.

**"The gate fails" — overstated.** It has not passed, and nothing was ever
observed at ten. But the 4 it was recorded as failing on is a number this probe
showed the host cannot sustain, so the kill criterion is **unresolved**, not
fired. Relatedly, *observed drift of 3* is what two baselines showed; calling it
`±3` implies an error bound this experiment was never designed to estimate.

**"41 of 48 paired comparisons" — an overcount of independent evidence.** The
arithmetic is right, but twelve concurrency levels inside one cycle share a
container and a moment. The unit of replication is the **cycle, of which there
are four**, and the result is a consistent direction with an indicative
magnitude — not a production-sized effect estimate.

One design decision changed with them: the shared thread pool is **conditional
on two graphs being loaded** rather than unconditionally on. The same experiment
that measured +31 ms for two sessions measured −11 % for one, and the service is
single-session until the identifier exists.

---

## What this host may not conclude

The measuring host is an ARM laptop under a cgroup quota. It can screen
candidates and establish within-host deltas honestly. **It cannot pronounce on
Cloud Run**, which is x86_64 — and the 4-versus-7 baseline difference above is
the concrete reason to insist on that rather than a formality.

So a combined result that reaches ten here reads as *"capacity recovery
demonstrated on the ARM proxy; production gate pending x86 confirmation"*, and
the gate stays open until a controlled 2-vCPU x86 host says the same. The gate
remains stated as **10**, and is never restated as its measured value.
