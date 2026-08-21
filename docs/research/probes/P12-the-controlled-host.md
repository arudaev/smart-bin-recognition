# P12 – The controlled host: the phase-2 gate, measured

*Run 2026-08-21 on a GCE `n2-standard-4` in `europe-west3-a`, created for the
measurement and destroyed after. Raw data:
[`data/P12-gce-latency.json`](data/P12-gce-latency.json),
[`data/P12-gce-loadtest-1crop.json`](data/P12-gce-loadtest-1crop.json),
[`data/P12-gce-loadtest-6crop.json`](data/P12-gce-loadtest-6crop.json),
[`data/P12-gce-loadtest-no-crops.json`](data/P12-gce-loadtest-no-crops.json).
Harness: `service/deploy/measure-on-gce.sh`.*

**Question.** [P8](P8-recovery-measurements.md) established that the development
laptop cannot hold a concurrency figure still — the identical baseline gave **7
at 22:30 and 4 at 23:48** — and concluded that *"the next step is a host, not
another recovery"*. This is that host.

**What made it admissible.** The service is pinned to **CPUs 0–1** with
`--cpus 2 --cpuset-cpus 0,1`, which is the two vCPU docs/05 § 3 is arithmetic
about. The other two cores exist so the **load-test client** has somewhere to
run that is not the service's. The old protocol worked because the Snapdragon
had twelve cores and the client had ten free; putting the client on the
service's two would have reproduced P8's contention deliberately. The CPU
platform is pinned to Intel Cascade Lake, because P9-versus-P10 measured the
identical graph 31 % apart on two Kaggle allocations.

**`representative: true`**, by the maintainer's decision on 2026-08-21: a
2-vCPU x86 box running the same amd64 image counts as the service for the
purpose of these budgets. That is a judgement about what the budget means and it
is recorded as one.

---

## The verdict

| half of the gate | budget | measured | verdict |
|---|---|---|---|
| validator @ 448 | ≤ 50 ms | **18.3 ms** p50, 25.2 ms p95 | **PASS**, 63 % headroom |
| identifier @ 320 per crop | ≤ 25 ms | **9.9 ms** p50, 14.9 ms p95 | **PASS**, 60 % headroom |
| **concurrent scanners, 1 bin** | **≥ 10** | **5** | **FAIL** |
| concurrent scanners, 6 bins | – | **2** | the PRD's normal input |

**Both latency halves pass on hardware that counts, and the concurrency half
fails by a factor of two.** This is the first admissible absolute concurrency
figure this project has ever had.

## The curves

Three repeats of a fourteen-level ramp, virtual scanners at 3 fps in strict
request-response, p95 budget 250 ms. A level passes only if it passed in every
repeat, and the verdict is the largest monotonic passing prefix.

**One crop per frame — `SBR_FORCE_CROPS=1`:**

| scanners | p95 per repeat (ms) | worst | server ms | throughput |
|---:|---|---:|---:|---:|
| 1 | 54.6 · 52.3 · 52.8 | 54.6 | 48 | 2.2 fps |
| 2 | 108.4 · 102.2 · 104.2 | 108.4 | 49 | 4.4 fps |
| 3 | 154.3 · 150.0 · 152.1 | 154.3 | 49 | 6.7 fps |
| 4 | 206.1 · 198.9 · 201.6 | 206.1 | 49 | 8.8 fps |
| **5** | **249.5 · 244.6 · 244.8** | **249.5** | 49 | 11.0 fps |
| 6 | 293.2 · 290.7 · 293.3 | 293.3 | 49 | 13.2 fps |

**Six crops per frame — `SBR_FORCE_CROPS=6`:**

| scanners | worst p95 | server ms | throughput |
|---:|---:|---:|---:|
| 1 | 115.3 | 109 | 2.2 fps |
| **2** | **229.9** | 106 | 4.4 fps |
| 3 | 334.9 | 107 | 6.6 fps |

**The host is quiet, and the numbers say so.** Across three repeats the worst
spread at any level is about 3 ms — against a host whose identical baseline
moved by three whole scanners in one evening. Level 5 lands at 249.5 ms against
a 250 ms budget, which is uncomfortably exact and is why the repeats matter: all
three passed.

## P4's arithmetic was right

This is worth stating because the derivation was distrusted for good reason —
it came from a shared Kaggle box and it had already been wrong once.

| | P4 predicted | P12 measured |
|---|---|---|
| 1 bin per frame | **4.3 – 5.1** | **5** |
| 6 bins per frame | **1.8 – 2.2** | **2** |

Both inside the predicted range. The corrected cost model — the one that stopped
double-counting the vCPUs — describes this service accurately.

The laptop's withdrawn figures were **4** and **1**. They were not wildly wrong
either; they were simply not reproducible, which is a different criticism and
the one P8 actually made.

## The first run measured an empty frame, and that is recorded rather than dropped

The first pass through this harness reported **10 concurrent scanners at one bin
and 10 at six**. Both numbers are wrong, and the way they are wrong is
instructive.

`run.py --bins N` is a **report label**. Its own help says so — *"for the report
only — set `SBR_FORCE_CROPS` on the CONTAINER to make it true"* — and the
harness had not set it. The client sends smooth noise, justified in its
docstring by *"the validator here is untrained, so what a real bin looks like
changes nothing about the cost"*. **That was true of a stock COCO graph and is
false now**: against the trained validator, noise contains no bin, nothing is
detected, no crop is cut, and the identifier never runs.

So both halves measured a **validator-only frame** and labelled them "1 bin" and
"6 bins" — and came back **identical to within 2 ms at every one of fourteen
levels**, which is what gave it away. That result is kept, in
[`data/P12-gce-loadtest-no-crops.json`](data/P12-gce-loadtest-no-crops.json),
because it is a real measurement of something worth knowing:

> **Validator-only, no crops: 10 concurrent scanners.** A frame that the
> validator rejects — which is most frames a real scanner sends, since it is
> pointed at the ground half the time — costs 24 ms and supports ten people.
> The gate's frame is the expensive one.

## What is left, and what it would have to buy

The shed ladder fires as designed: rung 1 (drop to 2 fps) from level 5, rung 2
(tap-to-scan) from level 9, zero errors and zero 503s throughout. **And
[P8b](P8-recovery-measurements.md)'s shared onnxruntime thread pool was already
active** — `ort_shared_pool_effective: true` in the health of both runs — so 5
is the figure *with* the one recovery that was ever shown to work.

To reach ten scanners at one bin the frame would have to cost **~25 ms instead
of 49**. Of that 49, the validator is 18.3 ms and the identifier 9.9 ms; the
remaining ~21 ms is decode, letterbox, colour and the wire. Halving the total
is not something the two remaining unmeasured recoveries can plausibly do:

- **validator at 384 px** — P8a could not distinguish it from drift on the
  laptop; on this host it could be measured properly, and at best it takes a
  third off 18.3 ms, or ~6 ms of 49;
- **capping crops at three** — does nothing at one bin per frame, which is the
  level the gate is stated at.

**So the gate fails, and the honest reading is that it fails on compute rather
than on tuning.** Whether that means more vCPU, a smaller validator, or a
revised gate is a decision this probe does not take. docs/07's kill criterion
asks whether it *"cannot be recovered"*; what P12 establishes is that it is not
recoverable by anything currently on the list.

## Hardware, stated in full

```
GCE n2-standard-4, europe-west3-a, --min-cpu-platform "Intel Cascade Lake"
Intel(R) Xeon(R) CPU @ 2.80GHz, 4 vCPU
service: docker --cpus 2 --cpuset-cpus 0,1   client: --cpuset-cpus 2,3
Container-Optimized OS, onnxruntime 1.29.0, SBR_INTRA_OP_THREADS=2
image  europe-west3-docker.pkg.dev/smart-bin-recognition/sbr/detect
       @sha256:7399db5724405430752e2b1d82f31159b83c8405e2a69154aa110e63e067fa8a
representative: true
```

**The image predates the double-softmax fix** (`service/pipeline.py`), which
changes a three-element numpy operation and no cost. Latency was measured five
times per role and the **slowest** repeat is the one reported — the spread was
18.02–18.30 ms for the validator and 9.74–9.91 ms for the identifier.

**Cost.** The VM was created, measured on, and deleted on every exit path. About
90 minutes of `n2-standard-4` at USD 0.250248/hour, plus a 20 GiB balanced boot
disk — roughly **USD 0.38**, against a 2-hour cap approved in advance. No
instance and no disk survives; both were confirmed empty afterwards.
