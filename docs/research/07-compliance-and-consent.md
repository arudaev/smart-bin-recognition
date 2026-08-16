# 07 – Compliance and consent

*2026-08-16. Feeds docs/01 § 7 (privacy) and docs/03 § 4 (contributions).*

> Not legal advice. This is an engineering note about which obligations plausibly
> attach to this design, written so the consent lifecycle can be specified rather
> than deferred.

---

## 1. The date already passed

EU AI Act Article 50 transparency obligations took effect **2 August 2026** —
two weeks before this note. This is no longer future work for an EU-facing
product. Penalties for non-compliance run to €15 M or 3% of worldwide turnover;
irrelevant at our scale in practice, entirely relevant to whether a university or
a municipality will touch the project.

What Article 50 principally requires is disclosure where an AI system interacts
with people, and marking of AI-generated or manipulated content. **Our exposure
is low by construction**: we do not generate content, we do not synthesise media,
and the app is visibly a camera-and-recognition tool.

The obligations that do bite are the ones the design already leans towards and
should now state explicitly:

- the user is told a model produced the identification, not a database;
- confidence and `unknown` are surfaced rather than hidden — docs/00 principle 3
  already commits to this;
- an answer traceable to a cited municipal source, which docs/02 § 4's pack
  format already carries.

Separately, GDPR applies to contributed frames independently of the AI Act, and
data protection authorities are actively enforcing it against AI systems.

## 2. Where the design is already strong

Genuinely good, and worth keeping visible in any write-up:

- **no user identity at all** — no accounts (docs/00 § 4, permanently out of
  scope), so there is no personal data to associate a frame with;
- **geohash-6 (~1.2 km)** rather than coordinates on the common path;
- frames **processed in memory and discarded** by default;
- retention is **opt-in and per-session**;
- retained frames downscaled and EXIF-stripped.

That is a stronger privacy posture than most consumer camera apps, and it was
chosen before it was required.

## 3. Where it is vague, and why that now matters

docs/01 § 7 says consent is "per-session and visible". Everything after that word
is missing:

| Unspecified | Why it matters |
|---|---|
| **When is consent asked?** Before the camera opens, or at the moment a frame is worth keeping? | Asking up-front trains people to dismiss it; asking at the moment is honest but interrupts the answer |
| **How long is a frame retained?** | GDPR storage limitation needs a stated period, not "until reviewed" |
| **How does someone delete a contribution?** | With no identity there is no account to delete from — this needs a design, e.g. a local contribution receipt |
| **How does a contributor learn what happened to it?** | docs/00 § 9.4 defaults to "visible to the contributor only, marked pending" and stops there |
| **Does consent cover only flagged frames, or the session?** | The distinction between "keep this one frame" and "keep frames from this session" is the whole consent scope |

docs/03 § 4 additionally assumes **auto-reject on face/plate detection**. That is
an unscoped ML component sitting in a privacy guarantee. Either it is built and
measured, or the guarantee is restated as human moderation before retention —
which is what actually happens today.

## 4. A consent lifecycle that fits the design

Proposed, for docs/03 to ratify. It follows from decisions already made:

```
scan  →  answer shown  →  was this frame worth keeping?
                                    │ no → discarded, nothing asked, no interruption
                                    │ yes
                                    ▼
                          ask once, at the moment, naming what and why
                                    │ declined → discarded; never asked again this session
                                    │ granted
                                    ▼
                downscale ≤ 512 px · strip EXIF · geohash-6 only · local receipt
                                    │
                                    ▼
                 pending queue, stated retention window, human review
                                    │
                          ┌─────────┴─────────┐
                     accepted              rejected
                 dataset revision        deleted at review
```

Three properties worth defending: the ordinary successful scan **never sees a
consent prompt** (docs/04 § 2 already discards those frames, so there is nothing
to consent to); the prompt names *this frame* rather than a policy; and the
**local receipt** gives deletion a mechanism without inventing an identity —
the device holds a token that can revoke a specific pending contribution.

## 5. What this changes for us

| Change | Where |
|---|---|
| Specify the consent lifecycle above as a designed state machine | docs/03 § 4 |
| State a retention window for pending frames, and a deletion path via local receipt | docs/03 § 4, docs/01 § 7 |
| Either scope face/plate auto-rejection as real work, or restate the guarantee as human moderation | docs/03 § 4 |
| Record that Art. 50 is in force and that our exposure is disclosure, not content marking | docs/00 § 8 (risks) |
| Keep "no identity" listed as a *compliance asset*, not just a scope decision | docs/03 |

## Sources

- [EU AI Act transparency obligations, 2 Aug 2026 (Cooley)](https://www.cooley.com/news/insight/2026/2026-08-03-eu-ai-act-transparency-obligations-take-effect-2-august-2026)
- [Preparing for Art. 50 compliance (Sidley)](https://datamatters.sidley.com/2026/06/24/eu-ai-act-transparency-obligations-preparing-for-compliance-by-2-august-2026/)
- [Art. 50: what providers and deployers must do (Symmetry)](https://www.symmetrycompliance.ie/eu-ai-act-article-50-transparency-obligations-what-ai-providers-and-deployers-must-do-before-2-august-2026/)
- [European Commission: safer and more transparent AI](https://commission.europa.eu/news-and-media/news/safer-and-more-transparent-ai-2026-08-02_en)
