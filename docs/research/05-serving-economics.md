# 05 – Serving economics

*2026-08-16. Feeds docs/01 § 2 (host table) and docs/05 § 3 (the open hosting
decision).*

docs/05 § 3 has carried an explicit hole since 2026-08-15: free Hugging Face
Docker Spaces return `402 Payment Required`, so the arithmetic survives but the
host does not. Phase 3 cannot deploy into an undecided host. This note closes the
hole.

---

## 1. The detail that actually decides it: Cloud Run's two billing modes

Cloud Run bills one of two ways, and **our transport chooses the expensive one**:

| Mode | Billed | Fits |
|---|---|---|
| **Request-based** (default) | CPU only while handling a request | typical HTTP APIs with idle gaps |
| **Instance-based** (`--no-cpu-throttling`) | CPU *and* memory on idle instances too | WebSockets, background work, persistent connections |

The free tier is 2 M requests, 180 000 vCPU-seconds and 360 000 GiB-seconds per
month **under request-based billing**. A held-open WebSocket — docs/01 § 4's
whole transport — forces instance-based, where an idle instance still bills. 180
000 vCPU-seconds is 50 vCPU-hours; one always-on 2-vCPU instance consumes that in
about 25 hours. **A permanently-open socket service does not fit the Cloud Run
free tier**, and it never did; the arithmetic in docs/05 § 3 was about *compute
per frame* and never about idle time.

This is the single most useful thing in this note, and it was invisible until
someone read the billing modes rather than the free-tier headline.

## 2. The options, honestly

| Option | Cost | What it buys | What it costs |
|---|---|---|---|
| **`POST /detect` primary, Cloud Run request-based** | plausibly €0 at pilot | the free tier actually applies; scales to zero | no live streaming; tap-to-scan is the main loop |
| **HF PRO, cpu-basic Space** | **USD 9/month** | restores the original design exactly — persistent process, WebSocket, 2 vCPU | the €0 claim becomes "€0 infrastructure, $9 hosting" |
| **Cloud Run instance-based, min-instances 0** | small but non-zero | streaming, scale-to-zero between sessions | cold starts on every idle gap; billing needs a card on file |
| Fly.io / Hetzner small box | ~€5–15/mo | full control, no cold start | a machine to maintain |

Note the free HF **CPU basic** tier (2 vCPU, 16 GB) is still advertised as free in
general write-ups. Our `402` is the empirical fact and it is what
`ml/src/sbr/bench.py` records; the advertised tier and the observed one disagree,
and **the observed one wins**. Re-test before committing money.

## 3. The recommendation

**Make `POST /detect` the primary path and streaming the enhancement.** Three
reasons, only one of which is cost:

1. It fits the one genuinely free billing mode.
2. The client already supports it. `VITE_DETECT_URL` exists, tap-to-scan is
   built, and docs/01 § 4 already specifies `POST /detect` "for tap-to-scan,
   upload, and any client that cannot hold a socket".
3. **The result lock means a scan is already short.** docs/01 § 4's realistic
   scan is ~15 frames then lock. The gap between "15 posts" and "15 frames over a
   socket" is much smaller than the gap between their billing models.

Keep the socket as the upgrade for when there is a host that suits it — $9/month
HF PRO is not a hard decision if streaming proves to matter.

## 4. Cold start is a product state, not a footnote

Both scale-to-zero options pay a cold start. docs/05 § 8 already commits to "an
honest 'waking up' state rather than a spinner", which is the right answer and is
already designed. What changes: cold start moves from "an HF Space quirk" to **a
property of every free option**, so the waking state is load-bearing rather than
defensive.

## 5. What this changes for us

| Change | Where |
|---|---|
| Close the hosting hole: `POST /detect` on Cloud Run request-based is the pilot target; HF PRO at $9/mo is the named fallback if streaming proves necessary | docs/05 § 3 |
| Fix the host table — "HF Space (free CPU) … Free, persistent process" is no longer true | docs/01 § 2 |
| Fix the upgrade ladder — "HF Space CPU upgrade 2→8 vCPU" steps up from a tier that does not exist | docs/05 § 7 |
| Record *why* WebSockets are expensive on serverless, so nobody re-derives "free streaming" | docs/05 § 3 |
| Promote the waking state from mitigation to designed state | docs/05 § 8 |
| Re-price concurrency on measured multi-crop cost, not one assumed crop | docs/05 § 3, probe **P4** |

## Sources

- [Cloud Run pricing](https://cloud.google.com/run/pricing) · [cost-optimised services](https://docs.cloud.google.com/run/docs/tips/services-cost-optimization) · [pricing guide](https://cloudchipr.com/blog/cloud-run-pricing)
- [Hugging Face pricing 2026](https://www.eesel.ai/blog/hugging-face-pricing)
- Empirical: `402 Payment Required` on Docker Space creation, recorded in `ml/src/sbr/bench.py` and docs/05 § 3
