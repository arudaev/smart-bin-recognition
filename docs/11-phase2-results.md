# 11 – Phase 2 results (v1)

> Every number here names the split it was measured on and the hardware it
> ran on. A metric that was not measured says so; nothing is interpolated,
> carried over from another split, or omitted to make a table look full.

Generated 2026-08-13 by `ml/scripts/evaluate.py`.

## The phase-2 gate

docs/07 states it: **validator ≤ 50 ms @ 448 and identifier ≤ 25 ms per crop
on service CPU, and ≥ 10 concurrent scanners on the free tier.**

| model | measured p50 | budget | verdict |
|---|---|---|---|
| validator @ 448 | **26.6 – 33.0 ms** | ≤ 50 ms | **within budget**, ~40 % headroom |
| identifier @ 320, per crop | **17.4 – 21.7 ms** | ≤ 25 ms | **within budget** |
| concurrent scanners, 1 bin | **4 ± 3** (see below) | ≥ 10 | **not met** |
| concurrent scanners, 6 bins | **1** (measured) | – | the PRD's normal input |

> **The concurrency row carries ±3 as of 2026-08-18, and the uncertainty is the
> host.** [Probe P8](research/probes/P8-recovery-measurements.md) bracketed a
> measurement block with the same baseline at both ends and got **7 at 22:30 and
> 4 at 23:48**. `docker run --cpus 2` is a cgroup ceiling rather than a floor,
> and the laptop was also running the development tooling at ~50 % CPU, so the
> container was being starved — the service's own `ms` moved from a flat 33 ms
> to 46–55 ms. **No absolute concurrency figure from this project is better than
> ±3 until a controlled 2-vCPU x86 host produces one.** The highest figure ever
> observed under any configuration is 8, so the gate is not met either way.

**The concurrency figure is no longer a prediction.** The load test ran on
2026-08-17 against `docker run --cpus 2`, ramping virtual scanners at 3 fps in
strict request-response until p95 crossed 250 ms:

| scanners | p50 | p95 | throughput | ladder |
|---:|---:|---:|---:|---|
| 1 | 96 ms | 111 ms | 2.3 fps | – |
| 2 | 90 ms | 143 ms | 4.6 fps | – |
| 3 | 100 ms | 170 ms | 6.9 fps | – |
| **4** | **106 ms** | **219 ms** | **9.2 fps** | – |
| 5 | 99 ms | 257 ms | 11.5 fps | rung 1 |
| 6 | 126 ms | 317 ms | 13.7 fps | rung 1 |
| 8 | 437 ms | 470 ms | 14.2 fps | rung 1 |
| 10 | 551 ms | 595 ms | 15.8 fps | rung 2 |
| 12 | 660 ms | 710 ms | 16.0 fps | rung 2 |

Load-test hardware: **`docker run --cpus 2` (cgroup quota 2.0), `linux/arm64`
native, Snapdragon X1E80100 @ 3.40 GHz, onnxruntime 1.28.0, Python 3.11.15.**
`representative: false` — **Cloud Run is x86_64**, so this is a second proxy,
not the serving tier. It is a *pinned* proxy, which the Kaggle kernel was not,
and its measured throughput of 15.8–16.0 frames/second sits inside the corrected
13–15 prediction. The Snapdragon core is fast for its class, so a shared Cloud
Run vCPU is more likely to give fewer scanners than more.

Artefacts: stock COCO YOLO11n @ 448 and YOLO11s-cls @ 320, int8, **untrained on
this project's data** and served with `SBR_ALLOW_UNGATED=1`. Sound for cost,
which depends on architecture and input shape; meaningless for accuracy, which
is not measured here.

Latency hardware: **Kaggle CPU kernel, Intel Xeon @ 2.20 GHz, onnxruntime
pinned to 2 of 4 vCPU, onnxruntime 1.28.0.** `representative: false` – a
proxy for a service container, not one, and about **25 % noisy** between
two runs six minutes apart. Both runs are reported as a range for that
reason.

Measured 2026-08-16 by
[probe P4](research/probes/P4-multi-bin-cost-curve.md), on **stock COCO
architectures untrained on this project's data**. That is sound for
latency, which depends on architecture and input shape, and meaningless
for accuracy, which is not measured there.

**The two model budgets pass and the thing they were supposed to buy does
not.** The concurrency figure is derived from the measured frame cost, and
it is out by a factor of two against the gate. Two contributing findings,
both in P4:

- docs/05 § 3's arithmetic **double-counted the vCPUs** – it divided 2 vCPU
  by a latency that had already been measured on both of them. Capacity is
  ~13–15 frames/second, not 30.
- a frame costs **15–40 ms more than its two graphs**, most likely from
  alternating between two onnxruntime sessions. At one bin that is a third
  of the frame and nothing had budgeted for it.

A third finding, and the load test is the only thing that could have produced
it: **the degradation ladder had never been reachable.** Inference blocked the
event loop, so requests queued in the ASGI layer instead of arriving at the load
shedder — twelve concurrent scanners gave `peak_depth: 1` and not one rung
fired. Every rung test passed throughout, because each forces its threshold to
zero and fires on the first request; they checked the shedder's arithmetic and
none checked that it is ever handed a queue. The service degraded by getting
slower and saying nothing, which is the one behaviour docs/05 § 3 rules out by
name. Fixed, and the fix is why the table above shows rungs firing at all.

Two notes on how this page should be read:

- **Latency did not need a trained model**, and that is why the table
  above is no longer empty. ONNX cost depends on architecture and input
  shape rather than on weights, so P4 and P5 filled it from stock
  exports while the identifier is still blocked on the human pass.
- **The concurrency figure is a range over scene complexity.** One bin per
  frame is the easy end and measures 4; a bank of six — which the PRD calls
  a normal input — measures **1**. Quoting the single number 4 without the
  scene it assumes is the same mistake as quoting 10 was.

## Architecture

[Probe P5](research/probes/P5-validator-architecture.md), same hardware.

| candidate | p50 @ 448 | budget | verdict |
|---|---|---|---|
| YOLO11n (incumbent) | 26.6 – 33.0 ms | ≤ 50 ms | fits |
| RF-DETR-nano | **475.3 ms** | ≤ 50 ms | **9.5× over** |
| D-FINE-N | – | ≤ 50 ms | **not evaluated** – the session will not open |

**YOLO11n stays.** 475 ms is not a near miss and no amount of tuning
closes a 9.5× gap. D-FINE-N is recorded as *not evaluated* rather than
*did not fit*, because a candidate that never ran has not answered the
question and writing it down as a failure would be manufacturing evidence
for a convenient conclusion.

The D-FINE-N gap was re-examined on 2026-08-17 and is now precise rather than
summarised: the exported graph fails at **session creation** with
`NOT_IMPLEMENTED: Could not find an implementation for Cos(7)` at
`/model/encoder/aifi.0/position_embedding/Cos`, reproduced on onnxruntime 1.26.0
on a different machine from the one that exported it. There is no latency to
measure on any host, and the cause is an export-time type choice in the AIFI
positional encoding rather than anything about the architecture's speed. See
[P5](research/probes/P5-validator-architecture.md).

### Targets, as distinct from gates

A gate is arithmetic the free tier depends on and it fails the build. A
target is how good the model is and it is reported. The sidecar now
carries both, in three categories — met, missed, and **unmeasurable**:

| target | role | status |
|---|---|---|
| `min_recall_heldout_city` ≥ 0.97 | validator | **unmeasurable** – no subset carries a second `region_id` |
| `min_precision_on_negatives` ≥ 0.97 | validator | _not measured_ – the run has not completed |
| `min_formfactor_acc_heldout_city` ≥ 0.85 | identifier | **unmeasurable** – same reason |

*Unmeasurable* is not *missed*. It means the evidence does not exist,
and it is reported rather than omitted so that the generalisation
question this phase exists to answer cannot be quietly dropped.

## The validator run, 2026-08-16: dispatched, and it died

Recorded because a run that failed is a result, and because the next person to
try this needs to know how far it got rather than starting from nothing.

`dispatch.py push validator --version 1` pushed cleanly to
`hlexnc/sbr-train-validator`. The kernel then:

- pulled the pinned pool — 77 890 files — and built the dataset;
- wrote `dataset/composition.json`: **18 954 images**, split 13 265 train /
  2 823 val / 2 866 test, from 370 legacy + 17 474 negatives + 1 110 Open Images;
- wrote `runs/validator/args.yaml`, so Ultralytics started: `yolo11n.pt`,
  80 epochs, batch 32, imgsz 448, AdamW, cosine LR, seed 42, `device: '0'`;
- produced **no weights** — `runs/validator/weights/` is empty;
- ended with status `ERROR`, an **empty log**, and an empty `failureMessage`.

GPU was enabled in the kernel metadata, so that is not it. Kaggle returned no
diagnostic at all through the API, and a re-push of the much cheaper CPU bench
kernel failed the same way — errored, no log.

### What the ladder found, 2026-08-17

That last inference — *"which points at something about the account or the
platform"* — **was wrong, and the way it was wrong is worth keeping.** Two
kernels failed with the same status, and a shared status was read as a shared
cause. A six-rung ladder, each rung changing exactly one thing
(`ml/kaggle/smoke_*`, dispatched by `dispatch.py`), separated them:

| Rung | Changes | Result |
|---|---|---|
| `smoke_bare` | nothing: no bundle, no dataset, no GPU | **COMPLETE** — the account and the platform are fine |
| `smoke_plain` | + the injected project bundle | **ERROR**, and *with a full traceback* |
| `smoke_secrets` | + the attached secrets dataset | **COMPLETE** — token found, 37 chars, `hf_` prefix |
| `smoke_usersecret` | a Kaggle Secret instead of the dataset | **COMPLETE**, and the secret is **not reachable** |

Four things follow, and only one of them was suspected before.

**1. The bundle layout was broken, and had been all along.**
`smoke_plain` died on `FileNotFoundError:
/kaggle/working/data/taxonomy/waste-streams.json`. `sbr.taxonomy` resolves the
repo root as `parents[3]` of its own file, and the bundle unpacked `src/` and
`data/taxonomy` as *siblings*, which put that one directory too high. It stayed
invisible because `load_config` resolved correctly from the same tree and the
only kernel that ever completed — `probe_latency` — never calls
`load_taxonomy`. **Every kernel that does was failing**, which includes
`train_identifier`, whose `classes_from_taxonomy: true` makes it the first thing
that run would have touched. Fixed: the bundle now mirrors the repository, the
same way `service/Dockerfile` does and for the same reason, and
`test_kernels.py` builds the real bundle and checks the invariant on the
unpacked tree.

**2. The attached secrets dataset was never the cause.** It was the one factor
the two failing kernels shared and the passing one did not, which made it the
leading hypothesis. It mounts, it carries the token, and the kernel that uses it
completes.

**3. A Kaggle Secret is not an alternative, and now that is measured rather than
believed.** `kaggle_secrets` imports inside a batch kernel and then
`get_secret` fails with `ConnectionError: Connection error trying to communicate
with service.` The attached dataset stays the way the token reaches an
API-pushed kernel.

**4. `bench_latency`'s failure was correct behaviour misread as a symptom.** It
ends with `raise SystemExit("no artefacts at v1 to measure - train something
first")`, and no model exists, so it refuses — exactly as designed. Re-pushed on
2026-08-17 it errored again, **with an empty log**, on an account that had
returned full tracebacks minutes earlier. So *"errored with no log"* is how a
deliberate `SystemExit` surfaces through the Kaggle API; it is not evidence of
anything being wrong.

### And then the validator's own cause, 2026-08-18

None of the four findings above explained it — the validator's config sets
`classes_from_taxonomy: false`, so it never touched the broken bundle path. The
GPU rung found it:

```
torch 2.10.0+cu128, cuda available: True
Tesla P100-PCIE-16GB with CUDA capability sm_60 is not compatible with the
current PyTorch installation. The current PyTorch install supports CUDA
capabilities sm_70 sm_75 sm_80 sm_86 sm_90 sm_100 sm_120.
```

**The Kaggle image ships a torch that cannot use the GPU Kaggle allocated.**
`torch.cuda.is_available()` returns `True`, so every availability check passes;
the failure arrives at the **first tensor move**, inside Ultralytics, after the
pool has been pulled, the dataset built and `args.yaml` written. That is the
2026-08-16 signature exactly — as far as `args.yaml`, then no weights.

**The first explanation was wrong and is worth recording as such.** It looked
like `pip install ultralytics` had replaced the image's torch, and the installs
were changed to `--no-deps` on that basis. The next run reported the same torch.
A rung that installs **nothing at all** settled it:

| `smoke_gpu` | |
|---|---|
| `installed_anything` | `false` |
| shipped | `torch==2.10.0+cu128`, `torchvision==0.25.0+cu128` |
| allocated | `Tesla P100-PCIE-16GB`, `sm_60` |
| verdict | the image ships a torch that cannot use this GPU |

**Nothing in this repository caused it and nothing in this repository fixes
it.** Kaggle allocates P100 or T4 and the kernel metadata schema has no field to
ask for one, so the remedy is to re-dispatch until a **T4 (sm_75)** is
allocated. What the repo does now is refuse in seconds with the reason
(`sbr.utils.gpu.require_usable_gpu`) rather than dying an hour in with no log —
and the smoke rung reports and continues on CPU, which is how a one-epoch run
completed and produced a checkpoint on 2026-08-18.

So the validator run is **unblocked in the sense that matters** — the failure is
understood, detected and survivable — and **still not done**, because it needs a
GPU allocation this project does not control.

Two things follow. The ship gate's latency half still has no
service-hardware measurement, because `gate.py` needs the bench kernel. And
`docs/07`'s phase-2 checklist item "first training run on a Kaggle kernel"
remains open, now with a known failure mode rather than as untried work.

One thing in the output deserves its own look: `composition.json` reports
`background_images: 0` and `negative_ratio: 0.0` while `per_pool.negatives` is
17 474, and `positives: 18 954` is the sum of *all three* pools. If that is real
rather than a reporting bug, the validator would train with no negatives at all
— and `min_precision_on_negatives ≥ 0.97` is one of its targets.

## What the models were trained on

_The validator run has not completed._

The split is **group-aware by capture cluster** – frames of one bin in one
visit share a split – and never random. docs/08 § 7.3's 0.9873 came from a
random 20 % of one capture session and is not comparable to anything below.

## Validator

| metric | split | value |
|---|---|---|
| mAP@0.5 | test (group-aware) | _not measured_ |
| mAP@0.5:0.95 | test | _not measured_ |
| precision | test | _not measured_ |
| recall | test | _not measured_ |
| mAP@0.5 | **held-out region** | _not measured_ |
| recall | **held-out region** | _not measured_ |

### Recall by bins per frame

docs/04 § 5 commits to this so a model that only works on one big centred
bin cannot hide behind an aggregate.

Not measured – the validator run has not completed.

Note that the legacy subset alone cannot fill the `4+` row: it has **no frame with four or more bins**.


### Precision on the negative corpus

Not measured – the validator run has not completed.


## Identifier

| metric | split | value |
|---|---|---|
| top-1 | test (group-aware) | _not measured_ |
| top-5 | test | _not measured_ |
| unknown rate | test | _not measured_ |
| accuracy when answering | test | _not measured_ |

_The identifier run has not completed._ It is blocked on the human
adjudication pass: the legacy labels are waste **streams**, and a stream
does not determine a shape, so `ml/scripts/adjudicate.py` has to run
before there is anything to train on.

## Novelty precision

The kill criterion in docs/07 is **< 0.5**, and the whole improvement loop
rests on the validator/identifier disagreement being a trustworthy signal.

**_not measured_.** It needs both models plus a human verdict on whether each
flagged frame was genuinely a new bin type, so it cannot be computed until
the identifier exists and its flags have been adjudicated.

## Numbers this project does not quote

- the predecessor's **95.2 % mAP@0.5** – a random split of one week of
  photographs in one city;
- the **0.9873** independent re-validation (docs/08 § 7.3) – same split, so
  it reproduces the memorisation rather than refuting it.

Both are in-distribution. Neither is this project's baseline.

