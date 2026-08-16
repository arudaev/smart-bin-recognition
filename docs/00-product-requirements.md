# 00 – Product Requirements

**Smart Bin Recognition** – point your phone at a bin, learn what it is and what
goes in it, in your language, anywhere.

Status: draft v1, 2026-08-01. Owner: Alexander Rudaev.

> ⚠️ **Revised 2026-08-16.** § 3.4, § 3.6 and § 4 described **on-device
> inference with no upload**. That was true when written and is no longer the
> design: [01-architecture § 1](01-architecture.md#1-the-decision) moved
> inference to a server, deliberately and with the costs written down. The
> earlier claims are corrected below rather than deleted, because a requirements
> document that quietly changes what it promised is worse than one that shows
> its working. [05-cost-model § 1](05-cost-model.md#1-what-changed) records the
> same change from the cost side.
>
> The document also contradicted **itself**: § 3.4 required the core loop to work
> with no signal while § 7 already allowed scanning to need a connection. § 7 was
> right.

---

## 1. Problem

From the predecessor's own problem slide, which still states it best:

> International students struggle with the German waste sorting system.
> Different coloured bins have specific rules that are often explained only in
> German, making it difficult to know what goes where. This leads to confusion,
> improper sorting, and potential fines when bins are contaminated with the
> wrong materials.

Three things generalise this beyond Deggendorf and beyond students:

- **Colour coding is not standardised.** It varies by country, by federal state,
  and sometimes by contractor within one city. Knowing "blue is paper" in one
  town actively misleads you in the next.
- **The information exists but is unreachable at the moment of need.** Every
  municipality publishes a waste guide. It is a German-language PDF, and you are
  standing outside in the rain holding a yoghurt pot.
- **Bins move.** Household bins are wheeled in and out, sheds get locked, glass
  banks appear next to new offices. Any static map is wrong within a year.

## 2. Who it is for

| Persona | Need | Primary surface |
|---|---|---|
| **Newly arrived resident** (student, worker, refugee) | "What is this bin and can my thing go in it?" – in their language, right now | Phone, scan |
| **Established resident** | "Which day does paper go out?" / "Where is the nearest glass bank?" | Phone, map + calendar |
| **Contributor** | Improve coverage for their town | Phone capture, desktop moderation |
| **Municipality** *(later)* | See where bins are and where residents are confused | Desktop, aggregate view |

Not for: waste-management professionals, industrial sorting, item-level
recycling classification of the *contents* of your hand.

## 3. Product principles

1. **Answer first.** The screen leads with the bin's identity and a yes/no-shaped
   rule list. Confidence scores, model names and technical state are secondary.
2. **Your language, not the bin's.** German words appear only when they are the
   proper noun on the physical object, and always with a translation.
3. **Honest about uncertainty.** "I don't know this bin" is a first-class,
   well-designed result, not an error state. It is also the entry point to
   contributing.
4. **Honest about the connection.** The rules browser, the item vocabulary and a
   cached region pack work with no signal, and a basement bin room is exactly why.
   **Scanning and the map do not** – inference is server-side
   ([01 § 1](01-architecture.md#1-the-decision)) – and the app says so as a
   designed state rather than failing silently.
5. **Costs nothing to run, forever.** Any feature that scales in price with
   users is either redesigned or cut. This is a hard constraint, not a preference.
6. **Nothing is kept unless the user chooses.** Frames are sent for recognition,
   held in memory, and discarded. **Retention** – not transmission – is the
   explicit, visible act, and it is asked for one frame at a time
   ([03 § 4](03-registry-geo-trust.md)). There is no user identity to attach a
   frame to, by design.

## 4. Scope – v1 (MVP)

**In:**

- Live camera scan with **multiple simultaneous bins**, each boxed and labelled.
  A bank of six containers is a normal input, not an edge case — which is a
  **cost** commitment as well as an accuracy one, since each bin is another
  identifier pass ([05 § 3](05-cost-model.md#3-the-concurrency-ceiling--the-number-that-matters)).
- Server-side inference over a gated connection; frames are discarded after
  recognition and retained only with per-frame consent.
- Tap-to-scan single-frame mode (default on low-end devices, and the primary
  path wherever streaming is not affordable).
- Result card per bin: canonical stream, local name, ✅ accepted / ❌ rejected
  lists, common-mistake note.
- **Full UI + rules localisation.** Launch locales: EN, DE, UA, RU, TR, AR, ES,
  FR, HI. RTL support for AR.
- Region packs: Deggendorf complete; a documented path to add any city.
- Registry contribution: submit an unknown bin (location + form + colour, photo
  optional and opt-in), with Turnstile + rate limits.
- Registry read: map of known bins near you, with `last_verified` staleness.
- Desktop/tablet surface with **no camera**: map, registry browser, rules search.
- Installable web app. Rules browser and cached region data work offline;
  **scanning and the map require a connection** and say so plainly.
- Accessibility: WCAG 2.2 AA, full keyboard path, screen-reader result cards,
  and a text-only path to every rule (never colour or camera as the sole route).

**Out – deliberately, with reasons:**

| Not in v1 | Why | Revisit |
|---|---|---|
| Identifying the *item in your hand* | A different, much harder CV problem; doubles dataset cost; the stated need is bins | v3, maybe never |
| User accounts, login, profiles | Adds GDPR surface, cost, and friction for zero benefit; reputation works pseudonymously | never |
| Native iOS/Android store builds | The web app covers it; a Capacitor wrapper is cheap to add later if install rates demand it | v2 |
| Pickup schedules | Needs per-municipality data, often only as PDF; the *data model* is in v1, the data is not | v3 |
| Municipal dashboard | No customer yet | post-v3 |
| Barcode / packaging scanning | Different problem, different data source | – |
| Gamification, points, streaks | Contradicts principle 1; adds retention machinery to a utility people should use rarely | never |
| Real-time crowd chat / comments | Moderation cost with no product benefit | never |
| Model training in the app | The predecessor's mistake. Training belongs on Kaggle | never |

## 5. Scope – v2 and v3

**v2 – coverage and trust**
- VLM escalation live for unknown bins, with moderation queue.
- Contributor reputation, direct-publish for trusted contributors.
- Desktop moderation tools; edit history per cluster.
- Second and third city packs, proving the region abstraction.
- Aperture-level detection on glass banks (clear / green / brown slots).

**v3 – the civic layer**
- Pickup schedules per region, with an import adapter per municipality and a
  manual-entry fallback.
- Bin-bank composition ("this stand has 6 containers: 2 clear glass, …").
- Access metadata (open / shed / locked) surfaced in the map.
- Optional municipality-facing aggregate view.

## 6. Success criteria

Measured, not vibes. Analytics are anonymous counters only – no journey tracking.

| Metric | v1 target | How measured |
|---|---|---|
| Time from app open to first correct answer | ≤ 4 s on a 2020 mid-range Android | Field test, 10 devices |
| Detection recall on held-out cities | ≥ 0.97 @ IoU 0.5 | [04-ml-pipeline § 7](04-ml-pipeline.md#7-evaluation) — **not measurable yet**: no dataset subset carries a second `region_id` |
| Stream resolution accuracy where a pack exists | ≥ 0.95 | Held-out labelled sightings |
| Escalation rate (scans reaching stage 3) | ≤ 5 % after 3 months in a covered city | Server counter |
| Monthly infrastructure cost | **€0** at pilot scale; see [05-cost-model § 3](05-cost-model.md#3-the-concurrency-ceiling--the-number-that-matters) | Vercel + HF + Supabase dashboards |
| Scan round-trip latency | ≤ 250 ms p50 on 4G | Service metrics |
| Concurrent scanners before degradation | ≥ 10 on the free tier, **at one bin per frame** | Load test; the six-bin case is a separate row once [docs/12 probe P4](12-validation-protocol.md#p4--multi-bin-cost-curve) has measured it |
| Lighthouse performance / a11y | ≥ 95 both | CI |

## 7. Non-negotiable constraints

- Vercel Hobby tier. No Pro, no paid add-ons, no per-inference API in the common path.
- The bill must round to zero at pilot scale, with a gradual, documented upgrade
  path rather than a cliff.
- Must be usable on a phone released in 2019.
- No feature may require the user to read German.
- The rules browser must work offline. Scanning may require a connection.
- Any feature whose cost scales with simultaneous users must be gated client-side.

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Wrong disposal advice given confidently | Real-world harm; user fined; project reputation | Never assert without a pack entry; show `last_verified`; cite the municipal source; make "unknown" a good result; never let a VLM guess reach a user unmoderated |
| Service saturates at launch | Scanning fails for everyone at once | Client-side gates (motion, cadence, result lock); visible stepped degradation to tap-to-scan; documented upgrade path |
| Cold-start: registry empty outside Deggendorf | App feels useless in new cities | Ship a strong "unknown bin" experience; seed packs from published municipal guides before launch in a city, not from users |
| Contributors poison the registry | Bad data, bad training set | Consensus-before-publish; reputation; no unmoderated path from user input into training data |
| VLM cost spike from abuse | Real money | Hard daily cap on total escalations project-wide; queue and defer rather than autoscale |
| Sole maintainer | Bus factor 1 | Everything documented here; data files are plain JSON; nothing depends on a proprietary service that cannot be swapped |
| EU AI Act Art. 50 transparency, **in force since 2026-08-02** | Not a fine at this scale; a blocker to any university or municipal partner | Exposure is disclosure, not content marking — we generate nothing. Say a model produced the identification, surface confidence and `unknown`, cite the municipal source. See [research/07](research/07-compliance-and-consent.md) |

## 9. Open questions

Tracked, not blocking. Each has a proposed default so work can proceed.

1. **Product name / wordmark.** "Smart Bin Recognition" is the project and repo
   name. A shorter consumer wordmark may serve the app better. *Default:* ship
   as **Smart Bin** until a better name wins.
2. **Escalation VLM provider.** *Default:* Claude Haiku for cost, with the
   provider behind an interface so it can be swapped.
3. **Region-pack authoring.** Whether v1 packs are hand-authored from municipal
   guides or bootstrapped by a one-off VLM pass over those guides with human
   review. *Default:* the latter – it is the same pipeline as stage 3, run offline.
4. **Where "unknown" bins live before moderation.** *Default:* visible to the
   contributor only, marked pending.
