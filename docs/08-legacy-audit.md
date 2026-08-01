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
| The presentation deck | **Keep – it is the design brief.** Problem statement, method, and visual language. | [handoff/DESIGN-SYSTEM.md](../handoff/DESIGN-SYSTEM.md) |
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

## 7. Measured on CPU, 2026-08-01

`waste_detector_best.pt` was run locally on a Surface Pro 11 (Snapdragon X, ARM64,
Python under x64 emulation, **no GPU**) against the 64 images of its own
validation split. Model: yolov8s, 11.14 M params, 22.6 MB.

### Latency

| Input size | Median | p90 | Throughput |
|---|---|---|---|
| 448 px | 143 ms | 153 ms | 7.0 fps |
| 640 px | 213 ms | 240 ms | 4.7 fps |
| 960 px | 373 ms | 406 ms | 2.7 fps |

Sobering in a useful way: even an emulated ARM laptop CPU manages ~7 fps on an
11 M-param model. A YOLO11n validator (~2.6 M) on a non-emulated x86 service CPU
has ample headroom. This is the measurement that makes the server-side design in
[01-architecture](01-architecture.md) credible rather than hopeful.

### Accuracy on its own validation split

Class-aware, count-matched, `conf=0.25`, `imgsz=960`:

```
TP 67   FP 19   FN 1
precision 0.779    recall 0.985
images with >=1 detection:  64/64 = 100.0 %

confusion (single-bin images, ground truth -> top prediction)
              Biomüll      Glas    Papier  Restmüll
  Biomüll          11         0         0         0
  Glas              0        10         0         0
  Papier            0         0        15         0
  Restmüll          0         0         0        24
```

**Three findings, and they shape this project's architecture:**

1. **Detection is effectively solved.** Every validation image produced at least
   one box; recall 0.985. Finding a bin is not the hard problem.
2. **Classification is perfect – and that is the warning.** A flawless diagonal
   on 60 images means memorisation of one week's bins in one town, not
   generalisation. It is exactly the number you would expect from an
   in-distribution split, and exactly the number that will collapse in Passau.
3. **Precision 0.779 – 19 false positives.** The model over-fires on things that
   are not labelled bins. Some are probably real unlabelled bins in frame; the
   rest are the hard negatives a dedicated validator needs to be trained against.

Together these are the empirical case for the two-model split in
[01-architecture § 3](01-architecture.md#3-two-models-and-why): keep the
near-saturated detection as a **trustworthy validator**, and treat identification
as the fragile part that the improvement loop exists to feed.

### What the archive actually contains

The layout does not match the predecessor's own README:

| | |
|---|---|
| Images | 427, in `labeled/{Alex,Fares,Sameer}/` – **not** in the YOLO tree |
| Labels | 401 files, 436 boxes, in `YOLO_Dataset/labels/` |
| `YOLO_Dataset/images/` | 16 files – effectively empty |
| Link between the two | hash suffix in filename; `_pairs.json` holds 368 mappings |
| Images with >1 bin | **31 of 401 (7.7 %)** |
| Class balance | Restmüll 180 · Papier 112 · Biomüll 99 · **Glas 45** |

The last two rows matter for planning. **Multi-bin scenes are nearly absent from
the training data**, so the predecessor's one-bin-at-a-time behaviour was partly a
data property and not purely a UI limitation – new collection has to deliberately
target banks and rows of containers. And **Glas is under-represented 4:1**
against Restmüll, which is consistent with the deck calling it the biggest
problem.

Reproduce with `ml/scripts/benchmark_legacy.py`.
