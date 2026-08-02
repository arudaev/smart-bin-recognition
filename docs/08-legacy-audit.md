# 08 – Legacy Audit: the Waste Sorting Assistant

> What the predecessor actually was, how it ran, what its pipeline looked like,
> and what survives into Smart Bin Recognition.

Source: [`arudaev/Painfully-Trivial`](https://github.com/arudaev/Painfully-Trivial),
directories `cv_garbage/` and `streamlit_app/`. TH Deggendorf, Computer Vision
course (Prof. Dr. Glauner), 2025. Team: Sameer, Fares, Alex.

The project was called "Deggendorf Waste Sorting Assistant" throughout the code.
The name it *should* have had is on slide 3 of its own presentation deck
(`cv_garbage/_CV-Project.pdf`):

> **Our Solution – Smart Bin Recognition**

That is the name this repo takes.

---

## 1. What it was

A YOLOv8 object detector fine-tuned on 466 self-captured photographs of waste
bins in Deggendorf, wrapped in a Streamlit web app with a WebRTC live-camera
mode. Four classes, hard-coded, German-only: `Biomüll`, `Glas`, `Papier`,
`Restmüll`.

| Fact | Value | Source |
|---|---|---|
| Base model | `yolov8s.pt` | `cv_garbage/2-Computer-Vision.py:426` |
| Dataset | 466 images, 372 train / 94 val (80/20) | deck slide 10 |
| Classes | 4 (`Biomüll`, `Glas`, `Papier`, `Restmüll`) | `2-Computer-Vision.py:323` |
| Training | 50 epochs, batch 4, imgsz 960, AdamW lr0 1e-3 | `2-Computer-Vision.py:425-466` |
| Compute | Google Colab GPU (Tesla T4) | deck slide 10 |
| Checkpoint | `waste_detector_best.pt`, 22.5 MB | GH release `v1.0.0` |
| Dataset archive | `cv_garbage.zip`, **2.15 GB** | GH release `v1.0.0` |
| Claimed metrics | mAP@0.5 95.2 %, precision 92.8 %, recall 89.6 % | `streamlit_app/README.md` |

### The three steps, per the deck

1. **The Dataset** – 466 real-life photos captured around Deggendorf, stored on
   Google Drive, synced into a Colab notebook.
2. **The Labeling** – a hand-rolled Jupyter widget GUI first (too slow), then
   Label Studio with bounding boxes, exported directly to YOLO format. Umlauts in
   filenames broke YOLO ingestion and files had to be renamed.
3. **The Codebase** – fine-tune YOLOv8, real-time loop with OpenCV, iterate.

---

## 2. How it actually ran

Three separate, partly incompatible execution paths existed:

**(a) Notebook / Colab** – `cv_garbage/2-Computer-Vision.ipynb` (and its
jupytext twin `.py`). Self-installing dependency cell, Google Drive mount, Label
Studio setup, training config, evaluation, matplotlib prediction grid. By the
time it was submitted the training call itself was commented out and
`best_model_path` was **hard-coded to an absolute Windows path**
(`2-Computer-Vision.py:500`), so the notebook could not reproduce its own model.

**(b) Local OpenCV loop** – `cv_garbage/YOLO_Model.py`. Opens `cv2.VideoCapture(0)`
(or a DroidCam HTTP stream at `192.168.0.109:4747`), predicts at `conf=0.65`,
`iou=0.35`, `imgsz=640`, draws boxes plus a two-item disposal hint, prints FPS.
This is the mode from the demo video – *a phone streaming to a laptop*. It is
what the deck's own next-steps slide calls "the laptop workaround."

**(c) Streamlit app** – `streamlit_app/app.py`, 2 287 lines, single file.
Five pages (Home, Live Detection, Model Training, Analytics, Team & About),
`streamlit-webrtc` for live video, model auto-downloaded from the GitHub release
on first run, deployed to Streamlit Community Cloud and Docker/GHCR.

### The pipeline, as built

```
phone camera ──► Google Drive ──► Colab notebook ──► Label Studio (manual bbox)
                                                          │
                                                    YOLO-format export
                                                          │
                                              YOLOv8s fine-tune (Colab T4)
                                                          │
                                                  best.pt (22.5 MB)
                                                          │
                                          GitHub Release asset ◄── manual upload
                                                          │
                    ┌─────────────────────────────────────┴──────────────┐
                    ▼                                                    ▼
        Streamlit Cloud (server-side                          local OpenCV loop
        PyTorch inference, WebRTC)                            (laptop + DroidCam)
```

---

## 3. Why it did not work as a live app

Not a skill problem – an architecture problem. Every failure traces to one root
cause: **inference ran on a server, and the server was a free Streamlit
container.**

| Symptom | Cause |
|---|---|
| Live camera unusable on the hosted demo | `streamlit-webrtc` needs a TURN/STUN relay and a persistent worker; Streamlit Community Cloud gives neither. `app.py:591` has an `is_running_on_streamlit_cloud()` check that *disables* live mode and tells the user to run locally. |
| Frame drops / stalls | Every frame is round-tripped to a shared CPU container running PyTorch. `WasteDetectionProcessor` compensates with `skip_frames = 3` and a 1.0 s hard timeout that silently passes frames through unprocessed (`app.py:275-330`). |
| Cold starts | 22.5 MB checkpoint pulled from a GitHub release on first request, plus `ultralytics` + `torch` import cost. |
| One bin at a time | Not a model limit – the UI only surfaced the top detection. The detector was multi-object all along. |
| German-only labels | Class names *were* the UI strings. `WASTE_CATEGORIES` (`app.py:240`) keys on `"Biomüll"`, so the model vocabulary, the rules table, and the display language were the same object. |
| Deggendorf-only | Rules were a hard-coded Python dict with no notion of location. |
| 2.15 GB dataset for 466 images | Full-resolution phone JPEGs committed as a release asset, never resized. |

There is also a fourth-order problem: `show_training_page()` /
`train_model_simulation()` (`app.py:1344`, `:1479`) let a *web visitor* trigger
"training," which on a free container can only ever be a simulation. Impressive
in a demo, meaningless in production, and the kind of thing that has to go.

---

## 4. What carries forward

| Asset | Verdict | Where it lands |
|---|---|---|
| 466 labelled images | **Keep – this is the crown jewel.** Real, local, hand-labelled data. | Seed of the HF dataset, after resize + relabel. See [04-ml-pipeline](04-ml-pipeline.md). |
| YOLO bounding-box labels | **Keep, remap.** Four German class names → canonical form-factor + colour attributes. | `ml/src/sbr/dataset/legacy_import.py` |
| `waste_detector_best.pt` | **Keep as a baseline to beat, not a labeller.** It knows only four Deggendorf classes; using it as a teacher would propagate the jurisdictional bias this project exists to remove. | Benchmark reference |
| The presentation deck | **Keep as a reference, not a specification.** Problem statement, method, and evidence of taste. | [handoff/DESIGN-FOUNDATION.md](../handoff/DESIGN-FOUNDATION.md) |
| Disposal rules dict | **Concept keeps, data does not.** Becomes a versioned, translated, location-aware taxonomy. | [02-waste-taxonomy](02-waste-taxonomy.md) |
| Streamlit app | **Delete.** Wrong runtime, wrong deployment model, wrong language strategy. | – |
| Server-side PyTorch inference | **Keep the idea, fix the execution.** Inference is still server-side – but on a persistent process with a streaming protocol and hard client-side gating, not a request-per-frame round trip to a sleeping container. | [01-architecture](01-architecture.md) |
| In-app training page | **Delete.** Training belongs on Kaggle GPU kernels, dispatched from a laptop. | [04-ml-pipeline](04-ml-pipeline.md) |
| Colab + Google Drive | **Delete.** Replaced by HF Hub datasets + Kaggle kernels. | Same as CheXVision. |
| 2.15 GB release archive | **Delete.** Re-published as resized shards. | HF dataset repo |

---

## 5. The deck already knew

Slide 13, "Next Steps", verbatim:

- **Multi-language Support** – "to clear up sorting for every resident."
- **Mobile or Web Integration** – "so anyone can use it without the laptop workaround."
- **Partner with Deggendorf city / THD** – "to integrate services like pickup schedules."

Those three bullets are, in order, the product requirement, the architecture
decision, and the phase-3 roadmap of this repo. The predecessor diagnosed itself
correctly; it just did not have the runtime to act on the diagnosis.

---

## 6. Numbers to treat with suspicion

The `streamlit_app/README.md` performance tables are partly aspirational and
should **not** be quoted as this project's baseline:

- The inference-speed table (RTX 3090 156 FPS, Jetson Nano 15 FPS, iPhone 13
  45 FPS) lists hardware the team did not benchmark on.
- mAP@0.5 of 95.2 % on a 94-image validation split drawn from the same 466-photo
  session – same bins, same streets, same week – is an
  in-distribution number. It says the model memorised Deggendorf's bins well.
  It says nothing about Passau, let alone Lisbon.
- The root `README.md` claims 19.5 FPS on GPU while the app README claims 30+.

Real baselines get re-measured on a held-out, geographically disjoint split
before any number ships in this repo. See
[04-ml-pipeline § 7](04-ml-pipeline.md#7-evaluation).

---

## 7. Measured, 2026-08-01

Re-measured against the **complete** archive, after an earlier pass against an
incomplete copy was retracted in full (`54c13ec`). Everything below is
reproducible from `cv_garbage/` and supersedes the retracted figures.

### 7.1 The archive, as it really is

| | |
|---|---|
| `YOLO_Dataset/images/{train,val}` | 372 / 94 = **466** |
| `YOLO_Dataset/labels/{train,val}` | 372 / 94 – one label per image, no orphans |
| `raw_images/` | 470 (4 never made it through labelling) |
| `labeled/` | split by annotator: Alex 156, Fares 161, Sameer 149 = **466** |
| `models/` | **9 training runs**, not one |
| `data.yaml` | `nc: 4`, names `Biomüll, Glas, Papier, Restmüll` |

The counts finally reconcile with the deck: 466 images, 80/20, three people
sharing the labelling roughly evenly.

### 7.2 Which model is the real one

Nine runs survive, all fine-tuning `yolov8s.pt`. Best-epoch mAP@0.5 from each
run's own `results.csv`:

| run | epochs | imgsz | batch | rows | best mAP50 |
|---|---|---|---|---|---|
| `20250624_104047` | 100 | 640 | 8 | 1 | 0.4831 (abandoned) |
| `20250624_113052` | 50 | 960 | 16 | 50 | 0.9890 |
| `20250624_133331` | 50 | 960 | 16 | 50 | 0.9890 |
| `20250624_141930` | 50 | 960 | 16 | 50 | 0.9890 |
| `20250624_151654` | 50 | 960 | 16 | 33 | 0.9820 (stopped) |
| `20250624_155510` | 50 | 960 | 8 | 0 | – (never started) |
| **`20250625_1422522`** | **50** | **960** | **16** | **50** | **0.9906** ← production |
| `20250628_074316` | 50 | 960 | 4 | 0 | – (never started) |
| `20250628_0743162` | 50 | 960 | 4 | 6 | 0.9351 (abandoned) |

`20250625_1422522` is the one hard-coded at `2-Computer-Vision.py:500` and
released as `waste_detector_best.pt`. Note the deck's slide 10 says *batch
size 4*; the production run was actually **batch 16**. The batch-4 runs came
three days later and were both abandoned.

### 7.3 Independent validation

`best.pt` re-validated on the project's own 94-image val split, CPU, ARM64:

| imgsz | mAP50 | mAP50-95 | precision | recall |
|---|---|---|---|---|
| 960 | 0.9873 | 0.7767 | 0.9793 | 0.9479 |
| 640 | 0.9869 | 0.8349 | 0.9808 | 0.9220 |
| **448** | **0.9810** | 0.8078 | 0.9533 | 0.9271 |
| 320 | 0.9339 | 0.7185 | 0.9455 | 0.8648 |

Per class at 960: Biomüll AP50 0.9950, Glas 0.9950, Papier 0.9796, Restmüll
0.9794.

**This reproduces – and exceeds – the claimed 95.2 %.** It does not vindicate it.
It confirms § 6: the split is a random 20 % of one capture session, so 0.987 is
what memorising Deggendorf's bins looks like.

### 7.4 CPU latency

Single image, `torch.set_num_threads(4)` as a stand-in for a free-tier container:

| imgsz | p50 | p95 | fps |
|---|---|---|---|
| 960 | 406 ms | 599 ms | 2.5 |
| 640 | 260 ms | 676 ms | 3.8 |
| **448** | **174 ms** | **181 ms** | **5.8** |
| 320 | 135 ms | 143 ms | 7.4 |

**448 px is the operating point**, and this is the most directly useful result
in this section: it costs 0.6 mAP50 against 960 and runs 2.3× faster, with a p95
that barely exceeds its p50. 320 buys 22 % more speed for 4.7 mAP50 – a bad
trade. This is measured evidence for the 448 choice in
[01-architecture](01-architecture.md), which until now was an assumption.

Caveat: yolov8s is heavier than what the service will actually run, and an ARM64
Surface CPU is not an x86 container. Treat these as an upper bound on latency and
a lower bound on throughput.

### 7.5 The result that matters most

A six-image probe on out-of-distribution content – renders of the team's own
presentation slides:

| image | content | detections |
|---|---|---|
| `slide_01` | title, text on white | none ✅ |
| `slide_03` | section break, text on white | none ✅ |
| `slide_06` | map screenshot | **`Glas` 0.25** ❌ false positive |
| `slide_13` | timeline, text on white | **`Glas` 0.39** ❌ false positive |
| `slide_10` | terminal screenshot | none ✅ |
| `slide_08` | **three photographs of real bins** | **none** ❌ false negative |

The model hallucinates a glass container on a page of plain black text on white,
and simultaneously fails to find three actual bins that are visibly present –
because they appear small, inside a layout, at a scale it never trained on.

n = 6, so this is a probe and not a measurement. But the direction is
unambiguous and it is the empirical justification for the two-model design in
[01-architecture](01-architecture.md) and
[04-ml-pipeline](04-ml-pipeline.md):

- A single model trained only on centred, close-range, in-city bin photographs
  has **no concept of "not a bin"**. It was never shown one. Hence the negative
  corpus for the validator – that requirement is now evidence-backed, not
  a design instinct.
- 0.987 in-distribution and a false positive on a text slide are the *same
  finding*. The gap between them is exactly the gap the held-out-city split in
  [04-ml-pipeline § 7](04-ml-pipeline.md#7-evaluation) exists to expose.
- Scale generalisation is a named risk. Multi-scale augmentation and small-object
  cases belong in the validator's training set from the first run.
