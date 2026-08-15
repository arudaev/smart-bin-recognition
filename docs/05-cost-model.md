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
| **VLM auto-labelling** | batch, offline | Anthropic/OpenAI | **real, capped** |
| Nightly tile rebuild | 1×/day | cron | ~€0 |

Reads are still free by construction: registry tiles are **pre-baked static
JSON** keyed by geohash-5, rebuilt nightly, served from CDN. No runtime database
query, at any traffic level.

## 3. The concurrency ceiling – the number that matters

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
> Candidate hosts, none yet committed:
>
> | host | 2 vCPU? | cost | note |
> |---|---|---|---|
> | Google Cloud Run | yes, scales to zero | free tier covers pilot scale | needs a billing account on file |
> | HF PRO | yes, cpu-basic | USD 9/month | restores the original design exactly |
> | HF Static Space | – | free | cannot run a server; no use here |
>
> Until one is chosen, the ship gate is measured on a **Kaggle CPU kernel with
> onnxruntime pinned to two threads** (`ml/kaggle/bench_latency/`), which is
> free and x86 but a *proxy*: `sbr.bench.Hardware.representative` is false for
> it, and `gate.py` refuses to decide on it without being told to.
>
> The hosting decision belongs to phase 3. This note exists so that nobody
> re-derives "€0 serving" from a sentence that was true when it was written.

With model A at ~40 ms and model B at ~25 ms per crop, one frame costs roughly
**65 ms of CPU** on 2 vCPU.

```
2 vCPU ÷ 0.065 s  ≈  30 frames/second of total capacity
client cadence     ≈  3 frames/second per active scanner
                   ─────────────────────────────────────
concurrent scanners ≈ 10        (before latency degrades)
```

Ten people scanning **at the same instant**. That sounds small until you convert
it into users, because a scan is short:

- one scan ≈ 5 s of streaming, then the **result lock** stops it
- 10 concurrent × 5 s ⇒ ~7 000 scans/hour of headroom
- at ~2 scans/user/month ⇒ comfortably **tens of thousands of monthly users**,
  provided they are not all scanning simultaneously

So: **the concurrency headroom is real for a pilot and for organic growth in one
or two towns** – on 2 vCPU from whichever host § 3 settles on. It is
not real for a launch spike, and it would not survive being posted somewhere
popular at 9 a.m.

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

## 5. The paid path

**VLM auto-labelling** (step 4 of the labelling pipeline). Two properties make it
safe:

1. It runs **offline in batch**, not in the user's request path. No user ever
   waits on it, and a spike in usage does not cause a spike in spend on the same
   day.
2. It is **capped by a hard integer**. When the cap is hit, the collection queue
   simply grows and is processed tomorrow. Coverage improves slower; nothing
   breaks and nothing overspends.

At ~€0.002 per labelled crop and a cap of 3 000/month: **~€6/month at the
ceiling**, and near zero at pilot volumes where the queue rarely fills.

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
| Occasional saturation at peak | Tune gates; drop model A to 384 px | €0 |
| Sustained saturation | **HF Space CPU upgrade** (2→8 vCPU) | ~€0.03/h, ~€20/mo |
| Sustained, predictable load | Move service to Fly.io / Hetzner CPU box | ~€5–15/mo |
| Real scale | GPU inference, batch frames across users | ~€50+/mo |
| Any of the above | **Municipal sponsorship** – geolocated bin data with staleness tracking is genuinely useful to a waste operator | the intended answer |

The upgrade path is deliberately gradual and the first two steps are cheap. There
is no cliff.

## 8. What we give up, stated plainly

- **No offline scanning.** The core loop needs a connection. Documented as a
  designed state, not hidden.
- **A cold Space costs ~30 s.** A free Space sleeps after inactivity. First scan
  of the day may be slow. Mitigations: a cheap cron ping during likely hours, and
  an honest "waking up" state rather than a spinner.
- **Frames leave the device.** Requires the privacy handling in
  [01-architecture § 7](01-architecture.md#7-privacy) to be real, not decorative.
- **Concurrency is a hard ceiling, not a soft one.** Ten simultaneous scanners is
  the number. Plan launches around it.

Never: ads, selling user data, or paywalling the disposal rules. The rules are the
public good; behind a wall, the project has failed at its purpose.
