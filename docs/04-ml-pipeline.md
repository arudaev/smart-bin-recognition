# 04 – ML Pipeline

> Two models, and a labelling pipeline where machines do the tedious work and a
> human only adjudicates. The goal is accuracy that compounds: the more the app
> is used, the better it gets.

Training pattern mirrors [CheXVision](../../11-CheXVision/AGENTS.md): HF Hub for
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

Roughly **30:1 negative to positive.** That ratio is the point. A detector
trained only on photos of bins learns that everything is a bin.

Hard negatives are also harvested automatically: any frame where A fires but a
contributor marks "there is no bin here" becomes a hard negative for the next
round.

### Why B runs on crops

Model B never sees a full frame. It sees a normalised, centred crop with the
background mostly removed. Three consequences:

1. A smaller, cheaper model reaches higher accuracy on the same data.
2. **Colour measurement is taken from the object, not the scene.** With the SAM 2
   mask (§ 3) it is taken from the *mask*, so a bin photographed against grass no
   longer reads as greenish.
3. Multi-bin scenes are free – N crops, N independent identifications, no
   crowding in the detector head.

## 2. The improvement loop

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
  a tight mask.
- **YOLO-World / YOLOE** – open-vocab detection, faster and lighter than
  GroundingDINO, slightly less accurate.

### The pipeline

```
new frames from the collection queue
        │
   [1] near-duplicate removal        DINOv2 embeddings, cosine > 0.95
        │                            (a 5 s scan yields 15 near-identical frames –
        │                             keep the sharpest, drop the rest)
        ▼
   [2] candidate boxes               GroundingDINO, prompt:
        │                            "waste container . wheelie bin . dumpster .
        │                             bottle bank . recycling container ."
        ▼
   [3] tight masks                   SAM 2, prompted by [2]'s boxes
        │                            → precise boxes AND a colour-measurement mask
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
Step 4 is the only paid step, it runs in **batch offline** rather than in the
user's request path, and it is capped.

**Agreement gating.** Where GroundingDINO and SAM 2 agree with high confidence
*and* the VLM's form factor matches model B's guess, the label is accepted
automatically into a `machine_labelled` pool. Everything else goes to a human.
The pools stay separate in the dataset so their contribution can be measured –
and rolled back if machine labels turn out to hurt.

### Why not label with the legacy model

It is available and it is tempting, but it only knows four Deggendorf classes.
Using it as a teacher would propagate exactly the jurisdictional bias this
project exists to remove. It is kept as a **baseline to beat**, not a labeller.

## 4. Human adjudication

The only irreplaceable step, so it is made as small as possible:

- Review is **by cluster**, not by image. One decision covers a group of visually
  near-identical bins.
- The reviewer sees the machine's proposal pre-filled and either confirms or
  corrects. Confirmation is one keystroke.
- Anything touching **safety-relevant rules** (what may be thrown where) is
  reviewed against a cited municipal source, never accepted on model confidence.
- Machine labels never enter the training set unreviewed *for new form factors*.
  For form factors already well represented, high-agreement machine labels may
  auto-accept.

## 5. Datasets

| HF repo | Contents |
|---|---|
| `arudaev/smart-bin-detect` | Model A: bins + negatives + hard negatives |
| `arudaev/smart-bin-identify` | Model B: crops labelled by form factor |
| `arudaev/smart-bin-raw` | private – retained frames pending adjudication |

Pinned by commit revision in `ml/src/sbr/utils/hub.py`. Every image carries
provenance: source, region, capture date, label origin
(`human` / `machine` / `legacy`), and adjudication status.

### Seeding from the legacy dataset

The predecessor's hand-labelled photographs are the seed of both datasets.

The complete archive has now been inventoried –
[08-legacy-audit § 7.1](08-legacy-audit.md#71-the-archive-as-it-really-is):

- `YOLO_Dataset/` holds **466** images with a 1:1 label file, 372 / 94 train/val,
  no orphans on either side.
- `raw_images/` holds 470; four never made it through labelling.
- `labeled/` is split by annotator (Alex 156, Fares 161, Sameer 149), which is a
  useful grouping key – annotator style is a plausible confound and can be held
  out to check for it.

### Multi-bin coverage: effectively zero

Counted 2026-08-02 over all 466 label files:

| boxes in frame | images |
|---|---|
| 1 | **430 (92.3 %)** |
| 2 | 30 |
| 3 | 6 |
| **4 or more** | **0** |

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
  specifically, and photograph them from the distance a user actually stands at.
- **Scale and count belong in the evaluation split.** Report detection recall
  bucketed by bins-per-frame, so a model that only works on the easy case cannot
  hide behind an aggregate number.

Still to establish before the import is trusted:

- class balance, and which classes are under-represented
- whether `labeled/` and `YOLO_Dataset/` disagree anywhere

`ml/src/sbr/dataset/legacy_import.py` was written against the incomplete archive;
its path resolution must be re-validated against the real layout above before use.

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

Per-model targets:

| Metric | Target |
|---|---|
| A recall (held-out city) | ≥ 0.97 |
| A precision on the negative corpus | ≥ 0.97 |
| B form-factor accuracy (held-out city) | ≥ 0.85 |
| End-to-end stream accuracy where a pack exists | ≥ 0.95 |
| Novelty precision – flagged items that were genuinely new | ≥ 0.70 |

The last one is the health metric for the whole loop. If the flag fires on things
that are not actually novel, adjudication time is being wasted.

## 8. Layout

```
ml/
├── configs/            default.yaml · validator.yaml · identifier.yaml
├── src/sbr/
│   ├── taxonomy.py             ontology, region packs, resolver
│   ├── config.py               YAML inheritance, cloud guard
│   ├── dataset/
│   │   ├── legacy_import.py    reconstructs the predecessor's split archive
│   │   ├── negatives.py        open-corpus + hard-negative assembly
│   │   └── prepare.py          group-aware / region-holdout splits
│   ├── autolabel/
│   │   ├── dedupe.py           DINOv2 embeddings, near-duplicate removal
│   │   ├── propose.py          GroundingDINO → SAM 2 → boxes + masks
│   │   ├── semantic.py         VLM crop → form factor + stream + citation
│   │   └── cluster.py          HDBSCAN over embeddings for batch review
│   ├── export/onnx_export.py
│   ├── escalation/schema.py
│   └── utils/hub.py
├── kaggle/{train_validator,train_identifier,autolabel_batch}/
├── scripts/            dispatch.py · validate_taxonomy.py · benchmark.py
└── tests/
```
