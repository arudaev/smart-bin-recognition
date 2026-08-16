# 04 – ML Pipeline

> Two models, and a labelling pipeline where machines do the tedious work and a
> human only adjudicates. The goal is accuracy that compounds: the more the app
> is used, the better it gets.

Training pattern mirrors [CheXVision](../../11-CheXVision/README.md): HF Hub for
data and artefacts, Kaggle GPU kernels for training, a laptop for dispatch only.
No local training, no Colab, no notebooks.

---

## 1. The two models

| | **A – Validator** | **B – Identifier** |
|---|---|---|
| Question | "Is there a bin, and where?" | "What kind of bin?" |
| Classes | 1 (`bin`) | 10 form factors |
| Arch | YOLO11n @ 448 | YOLO11s @ 320 on crops |
| Input | full frame | crop from A |
| Positives | every bin image we have | curated labelled bins |
| **Negatives** | **large open-corpus + hard negatives** | – |
| Target | recall ≥ 0.99, precision ≥ 0.97 | best achievable |
| Failure mode | misses a bin (rare) | says `unknown` (expected, useful) |

Rationale in [01-architecture § 3](01-architecture.md#3-two-models-and-why). The
short version: detection is expected to generalise across cities and
identification is not, so separating them turns "B is wrong" into a
**trustworthy signal** rather than noise. The premise is untested – phase 2
exists to test it.

### Model A's negative corpus

The majority of A's training data is **not bins**. This is what buys precision.

| Source | Purpose | Volume |
|---|---|---|
| Open Images / COCO street & urban scenes | general negatives | ~15 000 |
| **Hard negatives** – postboxes, planters, utility cabinets, parked cars, wheeled luggage, AC units, gas meters | the things that actually get confused for bins | ~2 000, curated |
| Recycling logos on non-bins (posters, packaging, signage) | breaks the "green + arrows = bin" shortcut | ~500 |
| Legacy + new bin images | positives | ~500 and growing |

**The ratio, defined once.** It is *background frames : frames containing at
least one bin*, and there is only one number:

| | frames | ratio |
|---|---:|---|
| designed, when this table was written | 18 000 : ~500 | ~36:1 |
| **realised, at revision `8666aa23`** | **17 474 : 1 480** | **11.8:1** |

The realised ratio is lower because the harvest **added positives** (1 110 Open
Images bin frames on top of 370 legacy), not because it lost negatives. That is a
good trade and the number needs no defending: what buys precision is that the
detector sees far more not-bins than bins, and 12:1 does that. The claim to
retire is "30:1 is the point" — the *asymmetry* is the point, and the specific
figure was never load-bearing.

Two earlier statements of this are superseded: "roughly 30:1" here, and "~15.7:1"
in § 5 below, which divided the negatives by the Open Images bins alone and left
the legacy frames out.

Hard negatives are also harvested automatically: any frame where A fires but a
contributor marks "there is no bin here" becomes a hard negative for the next
round.

### Why B runs on crops

Model B never sees a full frame. It sees a normalised, centred crop with the
background mostly removed. Three consequences:

1. A smaller, cheaper model reaches higher accuracy on the same data.
2. **Colour measurement is taken from the object, not the scene.** A mask (§ 3)
   would tighten this further, so a bin photographed against grass does not read
   as greenish — but *whether a mask is needed at all is unmeasured*. The crop is
   already filled by the object (`identifier.yaml` pads by 0.12), and a mask does
   not solve the harder problem of separating lid from body.
   [docs/12 probe P3](12-validation-protocol.md#p3--colour-measurement) tests
   whether SAM belongs on the critical path before it is put there.
3. Multi-bin scenes are free **in accuracy** – N crops, N independent
   identifications, no crowding in the detector head. They are **linear in
   cost**: N crops is N × 25 ms, and a bank of six triples the frame's CPU. The
   two were stated as one property until 2026-08-16; see
   [01 § 4](01-architecture.md#latency-budget) and
   [05 § 3](05-cost-model.md#3-the-concurrency-ceiling--the-number-that-matters).

## 2. The human-reviewed improvement loop

> Named carefully. It is **not** a self-improving system and calling it a
> flywheel overstates what is automated. Software finds valuable examples,
> deduplicates them, and proposes labels; **a human decides what becomes truth**,
> and promotion to a deployed model is a separate, manual, gated step. That is a
> controlled release cycle with machine assistance, which is the honest
> description and also the safe design — see the guardrails in § 4.

```
   user scans
       │
       ▼
   Model A ──── no bin ────► nothing
       │
    bin found
       │
       ▼
   Model B ──── confident + pack resolves ────► answer shown, done
       │
       ├── unknown / low confidence ──────┐
       ├── user corrected the answer ──────┤
       ├── geohash cell never seen ────────┤──► COLLECTION QUEUE
       └── contributor says "no bin" ──────┘    (frame retained only with consent)
                                                        │
                                                        ▼
                                          auto-labelling pipeline (§ 3)
                                                        │
                                                        ▼
                                          human adjudication, by cluster (§ 4)
                                                        │
                                                        ▼
                                          HF dataset revision bump
                                                        │
                                                        ▼
                                          Kaggle GPU retrain A and B
                                                        │
                                          fewer unknowns ──┐
                                                  ▲        │
                                                  └────────┘
```

The queue is prioritised by expected information gain: **A-confident +
B-unknown** first, then new regions, then user corrections, then everything else.
Ordinary successful scans contribute nothing and are discarded – there is no
value in the ten-thousandth photo of a bin we already recognise.

## 3. Auto-labelling

Four tools, each doing the one thing it is actually good at. A note on naming,
because it matters for picking the right one:

- **DINOv2** (Meta) – self-supervised **features**. It does *not* produce boxes
  and takes no text prompt. Useful here for embeddings: dedup and clustering.
- **GroundingDINO** – **open-vocabulary detection from text**. This is the one
  that boxes things from a prompt like `"waste container . wheelie bin ."`.
- **SAM 2** (Meta) – segments given a box or point prompt. Turns a loose box into
  a tight mask. **One object per prompt.**
- **SAM 3** (Meta, Nov 2025) – takes a *noun phrase* and returns masks for
  **every** matching instance at once. This is boxes and masks in one call, and
  it makes steps [2] and [3] below a single step.
- **YOLO-World / YOLOE** – open-vocab detection, faster and lighter than
  GroundingDINO, slightly less accurate. Note that this pipeline is **batch and
  offline**, so throughput is worth nothing here and accuracy is worth
  everything — the opposite of how one would choose for the request path.

### The pipeline

```
new frames from the collection queue
        │
   [1] near-duplicate removal        DINOv2 embeddings, cosine > 0.95
        │                            (a 5 s scan yields 15 near-identical frames –
        │                             keep the sharpest, drop the rest)
        ▼
   [2+3] boxes AND masks             SAM 3, concept prompt:
        │                            "waste container . wheelie bin . dumpster .
        │                             bottle bank . recycling container ."
        │                            → every instance at once, boxes + masks.
        │                            GroundingDINO → SAM 2 remains the documented
        │                            fallback for near-miss discrimination
        │                            (planter vs bin), which is a naming problem
        │                            SAM 3 does not obviously solve.
        ▼
   [4] semantic label                VLM on each masked crop → form factor,
        │                            candidate stream, citation to municipal
        │                            guidance. Strict JSON, canonical vocabulary
        │                            only (ml/src/sbr/escalation/schema.py)
        ▼
   [5] cluster the unknowns          DINOv2 embeddings + HDBSCAN
        │                            → a human labels a CLUSTER, not 500 images
        ▼
   [6] human adjudication (§ 4)
```

Steps 1–3 need no waste-domain knowledge and run free on a Kaggle GPU kernel.
Step 4 **no longer has to be paid either**: an open-weight VLM (InternVL3,
Qwen3-VL) runs on the same free Kaggle GPU, with a hosted batch API retained as
fallback for schema reliability
([05 § 5](05-cost-model.md#5-the-paid-path-and-how-it-stopped-being-one),
[research/04](research/04-labelling-and-vlms.md)). Either way it runs **batch
offline**, never in the user's request path, and it is capped.

### How accurate is any of this?

**Unmeasured, and no published number transfers to our bins.** Until
[docs/12 probes P1 and P6](12-validation-protocol.md) report, every accuracy
claim about auto-labelling in this document is a **prior**. What can be said now
is that "auto-labelling" is four tasks of very different difficulty and they
should not be quoted as one number:

| Sub-task | Expectation | Note |
|---|---|---|
| **Boxes** | decent recall, moderate precision | failure mode is exactly our hard-negative list — planters, postboxes, utility cabinets |
| **Per-location categorisation** | *not a model at all* | geohash → jurisdiction → pack is a deterministic lookup. The thing that could most harm a user is not model-driven |
| **Form factor** | hardest, possibly ill-posed | `wheelie_small` vs `wheelie_large` is a size distinction asked of a resized crop — probe P1 |
| **Colour** | a measurement, not a label | § 1, probe P3 |

**Accuracy is also the wrong headline metric**, because no auto-label ever
reaches a user — it is a proposal to a reviewer. What matters is *time saved per
human decision*: a 70 %-correct proposal confirmable with one keystroke is a win,
since the reviewer was going to look anyway. Accuracy starts mattering
enormously the moment auto-**accept** is on the table, which is the next
paragraph.

**Agreement gating.** Where the proposal step and the VLM agree with high
confidence *and* the VLM's form factor matches model B's guess, the label may be
accepted into a `machine_labelled` pool. Everything else goes to a human. The
pools stay separate in the dataset so their contribution can be measured – and
rolled back if machine labels turn out to hurt.

Two honest caveats on that gate:

- **It is circular by construction.** It auto-accepts what B already knows and
  routes disagreements to a human. That is the *safe* direction, but it means
  auto-labelling saves least effort exactly where value is highest — and the
  collection queue is prioritised by **A-confident + B-unknown** (§ 2), which is
  precisely the population the gate cannot accept. At pilot volume, expect most
  of the queue to reach a human regardless.
- **Label noise is expensive at our size.** At 85 % accuracy, auto-accepting puts
  15 % wrong labels into training; with ~1 480 positives that is not absorbable.
  This is the concrete reason behind the guardrail in § 4.

### Why not label with the legacy model

It is available and it is tempting, but it only knows four Deggendorf classes.
Using it as a teacher would propagate exactly the jurisdictional bias this
project exists to remove. It is kept as a **baseline to beat**, not a labeller.

## 4. Human adjudication

The only irreplaceable step, so it is made as small as possible:

- Review is **by cluster**, not by image. One decision covers a group of visually
  near-identical bins.
- Where frames came from **video**, review is by **track** – one physical bin
  through one walk-around. One decision then covers every frame that object
  appears in, which is what makes the only irreplaceable step in this pipeline
  affordable at scale ([research/08](research/08-video-ingestion.md)). It also
  cuts both ways: a wrong track label is wrong in every frame of the track, so
  per-frame adjudication of video data gets the downside without the upside.
- The reviewer sees the machine's proposal pre-filled and either confirms or
  corrects. Confirmation is one keystroke.
- Anything touching **safety-relevant rules** (what may be thrown where) is
  reviewed against a cited municipal source, never accepted on model confidence.
### What may auto-accept, and what may never

The guardrail in AGENTS.md says *"never let user input reach training data
without human label review"*, and this section used to permit high-agreement
machine labels to auto-accept. Both cannot be true. **The resolution is the
provenance of the image, not the confidence of the label** — because the two
cases have completely different blast radii:

| Image came from | May auto-accept? | Why |
|---|---|---|
| **A user's contributed frame** | **Never.** Human review, always | Poisoning the registry costs data; poisoning the training set costs every future answer. This is the guardrail and it is absolute |
| A public corpus we harvested (Open Images, and similar) | Yes, at high agreement, into `machine_labelled` | Nobody can aim it at us, and the pool is separated so its contribution is measurable and reversible |
| Any **new** form factor, from any source | **Never** | There is no well-represented prior to agree with, so "high agreement" is meaningless |

`identifier.yaml`'s `label_sources: ["human", "machine_agreed", "legacy"]` is
consistent with this — `machine_agreed` means the public-corpus row, never the
user row.

## 5. Datasets

| HF repo | Contents | Exists? |
|---|---|---|
| `arudaev/smart-bin-detect` *(dataset)* | Model A: bins + negatives + hard negatives | **yes**, pinned at `8666aa23` |
| `arudaev/smart-bin-detect` *(model)* | both artefacts + sidecars, `hub.model_repo` | not yet – no run has completed |
| `arudaev/smart-bin-identify` | Model B: crops labelled by form factor | **planned**; blocked on the adjudication pass |
| `arudaev/smart-bin-raw` | private – retained frames pending adjudication | **planned**; needs the service and the consent flow first |

The first two share an id: the Hub namespaces datasets and models separately, so
`arudaev/smart-bin-detect` is both a dataset repo and a model repo and they do
not collide. Worth stating, because it reads like a mistake.

Pinned by commit revision in `ml/src/sbr/utils/hub.py`. Every image carries
provenance: source, region, capture date, label origin
(`human` / `machine` / `legacy`), and adjudication status.

### What `smart-bin-detect` actually holds

At revision `c39b0f87` (2026-08-16), 18 954 frames over three subsets:

| Subset | Frames | Boxes | Layout | Region | What it buys |
|---|---:|---:|---|---|---|
| `legacy` | 370 | 403 | flat | `de-by-deggendorf` | the hand-labelled seed; one city, one week |
| `open_images` | 1 110 | 1 936 | sharded | `unknown` | worldwide bins, and **98 frames with 4+ bins** |
| `negatives` | 17 474 | 0 | sharded | `unknown` | 14 975 street + 2 499 hard, all guaranteed bin-free |

Against **all** bin frames the negatives are **11.8:1** (§ 1 defines the ratio and
records why the earlier 15.7:1 here was wrong — it divided by the Open Images
bins alone and dropped the legacy 370).

Two cautions this table exists to make visible. The `4+` bucket comes entirely
from Open Images — the legacy archive has no frame with four or more bins, so
any multi-bin recall number is measured on out-of-city data only. And no subset
carries a usable second `region_id`, so `holdout_region` is empty and the
generalisation number this phase wants is **not yet available** from this data.

### How a subset is laid out, and why it is sharded

Each repo holds one directory per subset – `legacy/`, `open_images/`,
`negatives/` – and each is a self-contained pool:

```
<subset>/
├── manifest.json     provenance per frame and per crop; declares the layout
├── images/ab/<id>.jpg
├── labels/ab/<id>.txt    an EMPTY file is a deliberate background image
└── crops/               identifier candidates, where relevant
```

The `ab` level is `sha256(stem)` truncated to two hex characters, 256 buckets.
It exists because **the Hub rejects a push where any directory holds more than
10 000 files**, and `ml/configs/open_images.yaml` asks for 15 000 street plus
2 500 hard negatives — so a flat `negatives/labels/` is ~17 500 and the push is
refused outright. The first harvest learned that after thirty minutes of
downloading, mid-upload; `sbr.utils.hub.preflight_layout` now refuses such a
tree before the first request.

`manifest.json` declares `"layout": "sharded"`. **A manifest with no `layout`
key is flat**, which is what the pinned `legacy` revision is, and
`sbr.dataset.pool` is the only thing that decides between the two. The training
tree that `prepare.build_yolo_tree` assembles is deliberately flat — it is local
scratch that ultralytics reads directly and that is never pushed.

Sharding clears the directory cap; it does not clear the **rate limit**. The Hub
allows 1000 API requests per 5 minutes and a full harvest is ~35 000 LFS
objects, so expect `upload_large_folder` to spend a long time in 429 backoff.
Those lines are the upload working, not failing. Budget on the order of an hour.

### Seeding from the legacy dataset

The predecessor's hand-labelled photographs are the seed of both datasets.

The published archive has now been inventoried from the release asset itself –
[08-legacy-audit § 7.1](08-legacy-audit.md#71-the-archive-as-it-really-is):

- `cv_garbage.zip` is a **partial copy**. It ships 401 of 466 label files and
  **16** of 466 images under `YOLO_Dataset/`; the pixels are in `labeled/`.
- **370 labels pair with an image.** That is the usable seed – not 466.
- `labeled/` is split by annotator (Alex 118, Fares 161, Sameer 148 present;
  101 / 135 / 132 of them pairable), which is a useful grouping key – annotator
  style is a plausible confound and can be held out to check for it.
- Class balance over the 403 usable boxes: Restmüll 171, Papier 101, Biomüll 87,
  **Glas 44**. Glas is under-represented and is the only class mapping to
  `igloo`.
- `labeled/` and `YOLO_Dataset/` disagree in exactly **2** of 370 frames.

The full 466 existed at training time – the Ultralytics caches inside the
archive say so – and the publishing step lost them. The layout is now a contract
in `ml/configs/legacy_archive.yaml`, verified by `sbr.dataset.archive`; the
import refuses to run against a copy that does not match.

### Multi-bin coverage: effectively zero

Re-counted 2026-08-06 over the 370 pairable frames (the earlier count was over a
466-file set that is not in the published archive; the finding is unchanged):

| boxes in frame | images | over all 401 label files |
|---|---|---|
| 1 | **341 (92.2 %)** | 370 |
| 2 | 25 | 27 |
| 3 | 4 | 4 |
| **4 or more** | **0** | **0** |

**There is not one photograph of a bank of containers in the entire dataset.**
The most crowded frame holds three household wheelie bins.

This is a product risk, not a data footnote. Multi-bin is a v1 headline
capability – [00-PRD](00-product-requirements.md) calls a bank of six containers
"a normal input, not an edge case" – and the identifier would currently be
trained almost entirely on a single, centred, close-range bin. It also explains
the slide-08 failure in
[08-legacy-audit § 7.5](08-legacy-audit.md#75-the-result-that-matters-most):
three real bins at small scale inside a layout, all missed. A model shown one
big centred bin 92 % of the time has no reason to learn anything else.

Consequences, both now committed:

- **Deliberate multi-bin capture is a priority for the first collection round**,
  not an optional extra. Target banks, kerbside rows, and underground clusters
  specifically, and capture them from the distance a user actually stands at.
  **Probably by filming rather than photographing**: a walk-along a bank gives
  multi-bin frames, viewpoint diversity and a real `region_id` from the video's
  GPS in one pass. [Probe P7](12-validation-protocol.md#p7--video-as-the-capture-format)
  decides. If video is used, **counts are reported as tracks / objects / videos /
  locations, never as a frame total** — 108 000 frames of forty bins is forty
  bins, and quoting the frame count would make every ratio in § 1 fiction.
- **Scale and count belong in the evaluation split.** Report detection recall
  bucketed by bins-per-frame, so a model that only works on the easy case cannot
  hide behind an aggregate number.

Both of the things that were still open here – class balance, and whether
`labeled/` and `YOLO_Dataset/` disagree – are answered above and recorded in
[08-legacy-audit § 7.1.1](08-legacy-audit.md#711-class-balance-and-internal-disagreement).

`ml/src/sbr/dataset/legacy_import.py` has been re-validated against the real
layout. It pairs on the eight-hex join key, refuses to run when
`sbr.dataset.archive.verify` reports a mismatch, and carries provenance on every
record.

**Seven of the ten form factors have no legacy data at all.** The four legacy
classes can only ever reach `wheelie_small`, `wheelie_large` and `igloo`;
`underground`, `textile_bank`, `street_basket`, `sack`, `crate`, `wall_unit`
and `container_bank` start from zero. Together with the multi-bin gap, that is
what the out-of-city harvest in phase 2 exists to fill.

## 6. Training

Kaggle GPU kernels, 30 h/week free, dispatched and forgotten.

```bash
python ml/scripts/dispatch.py push validator  --version 1
python ml/scripts/dispatch.py push identifier --version 1
python ml/scripts/dispatch.py status validator
```

Configs in `ml/configs/` with `_defaults_` inheritance. Nothing hard-coded.

Both models export to ONNX for the inference service. Because inference is
server-side, the ≤ 6 MB device budget is gone – but the models stay small anyway,
since **CPU inference latency is now the constraint** and the free Space has two
vCPUs. Budgets: A ≤ 50 ms @ 448, B ≤ 25 ms per crop.

## 7. Evaluation

The predecessor reported mAP@0.5 = 95.2 % on a random split of 466 photos taken
in one city in one week. Independent re-validation returned **0.9873** – it
reproduces, and beats the claim
([08-legacy-audit § 7.3](08-legacy-audit.md#73-independent-validation)).

That is not good news, and it is not this project's baseline. The same model
fires `Glas` at 0.39 confidence on a slide of plain black text on white, and
misses three real bins photographed at small scale
([§ 7.5](08-legacy-audit.md#75-the-result-that-matters-most)). A near-perfect
in-distribution score and a false positive on a text document are one finding,
not two: the model was never shown a negative, so it has no concept of "not a
bin". That is precisely what the validator's negative corpus is for, and why the
held-out-city split below is the only number worth quoting.

Three splits, always reported together:

| Split | Construction | Meaning |
|---|---|---|
| in-distribution | random, group-aware | upper bound |
| held-out location | whole neighbourhoods excluded | generalisation within a jurisdiction |
| **held-out city** | every image from an unseen city | **predicts launch behaviour** |

Grouping is by capture cluster, so frames of the same bin never straddle a split.

### Targets versus gates – different things, different consequences

A **gate** is arithmetic the free tier depends on: miss it and the service costs
money, so the build fails. A **target** is how good the model is: miss it and the
answer is to write the number down and go and fix it, not to refuse to ship the
only model that exists.

| Metric | Target | Where it lives |
|---|---|---|
| A recall (held-out city) | ≥ 0.97 | `validator.yaml` `export.targets` |
| A precision on the negative corpus | ≥ 0.97 | `validator.yaml` `export.targets` |
| B form-factor accuracy (held-out city) | ≥ 0.85 | `identifier.yaml` `export.targets` |
| End-to-end stream accuracy where a pack exists | ≥ 0.95 | needs the service; phase 3 |
| Novelty precision – flagged items that were genuinely new | ≥ 0.70 | [probe P2](12-validation-protocol.md#p2--novelty-scoring-bake-off) |

Until 2026-08-16 these were **decorative**: `export.targets` was read by nothing,
so a fast but useless model produced a sidecar indistinguishable from a good one.
`sbr.export.onnx_export.check_targets` now reads them and writes a verdict into
the sidecar beside the gates, in three categories — met, missed, and
**unmeasurable**.

That third category is the one that matters today: the held-out-city targets need
a second `region_id` and no subset has one (§ 5), so they report as *missing
evidence* rather than being silently skipped. That is what stops the
generalisation question — the one this whole phase exists to answer — from being
quietly dropped.

Novelty precision is the health metric for the whole loop: if the flag fires on
things that are not actually novel, adjudication time is being wasted. It has a
target here and a kill criterion in
[07-roadmap](07-roadmap.md#kill-criteria), and until probe P2 defines the frozen
set it has no measurement procedure at all.

### The gate that does not exist yet

Nothing stops **v2 from being worse than v1**. The ship gates judge an artefact
in isolation — latency, quantisation cost — and never against the deployed model.
A regression gate (compare the candidate to the pinned production sidecar on the
frozen set, refuse promotion on a regression) is the one idea worth taking from
industrial pipelines, and it costs one comparison
([research/03 § 2](research/03-data-engine-patterns.md)). It belongs with the
second training run, since v1 has nothing to regress against.

## 8. Layout

**What exists today:**

```
ml/
├── configs/            default · validator · identifier · legacy_archive · open_images
├── src/sbr/
│   ├── taxonomy.py             ontology, region packs, resolver
│   ├── config.py               YAML inheritance, cloud guard
│   ├── bench.py                the measuring instrument, and what "service CPU" means
│   ├── dataset/
│   │   ├── archive.py          the legacy archive's contract; refuses a short copy
│   │   ├── legacy_import.py    reconstructs the predecessor's split archive
│   │   ├── open_images.py      open-corpus + hard-negative assembly
│   │   ├── pool.py             the on-disk layout: shards, and the Hub's cap
│   │   └── prepare.py          group-aware / region-holdout splits
│   ├── export/onnx_export.py   int8 export, the ship gates, and the targets
│   ├── escalation/schema.py
│   └── utils/hub.py
├── kaggle/             train_validator · train_identifier · build_negatives · bench_latency
├── scripts/            dispatch · adjudicate · gate · evaluate · push_dataset
│                       inventory_legacy · benchmark_legacy · validate_taxonomy
└── tests/
```

**Planned, and deliberately not built yet** – `src/sbr/autolabel/` and
`kaggle/autolabel_batch/`: near-duplicate removal, SAM 3 proposal, VLM semantics,
and HDBSCAN clustering for batch review. This block used to list them as though
they existed.

Two of the four are probably **not ours to write**: FiftyOne does embedding
dedup, clustering and mistakenness out of the box and is open source
([research/03 § 5](research/03-data-engine-patterns.md)). Evaluate it before
writing `dedupe.py` and `cluster.py`. And none of this is built before
[probes P1, P3 and P6](12-validation-protocol.md) report — building an
auto-labelling stack around unmeasured assumptions is the specific mistake this
sequencing exists to avoid.
