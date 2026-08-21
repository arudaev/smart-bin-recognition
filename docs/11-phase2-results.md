# 11 – Phase 2 results (v1)

> Every number here names the split it was measured on and the hardware it
> ran on. A metric that was not measured says so; nothing is interpolated,
> carried over from another split, or omitted to make a table look full.

Generated 2026-08-13 by `ml/scripts/evaluate.py`.

## The phase-2 gate

docs/07 states it: **validator ≤ 50 ms @ 448 and identifier ≤ 25 ms per crop
on service CPU, and ≥ 10 concurrent scanners on the free tier.**

| half of the gate | budget | measured | verdict |
|---|---|---|---|
| validator @ 448 | ≤ 50 ms | **18.3 ms** p50, 21.3 ms p95 | **PASS**, 63 % headroom |
| identifier @ 320, per crop | ≤ 25 ms | **9.9 ms** p50, 11.4 ms p95 | **PASS**, 60 % headroom |
| **concurrent scanners, 1 bin** | **≥ 10** | **5** | **FAIL**, by a factor of two |
| concurrent scanners, 6 bins | – | **2** | the PRD's normal input |

**Measured 2026-08-21 on a controlled host, and this is the first admissible
absolute concurrency figure this project has had.** GCE `n2-standard-4`,
`europe-west3-a`, CPU platform pinned to Intel Cascade Lake; the service pinned
to CPUs 0–1 with `--cpus 2 --cpuset-cpus 0,1`, the load-test client on CPUs 2–3
so it cannot steal the cores the number is about; onnxruntime 1.29.0;
**`representative: true`** by the maintainer's decision that a 2-vCPU x86 box
running the same amd64 image counts as the service for these budgets. Created
for the measurement and destroyed after. Full account:
[P12](research/probes/P12-the-controlled-host.md).

**Two latency halves pass on hardware that counts. The concurrency half fails.**

The host is quiet and the numbers show it: across three repeats of a fourteen-
level ramp the worst spread at any level is about 3 ms, against a laptop whose
identical baseline moved by three whole scanners in one evening.

**P4's corrected arithmetic was right.** It predicted 4.3–5.1 scanners at one
bin and 1.8–2.2 at six; measured, it is **5** and **2**. The withdrawn laptop
figures were 4 and 1 — not wildly wrong, simply not reproducible, which is the
criticism [P8](research/probes/P8-recovery-measurements.md) actually made.

**The frame costs 49 ms and would have to cost ~25 ms.** The validator is
18.3 ms of that and the identifier 9.9 ms; the remaining ~21 ms is decode,
letterbox, colour and the wire. [P8b](research/probes/P8-recovery-measurements.md)'s
shared onnxruntime thread pool — the one recovery ever shown to work — was
**already active** for these runs, so 5 is the figure with it applied. Of the
two recoveries still unmeasured, 384 px takes at best ~6 ms off 49, and capping
crops does nothing at all at one bin per frame, which is the level the gate is
stated at. **The gate fails on compute rather than on tuning**, and whether that
means more vCPU, a smaller validator or a revised gate is not this document's
decision.

> **One figure here is a measurement of the wrong thing, kept because it is
> worth knowing.** The first pass through the harness reported **10 concurrent
> scanners** — because `run.py --bins N` is a report label and
> `SBR_FORCE_CROPS` had not been set on the container, so the client's synthetic
> noise produced no detections, no crops, and no identifier work at all. Both
> halves measured a **validator-only frame** and came back identical to within
> 2 ms at every level, which is what exposed it. As a fact about validator-only
> frames it stands: **a frame the validator rejects costs 24 ms and supports ten
> concurrent scanners.** Most frames a real scanner sends are that frame. The
> gate's frame is the expensive one.

### The superseded history

Everything below this line was the state of knowledge before 2026-08-21 and is
kept because the reasoning is still the right reasoning.

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
| `min_precision_on_negatives` ≥ 0.97 | validator | **MET, 0.9793** – measured 2026-08-18 on 2 662 background frames |
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
it.** What the repo *can* do is stop asking for the wrong machine and stop
paying for the discovery:

- **Ask for the T4 by name — and it works.** `machine_shape: "NvidiaTeslaT4"`
  in `kernel-metadata.json` is read by `kernels_push`, and
  `kaggle kernels push --accelerator` sets the same field. Re-running the
  no-install rung with it set returned:

  ```
  accelerator: Tesla T4, capability sm_75, torch 2.10.0+cu128 - usable
  verdict: "the image's torch can use the GPU it was given"
  ```

  Same image, same torch, allocation honoured. **The training path is
  unblocked**, and every GPU kernel here requests a T4 with a test pinning it.
  An earlier draft said no such field existed and that the remedy was to
  re-dispatch until lucky — **that was wrong**, and it is corrected here
  rather than quietly.
- **Check capability before spending anything.**
  `sbr.utils.gpu.require_usable_gpu` runs *before* the pool is pulled, so an
  unusable allocation is refused without paying for a 37 913-file download and
  a tree build. It still runs after dependency installation, so the saving is
  the expensive part rather than all of it. The smoke rung reports and continues on CPU instead of refusing,
  which is how a one-epoch run completed and produced a checkpoint on
  2026-08-18.

So the validator run is **unblocked**: the failure is understood, the right
machine is requestable and the request was honoured on 2026-08-18. What remains
is to run it.

Two things follow. The ship gate's latency half still has no
service-hardware measurement, because `gate.py` needs the bench kernel. And
`docs/07`'s phase-2 checklist item "first training run on a Kaggle kernel"
remains open, now with a known failure mode rather than as untried work.

One thing in the output deserves its own look: `composition.json` reports
`background_images: 0` and `negative_ratio: 0.0` while `per_pool.negatives` is
17 474, and `positives: 18 954` is the sum of *all three* pools. If that is real
rather than a reporting bug, the validator would train with no negatives at all
— and `min_precision_on_negatives ≥ 0.97` is one of its targets.

## The validator, trained 2026-08-18: it exists, and it may not ship

The first training run to complete. `hlexnc/sbr-train-validator`, yolo11n @ 448,
80 epochs, batch 32, seed 42, on a **requested Tesla T4**, against
`arudaev/smart-bin-detect@8666aa23ff1a` — whose composition the kernel asserted
against `sbr.dataset.expected` before spending a GPU minute, and which matched.
Artefacts at `arudaev/smart-bin-detect` `v1/`.

| metric | split | value |
|---|---|---|
| mAP@0.5 | test (group-aware) | **0.7524** |
| mAP@0.5:0.95 | test | 0.5175 |
| precision | test | 0.7960 |
| recall | test | 0.6879 |
| mAP@0.5 | held-out region | **unmeasurable** — no subset carries a second `region_id` |

**`may_ship: false`, and the reason is new.**

```
SHIP GATE FAILED: int8 quantisation cost 0.727 map50 (max 0.02)
```

**int8 quantisation destroys this model: 0.7524 fp32 against 0.025 int8.** Not a
degradation — a collapse to noise. The service is int8 by construction (docs/05's
whole latency budget assumes it), so there is no shippable artefact and the
refusal in `artefacts.py` is correct to hold.

This is the gate that **had no owner until 2026-08-16**, when both kernels were
deferring int8 accuracy to `gate.py`, which measures only latency. It was added
so that `may_ship` was reachable at all. **It fired on the first real run and
caught a model that would otherwise have shipped as a working detector and
answered noise.** That is the single best argument for the gate apparatus this
project has produced.

### Diagnosed 2026-08-21: quantising the detection head is what collapses it

[P9](research/probes/P9-int8-quantisation.md) measured eleven export
configurations off the same `best.pt`, calibrating from `train` and scoring on
`val`. Kaggle CPU kernel, **`representative: false`**.

| variant | val mAP@0.5 | drop vs PyTorch fp32 (0.7734) |
|---|---|---|
| fp32 ONNX control | 0.7748 | −0.0014 — **there is no export loss** |
| **detection head left in fp32** | **0.7481** | **+0.0252** |
| head fp32 + letterboxed calibration | 0.7350 | +0.0384 |
| letterboxed calibration alone | 0.0847 | +0.6887 |
| S8S8 · `reduce_range` · U8U8 · per-tensor · positive-enriched | 0.024–0.025 | ≈ +0.749 |
| as shipped | 0.015 | +0.7584 |

Excluding `/model.23/` is a **50-fold** recovery, for +5.7 ms on the Kaggle
proxy and +1.2 MB — neither of which closes a gate: the latency budget is stated
on *service* CPU and this measurement is `representative: false`, and size is not
gated at all. It also does not follow that nothing outside the head matters; that
graph still carries 619 QDQ nodes and still loses 0.0252, and **where that
residual lives was not tested**. **The three remedies onnxruntime's guidance names for this
failure mode — S8S8, `reduce_range`, U8U8 — all do nothing**, and S8S8 is 2.5×
slower besides; this is not the x86 saturation case it looked like. The calibration hypotheses were both
wrong too: enriching positives changes nothing, and letterboxing helps a
collapsed graph while *hurting* a working one.

**It still may not ship.** 0.0252 against a 0.02 budget is the middle row of P9's
pre-registered rule: the gate is missed, the model is real, and **the gate does
not move**. Whether to take a 0.025 trade is a product decision, and it would
need a `test` measurement first — there is none, deliberately, because nothing
was eligible and the split was left unspent.

Two figures here need their caveats carried with them. The historical baseline
reproduces the **collapse** but not the **figure** — 0.0150 against the published
0.025, on a graph that is not byte-identical to the Hub's — which is a toolchain
confound, recorded rather than smoothed. And anything below ~0.1 in that table is
**one number, not several**: across two runs the collapsed rows swap places
freely, while every row that means something replicates to within 0.001.

### And the residual has now been hunted and not found — P10, 2026-08-21

[P10](research/probes/P10-where-the-residual-lives.md) asked where the remaining
0.0252 lives. It ran the corrected SQNR diagnostic — which P9 never executed,
because `quantisation_error` only fires on a winner and P9 had none — and then
swept the modules it named, plus `/model.10/` regardless of the ranking.

| variant | val mAP@0.5 | drop vs 0.7733835 | QDQ nodes outside head |
|---|---:|---:|---:|
| head-fp32 anchor (P9's best, re-measured) | 0.747107 | 0.026277 | 619 |
| **head + `/model.10/` in fp32** | **0.748021** | **0.025363** | 544 |
| head + `/model.1/` | 0.746465 | 0.026918 | 613 |
| head + `/model.2/` | 0.745748 | 0.027636 | 581 |

**The diagnostic and the standing hypothesis agreed, and the sweep contradicted
both.** The single most damaged tensor in the graph is
`/model.10/m/m.0/attn/Softmax_output_0` at **23.90 dB SQNR**, 1.65 dB clear of
the next — the same C2PSA attention block a 1517× weight-scale anomaly had
pointed at. Excluding `/model.10/` removes **75 QDQ nodes, 12 % of everything
still quantised**, including that tensor — and buys **+0.000914 mAP**, which is
below the `MAP_NOISE = 0.005` this project uses for "the same candidate". The
other two modules made it slightly worse.

So: **no module outside the detection head accounts for the residual by a
distinguishable amount.** A low-SQNR activation does not imply a task-metric
cost. That is a stronger statement than P9's "not attributed" — it is evidence
against the obvious hypothesis rather than absence of evidence — and it means the
0.0254 is spread across the remaining 544 QDQ nodes rather than sitting in one
findable place.

**The gate is unmoved and the artefact still may not ship.** Best known
configuration on `val`, proxy hardware: **0.7480 against 0.7734, missing by
0.0054**. `test` was not touched and stays unspent. The remaining route to a
post-training-free int8 graph is quantisation-aware training, which is the
maintainer's decision and was **not attempted**.

**One number in P9's table above should not be compared with P10's.** The
identical head-fp32 graph measured **36.6 ms** on a Kaggle Xeon and **25.36 ms**
on a Kaggle EPYC — 31 % apart on the same bytes and the same onnxruntime,
entirely from which machine the platform allocated. Both are
`representative: false`. It is the plainest evidence in this document for why the
latency half of the gate is not closed by a proxy.

### Recall by bins per frame

docs/04 § 5 commits to this so a model that only works on one big centred bin
cannot hide behind an aggregate. **fp32, test split.** It does not hide:

| bins in frame | frames | truth boxes | detected | recall |
|---:|---:|---:|---:|---:|
| 1 | 153 | 153 | 139 | **0.9085** |
| 2 | 23 | 46 | 28 | 0.6087 |
| 3 | 15 | 45 | 35 | 0.7778 |
| **4+** | 13 | 70 | 42 | **0.6000** |

One bin is good and crowded frames lose a third of their containers. The `4+`
row exists at all only because the Open Images subset landed — the legacy
archive has no such frame — and 13 frames is a thin basis for it. **The bank of
six the PRD calls a normal input is the weakest case this model has.**

### Precision on the negative corpus

The predecessor hallucinated a glass container on a slide of black text on white.
Measured for the first time, on the 2 662 background frames in the test split:

| | |
|---|---|
| negative frames | 2 662 |
| frames with a false positive | 55 |
| frame-level specificity | **0.9793** |

**`min_precision_on_negatives` ≥ 0.97 is MET** — the first target in this
document ever to be measured rather than deferred, and the payoff for the 17 474
background frames. `min_recall_heldout_city` stays **unmeasurable**: no subset
carries a second `region_id`, which is what P7 exists to change.

## What the models were trained on

The validator: `arudaev/smart-bin-detect@8666aa23ff1a`, 18 954 frames =
17 474 background + 1 480 positive, split 13 265 train / 2 823 val / 2 866
test. The identifier: nothing yet.

The split is **group-aware by capture cluster** – frames of one bin in one
visit share a split – and never random. docs/08 § 7.3's 0.9873 came from a
random 20 % of one capture session and is not comparable to anything below.

## Validator

**Measured 2026-08-18 — see [the validator section above](#the-validator-trained-2026-08-18-it-exists-and-it-may-not-ship)**,
which carries the numbers, the recall-by-bins table, the negative-corpus
specificity, and the reason the artefact still may not ship: int8
quantisation costs 0.727 mAP@0.5 against a 0.02 budget — diagnosed
2026-08-21 as the detection head, and still 0.0252 short with the head
excluded ([P9](research/probes/P9-int8-quantisation.md)).


## Identifier

**Trained 2026-08-21**, on `arudaev/smart-bin-identify@cda374c9` — the 403
crops the human pass produced, run blind by reviewer `alex`. yolo11s-cls @ 320,
100 epochs, Kaggle T4. Full account: [P11](research/probes/P11-identifier-int8.md).

| metric | split | value |
|---|---|---|
| top-1 fp32 | **val** (group-aware, n=56) | **0.9821** |
| top-1 int8 | **val** (n=56) | **0.9821** |
| **int8 drop** | val | **0.0000** against a 0.02 budget |
| top-1 fp32 | test (group-aware, **n=47**) | 1.0000 |
| top-1 int8 | test (n=47) | 1.0000 |
| top-5 | test | 1.0 — **not a gate**, and arithmetic at three classes |
| unknown rate | test | 0.0 — **not a gate**, see below |
| accuracy when answering | test | 1.0 — **not a gate** |
| `min_formfactor_acc_heldout_city` | — | **unmeasurable** — no second city |

**The accuracy gate passes and the artefact does not ship**, because latency
was unmeasured at the time of writing; `may_ship: false` with `unmeasured`
naming the bench. That is the correct verdict, not a failure.

**`1.0000` must never be quoted without its denominator.** The test split is
**47 crops**: 25 `wheelie_small` over 9 capture clusters, 19 `wheelie_large`
over 8, and **`igloo` 3 crops over 2 clusters**. By the rule of three the 95 %
lower bound on that accuracy is **0.936**, and the igloo figure rests on two
scenes. docs/12 and AGENTS.md both predicted that a group-aware split over 17
igloo clusters would leave 2–3 in test; measured, it is 2.

**The better estimate of separability is [P1](research/probes/P1-form-factor-separability.md)'s
0.9834**, out-of-fold over all 403 crops under `GroupKFold` on capture cluster
— a far larger evaluation than 47 items.

**int8 cost nothing measurable, and the measurement is coarse.** The shipped
defaults were eligible on the first variant, so the pre-registered sweep never
ran. That is the same U8S8 per-channel configuration that cost the *validator*
0.727 mAP, which is consistent with P9's finding that the DFL detection head
was the cause — a classifier has none. It is consistent with, not proof of: on
56 val crops one extra misclassification is **0.018** against a **0.020**
budget, so the measurement resolves roughly one crop.

**The served class order is alphabetical**, read back from `model.names`:
`["igloo", "wheelie_large", "wheelie_small"]`. Not the config's order, not the
taxonomy's. The sidecar carries it and the service reads the sidecar.

### What it was not trained on

Three of ten form factors. `street_basket` is **dropped at n=1 in one capture
cluster** — it cannot be split across train/val/test, so it can be neither
trained nor evaluated — and `underground`, `textile_bank`, `sack`, `crate`,
`wall_unit` and `container_bank` have **no data at all**. All seven keep their
ids; everything B has never seen resolves to `unknown`.

[research/11](research/11-open-images-form-factors.md) established that Open
Images cannot close that gap: zero `underground`, zero `textile_bank`, zero
`wall_unit` in a 384-box sample. **`sack` and `textile_bank` both carry
Deggendorf pack rules**, so a pilot there will meet bins B cannot name.

## What a scan actually produces

Measured 2026-08-21 against the real validator graph, served locally with
`SBR_ALLOW_UNGATED=1`. Reported because "the service works" is a claim and
these are observations.

| frame | manifest says | detections returned | server `ms` |
|---|---|---|---|
| legacy, one bin | 1 | **1** at conf 0.884, body colour `black` | 129 |
| legacy, two bins | 2 | **1** at conf 0.779 | 126 |
| legacy, three bins | 3 | **3** at conf 0.858 / 0.768 / 0.606 | 129 |
| Open Images, eighteen bins | 18 | **7**, and **0 crops** — every box fell under `min_box_px` | 90 |
| negative corpus, street scene | 0 | **0** | 91 |
| negative corpus, hard negative | 0 | **0** | 84 |

Four things worth keeping:

- **The two-bin frame returned one box.** That is not a surprise, it is
  docs/11's own measured recall at two bins per frame: **0.6087**.
- **`form_factor`, `stream` and `local_name` were `null` on every detection**,
  because the service was running validator-only. The resolver answers
  `unknown`, which is the designed state.
- **The 18-bin frame produced `crops: 0`.** Every box was below the 64 px floor
  `identifier.yaml` sets, so the identifier would have been handed nothing —
  corroborating [research/11](research/11-open-images-form-factors.md)'s finding
  that 29 % of Open Images boxes fall under that floor.
- **Both background frames returned an empty list.** "Nothing here" is the
  answer that matters most, and it is the one the negative corpus was bought
  for.

The browser reached the same service from `http://localhost:5173` over CORS and
got HTTP 200, and the settings screen named the transport **`rest`** rather than
`mock`. A screenshot could not be produced in this environment; the page text
and the response are the evidence instead.

## Novelty precision

The kill criterion in docs/07 is **< 0.5**, and the whole improvement loop
rests on the validator/identifier disagreement being a trustworthy signal.

**_not measured_, and the blocker has changed.** It needed both models plus a
human verdict on whether each flagged frame was genuinely a new bin type. As of
2026-08-21 **both models exist**, so the first half is no longer missing; what
remains is the adjudication of the flags, which nothing has produced yet.

Worth noting what B's shape does to this. The disagreement signal is
*validator fires, identifier does not recognise it* — and B knows three form
factors out of ten. Against a Deggendorf street that is a reasonable detector of
novelty; against `sack`, `textile_bank` or anything else in the coverage gap it
will flag constantly and correctly, which is the loop working rather than
failing, but it means **the first novelty-precision measurement will be
dominated by the coverage gap rather than by genuinely new bin types.** Design
the set accordingly (docs/12 P2).

## Numbers this project does not quote

- the predecessor's **95.2 % mAP@0.5** – a random split of one week of
  photographs in one city;
- the **0.9873** independent re-validation (docs/08 § 7.3) – same split, so
  it reproduces the memorisation rather than refuting it.

Both are in-distribution. Neither is this project's baseline.

