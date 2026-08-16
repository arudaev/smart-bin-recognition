# 05 – Cost Model

> ⚠️ **This document was revised after the architecture changed to server-side
> inference.** The earlier version claimed €0/month at 10 000 MAU on the strength
> of on-device inference. That claim no longer holds, and pretending otherwise
> would be the most expensive kind of documentation error.

> Free-tier quotas move. Re-check Vercel, Hugging Face and Supabase before launch
> and at every traffic milestone. What matters below is the *shape*: which paths
> are free by construction, which have a ceiling, and where that ceiling is.

---

## 1. What changed

Moving inference to a server converts the dominant cost from **bandwidth**
(one-off model downloads) to **concurrency** (CPU seconds while people scan).
Those two scale completely differently:

| | On-device (rejected) | Server-side (chosen) |
|---|---|---|
| Cost driver | model download per install | CPU-seconds per scan |
| Scales with | installs | **simultaneous scanners** |
| Free ceiling | bandwidth quota | **vCPU of one small container** (see § 3) |
| Offline | works | does not |
| Model updates | cache invalidation problem | instant, universal |

The honest headline: **the constraint is now concurrency, and it binds much
sooner than bandwidth ever did.**

## 2. Where money goes

| Path | Frequency | Where | Marginal cost |
|---|---|---|---|
| App shell, JS, CSS | once per cold load | Vercel CDN | €0 |
| **Frame inference** | ~15 frames per scan | **HF Space CPU** | **€0 until saturated** |
| Rules, i18n, taxonomy | cached | Vercel CDN | €0 |
| Registry tiles | occasional | Vercel CDN, pre-baked | €0 |
| Map basemap | per map view | free tile provider | €0 |
| Sighting write | rare | Vercel fn + Supabase | ~€0 |
| **VLM auto-labelling** | batch, offline | **Kaggle GPU (open-weight)**, hosted API as fallback | **€0 by default; real and capped on the fallback** |
| Nightly tile rebuild | 1×/day | cron | ~€0 |

Reads are still free by construction: registry tiles are **pre-baked static
JSON** keyed by geohash-5, rebuilt nightly, served from CDN. No runtime database
query, at any traffic level.

## 3. The concurrency ceiling – the number that matters

> **Two hosts, not one.** They get discussed together and they are separate
> decisions:
>
> | | where latency is **measured** | where the service **runs** |
> |---|---|---|
> | | **Kaggle CPU kernel**, 2 pinned threads | **Cloud Run**, request-based |
> | | decided, built, working | decided 2026-08-16, not deployed |
>
> Kaggle kernels are batch jobs — no inbound network, no persistent process, no
> URL — so Kaggle can never be the serving host however convenient it is as the
> measuring one. Everything below is about the second column.

> **Correction, 2026-08-15.** This section used to open "A free Hugging Face
> Space gives **2 vCPU**." That is no longer true and the assumption was tested
> rather than assumed: creating a Docker Space returns `402 Payment Required` –
> *"Static Spaces are free for everyone, but hosting Gradio and Docker Spaces on
> free cpu-basic requires a PRO subscription."*
>
> **What survives:** the arithmetic below, which depends only on having 2 vCPU,
> not on who provides them. **What does not:** the claim that those 2 vCPU are
> free on Hugging Face, and therefore any statement here that the serving tier
> costs €0 without naming a host.
>
> **Resolved 2026-08-16** — the hosting hole below is closed. Argued in
> [research/05](research/05-serving-economics.md); recorded in
> [01 § 2](01-architecture.md#which-inference-host).
>
> | host | 2 vCPU? | cost | note |
> |---|---|---|---|
> | **Google Cloud Run, request-based** | yes, scales to zero | **free tier covers pilot scale** — *chosen* | needs a billing account on file, and **`POST /detect` rather than a socket** |
> | HF PRO | yes, cpu-basic | USD 9/month | the named upgrade if streaming proves necessary |
> | Cloud Run, instance-based | yes | small but non-zero | what a WebSocket actually costs |
> | HF Static Space | – | free | cannot run a server; no use here |
>
> **The detail that decided it.** Cloud Run's free tier — 2 M requests, 180 000
> vCPU-seconds, 360 000 GiB-seconds — applies to **request-based** billing, which
> charges CPU only while a request is in flight. A held-open WebSocket forces
> **instance-based** billing, where idle instances bill CPU and memory too; one
> always-on 2-vCPU instance consumes the whole monthly allowance in about 25
> hours. The socket was never free, and nothing above ever said it was: this
> section's arithmetic is about compute per frame and says nothing about idle
> time.
>
> So the pilot ships `POST /detect`, the client already supports it, and the
> result lock means a scan is ~15 frames either way.
>
> The ship gate is still measured on a **Kaggle CPU kernel with
> onnxruntime pinned to two threads** (`ml/kaggle/bench_latency/`), which is
> free and x86 but a *proxy*: `sbr.bench.Hardware.representative` is false for
> it, and `gate.py` refuses to decide on it without being told to.
>
> This note exists so that nobody re-derives "€0 serving" from a sentence that
> was true when it was written.

> **Measured 2026-08-16, and it is worse than this section used to say.**
> [Probe P4](research/probes/P4-multi-bin-cost-curve.md) ran the curve on a
> 2-vCPU CPU kernel. Two things came back: the frame costs more than budgeted,
> and **the arithmetic below had a factor-of-two error in it.**
>
> ```
> 2 vCPU ÷ 0.065 s  ≈  30 frames/second of total capacity    <- WRONG
> ```
>
> That treats 65 ms as *one core-second* of work which two cores can do twice
> over. It is not: it is a latency measured with onnxruntime **pinned to both
> cores**. Total capacity is `1 ÷ 0.065 ≈ 15` frames/second, not 30. Running two
> single-threaded workers instead roughly doubles each frame's latency and lands
> on the same total, because throughput is bounded by the CPU work either way.

> **MEASURED FOR REAL, 2026-08-17.** Everything below this line down to the next
> rule was *derived* from single-stream latency. The load test has now run
> against a pinned container, and it agrees:
>
> | bins/frame | predicted (P4) | **measured** | throughput |
> |---:|---:|---:|---:|
> | 1 | 4.3 – 5.1 | **4** | 15.8 – 16.0 frames/s |
> | 6 | 1.8 – 2.2 | **1** | 7.8 – 8.3 frames/s |
>
> Concurrent scanners whose **p95 stayed under 250 ms**, each running strict
> request-response at 3 fps. Host: `docker run --cpus 2`, `linux/arm64` native
> on a Snapdragon X1E80100 @ 3.40 GHz, onnxruntime 1.28.0. **Not
> representative**: Cloud Run is x86_64, so this is a second proxy rather than
> the tier itself – but a *pinned* one, which the Kaggle box was not. Reports in
> `artifacts/loadtest-{1,6}bin.json`.
>
> Measured throughput of 15.8 frames/s lands inside the corrected 13–15
> prediction, which is the strongest evidence the arithmetic error below is
> genuinely fixed.
>
> **The load test also found that the degradation ladder had never been
> reachable.** Inference blocked the event loop, so requests queued in the ASGI
> layer instead of arriving at the shedder: twelve concurrent scanners produced
> `peak_depth: 1` and not one rung fired. The service got slower and said
> nothing, which is the behaviour § 3 forbids by name. Fixed by separating
> admission from execution – the shedder counts everyone waiting, a semaphore
> bounds how many are inside onnxruntime. Rung 1 now fires at 5 concurrent
> scanners and rung 2 at 10.

Measured cost per frame, and the ceiling re-derived on it:

| bins in frame | CPU per frame | frames/s on 2 vCPU | concurrent scanners at 3 fps |
|---:|---:|---:|---:|
| 1 | **66–77 ms** | 12.9–15.2 | **4.3–5.1** |
| 3 | **89–108 ms** | 9.3–11.3 | 3.1–3.8 |
| 6 | **154–188 ms** | 5.3–6.5 | **1.8–2.2** |

```
one frame, one bin  ≈  66-77 ms on 2 pinned vCPU  (measured, not derived)
total capacity      ≈  13-15 frames/second
client cadence      ≈  3 frames/second per active scanner  (4 fps cap, ~3 achieved)
                    ─────────────────────────────────────
concurrent scanners ≈  4-5      at ONE bin per frame
                    ≈  2        at the six-container bank the PRD calls normal
```

**The honest headline is 1 to 4 concurrent scanners, not 3 to 10.** The phase-2
gate asks for ≥ 10 at one bin per frame; the measured figure is **4**, and at the
six-container bank the PRD calls a normal input it is **1**. Out by a factor of
2.5 at the easy end and by an order of magnitude at the realistic one.

The prediction and the measurement agree closely enough that neither rescues the
other. Ranges above are ranges because the *predicting* host was a shared Kaggle
kernel that varied ~25 % between runs six minutes apart; the measured figures
below them come from a pinned container and are single values.

The load test settles the concurrency question and does not settle the hardware
one: both hosts are proxies for Cloud Run's x86_64. The Snapdragon core is a
fast modern one, so if anything it flatters the result — a slower shared vCPU
would give fewer scanners, not more.

**Batching crops is not the lever this section thought it was.** P4 measured
1.24× at three crops and 1.10× at six — never the 2× that would have made it a
requirement. The identifier costs ~20 ms per crop whether batched or not, because
on two pinned threads it is arithmetic-bound and there is no per-call overhead to
amortise. The service batches anyway; the cost model may not lean on it. See
[01 § 4](01-architecture.md#latency-budget).

What is left, in order of cheapness: **drop the validator to 384 px** (it is a
third of a one-bin frame); **find the 15–40 ms per frame that belongs to neither
graph** and is most likely session switching; **cap crops harder** than the
default six, with the remainder deferred to the next frame.

The cadence figure is ~3 fps *achieved* against the **4 fps cap** in 01 § 4: the
cap is the guarantee, 3 is the average once the motion gate is working.

Four people scanning **at the same instant**, at one bin each. That sounds worse
than it is, because a scan is short:

- one scan ≈ 5 s of streaming, then the **result lock** stops it
- 4 concurrent × 5 s ⇒ ~2 900 scans/hour of headroom
- at ~2 scans/user/month ⇒ still **thousands to low tens of thousands of monthly
  users**, provided they are not all scanning simultaneously

At six bins per frame the same arithmetic gives one concurrent scanner and
~720 scans/hour, which is a pilot in one town and nothing beyond it.

So: **the headroom is real for a pilot in one town** – on 2 vCPU from whichever
host § 3 settles on. It was never real for a launch spike, and at four concurrent
scanners it would not survive being posted somewhere popular at 9 a.m. by a wider
margin than this document previously claimed.

This is why the client-side gates in
[01-architecture § 4](01-architecture.md#client-side-gating--the-thing-that-controls-cost)
are load-bearing infrastructure, not polish:

| Gate | Effect on capacity |
|---|---|
| Motion/stability gate | a still camera sends ~1 frame instead of ~12 |
| Result lock at 3 stable frames | caps a scan at ~15 frames instead of unbounded |
| 4 fps cadence cap | prevents fast phones from consuming more than their share |
| 20 s abort | bounds the worst case |

Without them a single user on a fast connection could consume a third of total
capacity by pointing their phone at a wall.

### Degradation, not failure

When the service saturates it must degrade honestly:

1. Queue depth crosses a threshold → **server tells clients to drop to 2 fps.**
2. Deeper → **live streaming disabled, tap-to-scan only.** Still works, still
   useful, visibly different.
3. Deeper still → **queue with a stated wait**, never a silent timeout.

The user-facing message says what is happening ("busy right now – tap to scan").
Never a spinner that lies.

## 4. Bandwidth

Not the binding constraint any more, but worth knowing:

| Item | Per scan | At 20 000 scans/month |
|---|---|---|
| Uplink frames (~30 KB × 15) | ~450 KB | ~9 GB |
| Downlink JSON (~1 KB × 15) | ~15 KB | ~0.3 GB |
| App shell (cached) | – | ~3 GB |
| Registry tiles + i18n | – | ~2 GB |

Uplink goes to the HF Space, not to Vercel, which is convenient: it does not
touch Vercel's quota at all.

## 5. The paid path, and how it stopped being one

**VLM auto-labelling** (step 4 of the labelling pipeline) was the only place this
system spent money. As of 2026-08-16 it does not have to.

**Default: an open-weight VLM on the free Kaggle GPU.** InternVL3 (MIT) and
Qwen3-VL are competitive on the constrained task we actually need — name the form
factor from a closed vocabulary, emit strict JSON against
`ml/src/sbr/escalation/schema.py`. We already have 30 h/week of Kaggle and the
dispatch path to use it; a batch labelling kernel is the same shape as
`build_negatives`. `escalation/schema.py` already treats the provider as
swappable, so this is configuration rather than redesign.
See [research/04](research/04-labelling-and-vlms.md);
[docs/12 probe P6](12-validation-protocol.md#p6--open-weight-vlm-for-batch-labelling)
measures schema-valid rate and agreement before this is relied on.

**Fallback: a hosted batch API**, kept because schema reliability under
constrained decoding is genuinely more mature there. If used, use the **batch
tier** — a flat 50 % discount on input and output — for which this design already
satisfies both preconditions.

The two properties below are why the fallback is safe either way:

1. It runs **offline in batch**, not in the user's request path. No user ever
   waits on it, and a spike in usage does not cause a spike in spend on the same
   day.
2. It is **capped by a hard integer**. When the cap is hit, the collection queue
   simply grows and is processed tomorrow. Coverage improves slower; nothing
   breaks and nothing overspends.

On the open-weight default: **€0**, capped by Kaggle's 30 h/week rather than by
money. On the hosted fallback at ~€0.002 per labelled crop with a cap of
3 000/month: **~€6/month at the ceiling** (~€3 on the batch tier), and near zero
at pilot volumes where the queue rarely fills.

Escalation-in-the-request-path – where a user waits while a VLM identifies their
bin live – remains **out of scope**. It is the one design that turns a usage spike
directly into a bill.

## 6. Cost decays as coverage grows

Unchanged from the original argument, and still the strongest property of the
design:

```
month 1, new city:   ~30 % of scans flag as novel   – the pack is empty
month 3:             ~8 %
month 6:             ~2 %
steady state:        <1 %                            – genuinely new bin types only
```

Each adjudicated flag produces a region-pack entry that answers *that appearance
in that jurisdiction* for every future user, free, forever. Labelling spend falls
while accuracy rises.

## 7. When it stops being free, and what to do

Ordered by cost, cheapest first. None needed for a pilot.

| Trigger | Response | Cost |
|---|---|---|
| Occasional saturation at peak | Tune gates; batch crops; drop model A to 384 px | €0 |
| Streaming becomes necessary | **HF PRO `cpu-basic`**, or Cloud Run instance-based | USD 9/mo |
| Sustained saturation | More vCPU on whichever host § 3 settled on (2→8) | ~€0.03/h, ~€20/mo |
| Sustained, predictable load | Move service to Fly.io / Hetzner CPU box | ~€5–15/mo |
| Real scale | GPU inference, batch frames across users | ~€50+/mo |
| Any of the above | **Municipal sponsorship** – geolocated bin data with staleness tracking is genuinely useful to a waste operator | the intended answer |

The upgrade path is deliberately gradual and the first two steps are cheap. There
is no cliff.

## 8. What we give up, stated plainly

- **No offline scanning.** The core loop needs a connection. Documented as a
  designed state, not hidden.
- **Cold start is a designed state, not a footnote.** Every free option scales to
  zero, so the first scan after a quiet period is slow — this is a property of
  the whole free tier, not an HF Space quirk. The "waking up" state is therefore
  load-bearing UI, and a cheap cron ping during likely hours is the mitigation.
- **Frames leave the device.** Requires the privacy handling in
  [01-architecture § 7](01-architecture.md#7-privacy) to be real, not decorative.
- **Concurrency is a hard ceiling, not a soft one.** Measured on a pinned
  2-vCPU container 2026-08-17: **four** simultaneous scanners at one bin per
  frame, and **one** at the bank of six the PRD calls a normal input. Not the
  ten this document asserted for a year, and not the four-to-five predicted
  from single-stream latency the day before. Plan launches around it.

Never: ads, selling user data, or paywalling the disposal rules. The rules are the
public good; behind a wall, the project has failed at its purpose.
