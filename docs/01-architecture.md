# 01 – Architecture

> Inference runs **on a server**, reached over a streaming connection. The client
> is thin: it captures frames, gates them, sends them, and draws boxes.

---

## 1. The decision

No model is downloaded to the user's device. No WebGPU, no ONNX Runtime Web, no
multi-megabyte cache sitting on every phone that ever opened the app. The camera
loop and the map both require a connection, and that is accepted.

**Why this and not on-device:**

- A per-device model download is a per-device cost in bandwidth and storage, and
  it grows with every install and every model version. Server-side inference
  ships the model **once**, to one place.
- Model updates are instant and universal. No cache invalidation, no version
  skew across a user base, no "which model version produced this answer".
- The server can run a model too large for a phone, which matters for the
  identifier (§ 3), and can run two models in sequence without a device budget.
- Old phones stay fast because they do no inference at all. A 2019 Android does
  the same work as a flagship: capture, compress, send, draw.

**What it costs:**

- **No offline.** The scan does not work without a connection. The rules browser
  and cached region data still do; the camera and the map do not.
- **Latency is network-bound**, not compute-bound. Budget below.
- **Concurrency is the real ceiling**, not bandwidth. See
  [05-cost-model](05-cost-model.md) – this is the honest constraint, and it is
  the one that decides when money starts being spent.
- Frames leave the device, so there is a genuine privacy story to write and
  honour (§ 6).

## 2. Topology

```
┌── DEVICE ──────────────────────────┐
│  getUserMedia → <canvas>           │
│  downscale 448px, JPEG q70 (~30 KB)│
│  motion + stability gate  ◄──────┐ │   only send when the scene changed
│         │                        │ │
│         ▼                        │ │
│   WebSocket ──── frame ──────────┼─┼──────────►  INFERENCE SERVICE
│    (or POST /detect)             │ │            2 vCPU; host per § 2
│                                    │            FastAPI + ONNX Runtime
│   draw boxes · result cards        │                  │
└────────────────────────────────────┘            Model A → Model B
              │                                          │
              │  REST                                    ▼
              ▼                                   detections JSON
   VERCEL (frontend + thin API)                   {box, form_factor,
   · /api/pack/:geohash   registry tiles           colours, stream,
   · /api/sighting        writes (Turnstile)       confidence, novelty}
   · /api/escalate        VLM, capped
              │
              ▼
   Postgres + PostGIS (Supabase)  ──nightly──►  static registry tiles
```

**Three hosts, each doing what it is cheapest at:**

| Host | Runs | Why there |
|---|---|---|
| **Vercel** (Hobby) | React frontend, thin serverless API, registry tiles | Free static + edge; already the deployment target for THD Room Finder |
| **Inference host** *(see below)* | FastAPI + ONNX Runtime, models A and B | Needs a **persistent process**, which Vercel functions are not |
| **Supabase** (free) | Registry Postgres + PostGIS | Real geo queries; free tier is generous |

Vercel serverless functions cannot hold a WebSocket – they are stateless and
time-limited. That is the specific reason inference does not live on Vercel.

### Which inference host

**Not Hugging Face on the free tier, which is what this table used to say.**
Creating a Docker Space returns `402 Payment Required`: hosting Gradio and
Docker Spaces on free `cpu-basic` now requires PRO. Recorded in
`ml/src/sbr/bench.py` and [05 § 3](05-cost-model.md#3-the-concurrency-ceiling--the-number-that-matters).

The replacement decision, argued in
[research/05](research/05-serving-economics.md):

| | Host | Cost | Trade |
|---|---|---|---|
| **Pilot** | **Cloud Run, request-based billing, `POST /detect` primary** | free tier applies | no live streaming |
| Upgrade | HF PRO `cpu-basic` | USD 9/mo | restores streaming exactly as designed |

The detail that decides it: Cloud Run bills **request-based** (CPU only while
handling a request; 180 000 vCPU-seconds free) or **instance-based** (CPU and
memory on idle instances too). **A held-open WebSocket forces instance-based**,
and one always-on 2-vCPU instance exhausts the monthly free allowance in about
25 hours. The socket was never free; the arithmetic in 05 § 3 was about compute
per frame and never about idle time.

So the streaming loop below is the **design**, and single-frame `POST /detect`
is the **pilot deployment** of it. The client already carries both
(`VITE_DETECT_WS` / `VITE_DETECT_URL`), and the result lock means a scan is ~15
frames either way.

## 3. Two models, and why

**This is the core of the design.** Recognising *that* something is a bin and
recognising *which* bin it is are different problems with different difficulty,
and fusing them is what made the predecessor brittle.

The working hypothesis is that **detection is far easier than identification**:
finding a bin-shaped object generalises across cities, while knowing which bin it
is does not. This is stated as a hypothesis on purpose – it has **not** been
measured yet, and the phase-2 spike exists to test it
([07-roadmap](07-roadmap.md)). If it turns out false, the split still costs
little; if it holds, it is what makes the improvement loop work.

So:

| | **Model A – Validator** | **Model B – Identifier** |
|---|---|---|
| Question | "Is there a bin, and where?" | "What kind of bin is it?" |
| Classes | 1 (`bin`), class-agnostic | 10 form factors |
| Input | full frame | **crop from A's box** |
| Trained on | all bin images **+ a large negative corpus** | curated, labelled bins only |
| Target | ≥ 99 % detection, very low FP | best achievable |
| Runs | every gated frame | only where A fired |
| Fails by | missing a bin (rare) | saying `unknown` (expected, and useful) |

Model A sees mostly **negatives**: random street scenes from an open image
corpus plus deliberate hard negatives – postboxes, planters, parked cars,
utility cabinets, recycling logos on non-bins. That is what buys the low false
positive rate, and it is cheap data that needs no waste-domain labelling.

Running B on A's **crop** rather than the full frame is also an accuracy win:
the crop is normalised, centred and background-free, so colour measurement is
taken from the object instead of from whatever was behind it.

### The disagreement signal

The two models disagreeing is not a failure. It is the acquisition function for
new training data, and it is free:

| Model A | Model B | Meaning | Action |
|---|---|---|---|
| confident bin | confident form factor, pack resolves | normal | show answer |
| **confident bin** | **unknown / low confidence** | **a bin type we have never seen** | **flag for collection – highest value** |
| confident bin | confident, but user corrects | mislabelled or region rule wrong | flag, weight highly |
| no detection | – | user reports a bin anyway | detector gap – flag |
| any | any | **geohash cell never seen before** | flag regardless of confidence |

A high-precision validator makes "B is wrong here" a *trustworthy* signal, which
is exactly what an active-learning loop needs. Without model A you cannot tell
"unfamiliar bin" from "not a bin".

### Debug mode

A toggle (contributors and dev builds) renders **both** models: A's boxes in one
weight, B's in another, with confidences and the novelty verdict. This is the
tool for understanding why a location is failing, and it is the interface to the
data-collection loop rather than a developer toy.

## 4. Streaming protocol

**WebSocket, strict request-response.** The client sends the next frame only
after receiving the previous result. This is deliberate: it makes backpressure
automatic, prevents queue build-up under load, and self-throttles on slow
connections without any explicit rate logic.

```
client → server   { seq, jpeg: <binary>, geohash6, locale, debug? }
server → client   { seq, ms, detections: [
                      { box, validator_conf,
                        form_factor, identifier_conf,
                        body_colour, lid_colour,
                        stream, stream_conf, local_name,
                        novelty: none|unknown_type|new_region }
                    ] }
```

`POST /detect` exists for tap-to-scan, upload, and any client that cannot hold a
socket. Same payload, one frame.

### Client-side gating – the thing that controls cost

Frames are expensive; not sending them is free. Four gates, in order:

1. **Motion / stability.** A cheap luma diff on a 64×64 downsample. If the scene
   has not changed materially, do not send – reuse the last result. Pointing at
   a stationary bin costs almost nothing after the first frame.
2. **Cadence cap.** Never more than 4 frames/second regardless of network.
3. **Result lock.** Once the same identification holds across 3 consecutive
   results, **stop streaming** and present the answer. A scan is a task with an
   end, not an infinite loop. This is the single biggest saving.
4. **Hard stops.** Pause on `visibilitychange`; abort after 20 s of streaming
   with no confident result and fall back to tap-to-scan.

Realistic scan: ~5 s of streaming, ~15 frames, ~450 KB, then lock.

### Latency budget

Target budget, to be confirmed by measurement in phase 2:

| Stage | Budget |
|---|---|
| Capture + downscale + encode | ~15 ms |
| Uplink (30 KB, 4G) | ~60 ms |
| Model A @ 448 | ~40 ms |
| Model B, **per crop** | ~25 ms |
| Resolve + downlink | ~25 ms |
| **Round trip, one bin** | **~165 ms → ~6 fps, capped at 4** |

Good enough. The perceived experience is carried by box smoothing and the result
lock, not by raw frame rate.

**Model B is per crop, and that is not free.** A bank of six containers — which
[00-PRD § 4](00-product-requirements.md#4--scope--v1-mvp) calls a normal input —
costs `40 + 6×25 = 190 ms` of service CPU, roughly three times the one-bin frame.
docs/04 § 1's "multi-bin scenes are free" is true of **accuracy** (N independent
crops, no crowding in the detector head) and false of **cost**, which is linear
in bins. The two were stated as one property until 2026-08-16.

Consequences: the concurrency ceiling in
[05 § 3](05-cost-model.md#3-the-concurrency-ceiling--the-number-that-matters) is
a range over scene complexity, not a single number; and batching the crops
through one ONNX call rather than *n* sequential ones is a **service
requirement**, not an optimisation. [docs/12 probe P4](12-validation-protocol.md#p4--multi-bin-cost-curve)
measures both — and needs no trained model to do it.

## 5. Device tiers

Capability probe, never user-agent.

| Tier | Probe | Experience |
|---|---|---|
| **Scanner** | `getUserMedia` + an `environment`-facing camera | Live streaming scan |
| **Viewer + capture** | camera present, front-facing only | Still capture / upload → `POST /detect`; no live loop |
| **Viewer** | no camera, or denied | **No camera UI at all.** Map, registry, rules search, contributor tools |

Desktop gets no camera, ever – and in exchange gets the richer surface: map with
filters, `last_verified` staleness, edit history, and the moderation queue.

## 6. What works without a connection

Stated plainly, because the app must not lie about this:

| Works offline | Does not |
|---|---|
| Rules browser, all streams and items | **Camera scan** |
| Cached region pack for a visited area | **Map** |
| Locale bundles | Registry reads outside cache |
| Queued contributions (flush on reconnect) | Escalation |

Offline is a **stated, designed state** with an honest message – "Scanning needs
a connection" – not a red error banner and not a silent failure.

## 7. Privacy

Frames leave the device, so this has to be deliberate:

- Frames are **processed in memory and discarded**. Nothing is written to disk on
  the inference service by default.
- A frame is **retained only when it is flagged for collection** (§ 3) *and* the
  user has consented. Consent is asked **per frame, at the moment**, naming that
  frame and why it is worth keeping — not once per session as a blanket. An
  ordinary successful scan never sees the prompt, because there is nothing to
  consent to: the frame is already discarded (docs/04 § 2). The full lifecycle,
  including retention window and deletion, is
  [03 § 4](03-registry-geo-trust.md).
- Retained frames are downscaled, EXIF-stripped, and reviewed before entering any
  dataset.
- Deletion works without an identity: the device keeps a **local receipt** for
  each pending contribution, and the receipt revokes it. That is what makes
  "no accounts" compatible with a real deletion path rather than an excuse for
  not having one.
- Location sent with a frame is **geohash-6 (~1.2 km)** – enough to select a
  jurisdiction, not enough to locate a household. Precise coordinates are sent
  only on an explicit registry contribution.
- No frame is ever associated with a user identity. There is no user identity.

## 8. Repository layout

```
smart-bin-recognition/
├── web/                 React + TS + Vite (Vercel)
│   ├── src/
│   │   ├── capture/     camera, downscale, motion gate, WS client, result lock
│   │   ├── domain/      resolver, taxonomy types, geo – framework-free
│   │   ├── data/        pack client, IndexedDB cache, contribution queue
│   │   ├── features/    scan / result / map / registry / rules / contribute
│   │   ├── components/  design-system components
│   │   ├── i18n/        locale bundles
│   │   └── styles/      tokens
│   └── api/             Vercel serverless: pack, sighting, escalate
├── service/             FastAPI + ONNX inference service (HF Space)
│   ├── app.py           WS /stream + POST /detect
│   ├── pipeline.py      model A → crop → model B → resolve → novelty
│   └── Dockerfile
├── ml/                  Python: dataset, training, export, dispatch
├── data/taxonomy/       canonical streams + region packs
└── docs/
```

Layering rule: `features → components → data → domain`, and **`domain/` imports
no framework**. The resolver runs identically in the browser and in
`service/pipeline.py`; the Python implementation in `ml/src/sbr/taxonomy.py` is
the reference and is unit-tested.
