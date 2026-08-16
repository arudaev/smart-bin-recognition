# 03 – Registry, Geo and Trust

> The registry is a shared, crowd-maintained map of physical bins. It is also the
> part of the system most exposed to abuse and most capable of causing harm, so
> it is designed defensively from the start.

---

## 1. What a registry entry is

Not a photo, and not a sighting. A **cluster**: one physical bin location that
several independent observations have agreed on.

```sql
create table bin_cluster (
  id              uuid primary key,
  centroid        geography(point, 4326) not null,
  h3_cell         text not null,              -- resolution 11, ~25 m
  geohash5        text not null,              -- CDN tile key

  form_factor     text not null,
  body_color      text,
  lid_color       text,
  count           smallint not null default 1, -- how many identical bins here

  resolved_stream text,                        -- FK → taxonomy stream id
  resolution_via  text,                        -- pack_rule | vlm | moderator | contributor
  confidence      real not null,

  access          text,                        -- open | shed | locked | unknown
  status          text not null default 'pending',  -- pending|active|disputed|retired
  region_id       text,

  first_seen      timestamptz not null,
  last_verified   timestamptz not null,
  observation_n   integer not null default 1
);
```

`sighting` rows are append-only evidence pointing at a cluster; clusters are
derived. Nothing is ever hard-deleted – a bin that disappears goes `retired`, so
the history of what was where survives, which is what makes the "bins move
around constantly" problem tractable rather than corrosive.

## 2. Clustering and dedup

On write, a sighting folds into an existing cluster when **all** hold:

- within **15 m** (`ST_DWithin`), tuned to consumer GPS error, not to bin size
- same `form_factor`
- compatible colour (equal, or one side unknown, or within one CIELAB
  neighbourhood – wet plastic at dusk reads darker)

Otherwise it opens a new `pending` cluster. Splitting wrongly-merged clusters is
a moderator action; over-merging is the worse error, so the radius is kept tight
and duplicates are tolerated until moderation.

A cluster's `count` handles the common physical reality: five identical brown
bins in a row are one cluster with `count: 5`, not five clusters. The UI reads
this back as "5 × bio bins here".

## 3. Staleness, not deletion

Bins move. The registry never claims otherwise:

- `last_verified` is shown in every result and on every map pin, as a relative
  time in the user's locale ("checked 3 days ago" / "not checked since March").
- Confidence **decays with age**, at a rate that depends on form factor: an
  `igloo` or `underground` container is effectively permanent; a household
  `wheelie_small` is wheeled in and out weekly and decays fast.
- Below a floor, a cluster drops out of the published pack and back to
  `pending` – visible to contributors, not asserted to users.
- A "still here?" / "gone" confirm control on every pin is the cheapest possible
  contribution, and the one that keeps the map alive.

This is why the design brief insists staleness is a **first-class visual
element**, not fine print. An eight-month-old pin and a yesterday pin must not
look the same.

## 4. Geo privacy

Location is the most sensitive thing this app touches. It points at people's homes.

| Data | Precision stored | Reason |
|---|---|---|
| Sighting coordinate | ~1 m, **transient** | needed for clustering; discarded after fold-in |
| Cluster centroid | ~5 m | it is street furniture, publicly visible |
| Escalation payload | geohash-6 (~1.2 km) | enough to pick a jurisdiction, not a household |
| Analytics | region id only | counters, never journeys |

Rules:

- **Never** store a sighting coordinate against a contributor identity. The
  sighting table has no author column – only an opaque, rotating submission
  token used for rate limiting, which is discarded on a schedule.
- Photos are **opt-in per submission**, downscaled to 512 px on-device before
  upload, stripped of EXIF, and reviewed before retention. A submission without
  a photo is fully useful – form factor, colour and count are structured fields.
- No background location. No location access outside an active scan or an
  explicit map interaction.
- A user's own scan history stays on-device in IndexedDB and is never uploaded.

### The consent lifecycle for retained frames

Until 2026-08-16 this said only that consent was "per-session and visible", which
is not a specification. It is one now, and it follows from decisions already
taken — see [research/07](research/07-compliance-and-consent.md). EU AI Act
Art. 50 has been in force since 2026-08-02, so this is current work rather than
future work.

```
scan  →  answer shown  →  is this frame worth keeping?
                                  │ no → discarded, nothing asked, no interruption
                                  │ yes
                                  ▼
                        ask ONCE, at the moment, naming THIS frame and why
                                  │ declined → discarded; not asked again this session
                                  │ granted
                                  ▼
            downscale ≤ 512 px · strip EXIF · geohash-6 only · LOCAL RECEIPT
                                  ▼
              pending queue · stated retention window · human review
                                  │
                        ┌─────────┴─────────┐
                   accepted              rejected
              dataset revision        deleted at review
```

Four properties, each of which is a decision and not a detail:

- **An ordinary successful scan never sees a consent prompt.** There is nothing
  to consent to: the frame is already discarded ([04 § 2](04-ml-pipeline.md)).
  Prompting on every scan is how people learn to dismiss prompts.
- **Consent is per frame, not per session.** "Keep this one" and "keep everything
  from this session" are different questions and only the first is honest about
  scope.
- **Deletion works without an identity.** The device keeps a **local receipt** —
  an opaque token — for each pending contribution, and the receipt revokes it.
  This is what makes "no accounts" a privacy asset rather than an excuse for
  having no deletion path.
- **A retention window is stated**, and pending frames that are never reviewed
  expire rather than accumulating.

One thing above is **not yet real and must not be described as though it were**:
the automatic face/plate rejection assumed elsewhere in this document is an
unscoped ML component. Until it is built and measured, the guarantee is **human
moderation before retention**, which is what actually happens.

The uncomfortable case, named explicitly: a household bin outside a single
dwelling is, in effect, a fact about that dwelling. Mitigations are the tight
5 m centroid, decay-out of stale household bins, no photos of house numbers
passing review, and a takedown path. Communal and street infrastructure carries
none of this concern, and is where the registry's value mostly lives anyway.

## 5. Trust ladder

No accounts – a device-local keypair. Pseudonymous, portable via export, and not
linkable to a person.

| Level | Earned by | Gets |
|---|---|---|
| **Anonymous** | – | submit sightings; they enter `pending` |
| **Recognised** | 3 submissions that survived moderation | higher rate limits; confirm/deny on existing pins |
| **Trusted** | 20 survived, 0 reverted | direct-publish on confirmations; access to the desktop moderation queue |
| **Moderator** | manual grant | split/merge clusters, edit packs, retire entries |

Reputation is a *rate-limit and review* mechanism, not a leaderboard. It is
never displayed as a score, badge, rank or streak. See
[00-PRD § 4](00-product-requirements.md#4-scope--v1-mvp) – gamification is a
permanent non-goal.

## 6. Publication gate

A `pending` cluster becomes `active` – and therefore visible to ordinary users –
only when one of:

- two independent contributors agree on it, **or**
- a VLM escalation corroborates it and a moderator approves, **or**
- a moderator or trusted contributor publishes it directly, **or**
- it arrived via municipal data import.

Until then it is visible only to its submitter, marked pending. This is the
guardrail against the product's worst failure: telling somebody with confidence
that the wrong thing goes in the wrong bin.

**Separately and more strictly:** consensus is enough to *publish a pack entry*;
it is **not** enough to enter the training set. Training data requires human
label review. Those are different bars because they have different blast radii –
a bad pack entry is fixed by editing one JSON file, a bad label is baked into a
model.

## 7. Abuse

| Vector | Defence |
|---|---|
| Automated spam submission | Cloudflare Turnstile, verified server-side before the handler body runs |
| Volume from one actor | Per-install and per-IP token buckets in KV; reads are static and unmetered |
| Fake locations | Speed-of-travel plausibility, land/sea check, bbox check against a known region |
| Coordinated poisoning | Consensus-before-publish; independence check on contributor tokens; no path into training data without human review |
| Escalation cost attack | Hard project-wide daily ceiling; queue, never autoscale ([05-cost-model § 4](05-cost-model.md#4-the-one-paid-path-and-its-leash)) |
| Photo abuse (people, plates, doors) | Opt-in per frame, 512 px, EXIF stripped, **human moderation before retention**. Automatic face/plate rejection is *planned, not built* — see § 4 |
| Scraping the registry | It is public civic data by design; tiles are rate-limited at the CDN and that is the extent of it |

## 8. Serving

Reads never touch the database. A nightly cron (plus an on-demand rebuild when a
tile changes materially) renders `active` clusters into static tiles:

```
/packs/<geohash5>.json        bins in this ~5 x 5 km tile
/packs/<region_id>.rules.json region pack – rules, local names, i18n keys
```

Immutable, content-hashed, cached hard, service-worker cached on device. Tiles
the user has already visited stay readable without a connection, so the **rules**
for your own town remain available offline even though the live map does not.
