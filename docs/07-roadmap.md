# 07 – Roadmap

Phases are gated on outcomes, not dates. Sole maintainer; estimates are honest
about that.

---

## Phase 0 – Foundation ✅

- [x] Audit the predecessor; extract what carries forward → [08-legacy-audit](08-legacy-audit.md)
- [x] Canonical waste-stream taxonomy + JSON schemas
- [x] Region-pack format + Deggendorf draft pack
- [x] Architecture, PRD, cost model, i18n strategy
- [x] Python ML package skeleton (import, config, export, dispatch, kernel)
- [x] Claude Design brief + tokens + screen inventory

**Exit:** a designer or an agent can start work from documents alone.

---

## Phase 1 – Design ✅

- [x] Claude Design builds the system, then the app, from [`handoff/`](../handoff/README.md)
- [x] Review against the device-capability matrix – especially: does the
      no-camera desktop surface stand on its own? It does, and it is what the
      probe opens when it finds no environment-facing camera, rather than
      something reached by resizing a window.
- [x] Verify RTL (Arabic) at every breakpoint before accepting
- [ ] Verify Devanagari – deferred with the locale itself; there is no `hi`
      bundle to render yet, and checking the font stack against English text
      proves nothing
- [x] Import generated components into `web/` via the Claude Design MCP link
- [x] Extract design tokens into `web/src/styles/`

**Exit met.** Every designed state exists in `web/`, including the ones that are
easy to skip: no pack, draft pack, `unknown`, stale sighting, camera refused,
offline. What was ratified along the way is in
[`handoff/DECISIONS.md`](../handoff/DECISIONS.md); what the flow review changed
is in [`handoff/FLOW-NOTES.md`](../handoff/FLOW-NOTES.md).

---

## Phase 2 – Vision spike *(highest risk – in progress)*

- [x] `legacy_import.py` → resized dataset with provenance on HF Hub, pinned by
      revision. **370 usable frames, not 466**: the published archive is a
      partial copy and the shortfall is now a contract, not a surprise
      ([08 § 7.1](08-legacy-audit.md#71-the-archive-as-it-really-is)).
- [x] Tooling for the human pass – `ml/scripts/adjudicate.py`, 403 crops ordered
      by capture cluster, one keystroke each
- [ ] **The human pass itself.** Blocks the identifier and nothing else.
- [x] Negative corpus + out-of-city bins from Open Images. **Landed 2026-08-16**
      and pinned: 1 110 bin frames carrying 1 936 boxes, of which **98 hold four
      or more bins** — the legacy archive holds none — plus 17 474 background
      frames (14 975 street scenes, 2 499 hard negatives), a 15.7:1 negative
      ratio within the subset. Pools are shard-nested because the Hub refuses a
      directory over 10 000 files ([04 § 5](04-ml-pipeline.md)).
- [x] **Every ship gate has an owner.** Until 2026-08-16 int8 accuracy had none —
      both kernels deferred it to `gate.py`, which measures only latency, so
      `may_ship` was unreachable and the first run would have produced an
      undecidable artefact. The kernels now score the quantised graph on the same
      split, and `export.targets` is read rather than decorative
      ([04 § 7](04-ml-pipeline.md#targets-versus-gates--different-things-different-consequences)).
- [x] **Probes P4 and P5** — ran 2026-08-16, without a training run, exactly as
      [docs/12](12-validation-protocol.md) predicted they could. **Both model
      budgets pass and the concurrency they were supposed to buy does not**:
      validator 26.6–33.0 ms and identifier 17.4–21.7 ms per crop, but a one-bin
      frame costs 66–77 ms and the ceiling re-derives to **4–5 concurrent
      scanners, not 10**. Two causes, both recorded in
      [P4](research/probes/P4-multi-bin-cost-curve.md): docs/05 § 3's arithmetic
      double-counted the vCPUs, and 15–40 ms per frame belongs to neither graph.
      Crop batching was measured at 1.10–1.25×, never the 2× that would have made
      it the service requirement docs/01 § 4 called it.
      [P5](research/probes/P5-validator-architecture.md): RF-DETR-nano is 475 ms,
      9.5× over budget, so **YOLO11n stays**; D-FINE-N is unevaluated, which is
      recorded as a gap rather than as a failure.
- [ ] **Probe P1** — form-factor separability, *before* the adjudication pass, so
      403 crops are not labelled against a class list that turns out wrong
- [ ] **First training run on a Kaggle kernel — attempted 2026-08-16, failed.**
      The kernel pulled the pinned pool, built the dataset (18 954 images, split
      13 265/2 823/2 866) and started Ultralytics, then ended with status
      `ERROR`, **no weights, an empty log and an empty failure message**. GPU was
      enabled, so that is not the cause; a re-push of the cheap CPU bench kernel
      failed identically, which points at the account or the platform rather
      than at either script. Recorded in
      [11 § the validator run](11-phase2-results.md); unresolved.
- [x] ONNX export path, role-aware, with the four gates config-driven and pinned
- [x] The thing that makes the latency budget real: a **2-vCPU bench**,
      because "on service CPU" cannot be measured on a training GPU
- [ ] Colour extraction, validated against **hand-labelled body/lid colours**
      ([probe P3](12-validation-protocol.md#p3--colour-measurement)). The earlier
      wording here — "from SAM 2 masks, validated against the legacy class
      labels" — was wrong twice: legacy labels are waste *streams* and a stream
      is not a colour any more than it is a shape, and whether a mask is needed
      at all is exactly what the probe tests.
- [x] **Load-test the service: how many concurrent scanners before degradation?**
      Done 2026-08-17. **4 at one bin per frame, 1 at six**, on a pinned 2-vCPU
      container. It also found that the degradation ladder had never been
      reachable in production — inference blocked the event loop, so the load
      shedder never saw a queue and no rung ever fired.

**Gate:** validator ≤ 50 ms @ 448 and identifier ≤ 25 ms per crop on service
CPU, and ≥ 10 concurrent scanners on the free tier **at one bin per frame**. If
this fails, the free-tier thesis needs revisiting – which is why it is phase 2
and not phase 5.

The concurrency half now carries a caveat it did not have: a six-bin frame costs
roughly three times a one-bin frame, so ten concurrent scanners is the *easy*
end of a 3–10 range ([05 § 3](05-cost-model.md#3-the-concurrency-ceiling--the-number-that-matters)).
Probe P4 measures the curve.

### Gate status, 2026-08-17: ANSWERED. The latency half passes, the concurrency half fails, and the kill criterion fires.

| half | budget | measured | verdict |
|---|---|---|---|
| validator @ 448 | ≤ 50 ms | 26.6 – 33.0 ms | **pass**, ~40 % headroom |
| identifier @ 320 per crop | ≤ 25 ms | 17.4 – 21.7 ms | **pass** |
| concurrent scanners @ 1 bin | ≥ 10 | **4** | **FAIL** |
| concurrent scanners @ 6 bins | – | **1** | the PRD's normal input |

No longer a prediction. Measured 2026-08-17 by `service/loadtest/run.py` against
`docker run --cpus 2`, virtual scanners at 3 fps in strict request-response,
ramped until p95 crossed 250 ms. Full curve and hardware in
[11-phase2-results](11-phase2-results.md).

**So: the kill criterion below fires.** It is stated as *"phase 2 gate fails and
cannot be recovered → the free-tier serving thesis is wrong. Stop and cost a
paid tier honestly rather than shipping something that falls over at launch."*

The gate fails. Whether it **cannot be recovered** is the open half, and it is
worth being exact rather than reaching for either conclusion:

- Four is against a gate of ten, on a *pinned proxy* whose core is faster than a
  shared Cloud Run vCPU. The real host is unlikely to do better.
- The measurement agrees with the prediction that preceded it, so this is not
  one noisy result.
- What has **not** been tried is the recovery list docs/05 § 7 wrote down in
  advance: the validator at 384 px (it is a third of a one-bin frame), finding
  the 15–40 ms that belongs to neither graph, and capping crops at 3 rather
  than 6. Each is cheap and none has been measured.
- What **has** been fixed since the prediction is the degradation ladder, which
  had never once fired in production ([11](11-phase2-results.md)). That does not
  raise the ceiling; it means the product now degrades honestly at it instead of
  getting silently slower.

**The honest reading: the thesis as written — ten concurrent scanners free — is
dead. A pilot in one town at four concurrent scanners is intact, and the
client-side gates are what make that liveable.** Before rationalising or
abandoning, run the three cheap recoveries and re-measure; if they land the
figure short of ten, cost the paid tier honestly, which docs/05 § 7 already
prices at USD 9/month for the first step.

Nothing about this is blocked on a trained model. It was measurable without one,
and it was.

Two things found on the way that change what this phase can conclude:

- **Seven of the ten form factors have no legacy data at all.** The four legacy
  classes reach only `wheelie_small`, `wheelie_large` and `igloo`.
- **There is a way out of the held-out-city gap, and it is cheap.** Video
  containers carry GPS and a timestamp, so filming a walk-around gives frames a
  **real `region_id`** — which is the single thing standing between this phase
  and the question it exists to answer. It also produces multi-bin frames and
  viewpoint diversity as a side effect, and makes the human pass affordable by
  letting one decision cover a whole **track** instead of one frame.
  [Probe P7](12-validation-protocol.md#p7--video-as-the-capture-format) tests it
  on twenty minutes of filming before anything is built;
  [research/08](research/08-video-ingestion.md) argues it and lists the five ways
  it goes wrong. The dangerous one — near-identical frames straddling a split,
  which reports memorisation as generalisation — is already guarded in
  `prepare.py`.
- **The held-out "city" is still not a city.** The Open Images subset has now
  landed and it does broaden the distribution — worldwide photographs, and the
  only multi-bin frames the project has — but every one of its frames carries
  `region_id: "unknown"`, because Open Images does not say where a photograph
  was taken. So it cannot serve as a geographic holdout either. Until a real
  second-city capture lands, the honest split remains group-aware by capture
  cluster, and `holdout_region` stays empty. The training kernel already says so
  rather than quietly reporting an aggregate.

---

## Phase 3 – Core app *(both halves built and now joined; blocked on a model)*

The client half ran ahead of phase 2, because it could: the loop takes its
transport as an argument, so an in-process mock drives exactly the loop a socket
will drive. The service caught up on 2026-08-16, and on 2026-08-17 the two were
actually joined — pinned to the same bytes rather than to the same paragraph,
with the degradation ladder wired end to end and CI running both trees.

What is left is no longer engineering between here and "a person in Deggendorf
gets an answer". It is **a model**. The service will not start without one, by
design, and both roles are now blocked: the identifier on the human pass, the
validator on a training run that failed with no log.

- [x] Vite + React + TS scaffold; service worker for the offline rules browser
- [x] **FastAPI inference service: `POST /detect` + WS `/stream` + `/health`.**
      `service/` holds nine modules and 111 passing tests: the two transports,
      the degradation ladder (`shed.py`), sidecar-driven artefact loading with a
      **hard refusal** on anything whose `gate_result` does not say `may_ship`,
      provisional colour in CIELAB, and a discipline test that parses the request
      path and fails if anything on it could write a frame to disk.
      `POST` is primary and the socket ships unused — a held-open WebSocket
      forces Cloud Run's instance-based billing
      ([01 § 2](01-architecture.md#which-inference-host)).
- [ ] **Deploy.** The Google Cloud side is **built and paid for** as of
      2026-08-17 — project `smart-bin-recognition`, billing linked, a €5/month
      budget with alerts created *before* any billable resource, Artifact
      Registry, an `amd64` image, `service/deploy/cloudrun.sh` and a full
      runbook. **No service is running, and that is correct:** the container
      refuses to start because no artefact's sidecar says `may_ship`. That
      refusal has now been exercised in production, which is the first time it
      has run anywhere but a test. The client is therefore not on Vercel either
      — pointing it at an untrained COCO graph would make it confidently wrong,
      which is the one thing this product must not be. Deploying is one command
      once a model exists.
- [x] **The load test** — done 2026-08-17, against `docker run --cpus 2` as
      required. See the phase-2 gate above. It needed no trained model:
      `SBR_ALLOW_UNGATED=1` with the int8 artefacts under `artifacts/probe2/`
      is the same trick that let P4 and P5 run.
- [x] **CI for `service/` and `web/`.** `service.yml` runs ruff, mypy and 141
      tests; `web.yml` runs `npm run verify` (typecheck, 274 tests, locales,
      build, transfer budget). Both are path-filtered on more than their own
      directory, because both read `data/taxonomy` and the service imports
      `sbr.taxonomy`. Each also guards the wire contract from its own side.
- [x] **The wire contract has drifted, and only a byte-level test will catch it.**
      Fixed. `emit-wire-fixtures.mjs` encodes requests with the shipped
      TypeScript encoder; `test_wire_contract.py` decodes those bytes and emits
      responses; `contract.test.ts` reads them back. `protocol.ts` gained
      `advice` and `pack_status`, typed to mirror the wire's distinction between
      *absent* and *null*. It caught real drift on its first run: `encode_frame`
      escaped non-ASCII, so a locale of `ar-Ω` produced a 64-byte header where
      the browser produces 60.
- [x] **The ladder's client half.** `Cadence.setMaxFps` clamps against
      `MAX_FPS`, so the service may lower a cadence and never raise it — enforced
      at both ends, because they deploy separately. `StopReason` gained `shed`,
      `TransportError` carries advice so rung 3 survives being thrown, and
      `loop.ts` applies all three rungs. Fixed a bug it would otherwise have
      inherited: `send()` bailed on any frame after the first once the loop had
      stopped, so tap-to-scan after the twenty-second timeout silently did
      nothing — the affordance appeared and the button was dead.
- [x] Capability probe; three device tiers
- [x] Scan loop: motion gate, 4 fps cap, **result lock**, 20 s abort, tap-to-scan
- [x] Resolver in `domain/`, framework-free, unit-tested against the pack schema
- [x] Multi-bin result cards
- [ ] Nine locales, including RTL – `en` is complete (422 keys) and `de` / `ar`
      are at 64 % and fall back to English; six locales are not started.
      `npm --prefix web run check:locales` prints the gap.
- [x] Desktop surface: map, registry browser, rules search – the surfaces are
      real, the registry behind them is fixtures until phase 4
- [ ] Deploy to Vercel

Built in the same pass, beyond what this phase originally listed:

- [x] Installable PWA: manifest, generated icon set, update flow that asks
      rather than reloads under a person mid-answer
- [x] Offline split as routing – rules cached, recognition never cached
      (see [01-architecture § 6](01-architecture.md))
- [x] Region packs over `api/pack/[region]`, cached in a store that survives
      deploys
- [x] Settings surface: which tier, which service, what is cached, which locale
      is falling back
- [x] Performance work: a metric vocabulary, web vitals, a transfer budget that
      exits non-zero
- [x] 274 tests, no browser – the gates, the protocol, the awkward loop
      sequences, the router, the theme, and a source-discipline test that
      enforces the conventions
- [x] A real application shell, replacing the imported prototype viewer: real
      URLs on a hand-rolled History API router, the theme on `<html>`, `100dvh`
      and safe-area insets instead of a drawn 390x812 phone, a viewer surface
      that works from a small laptop to a wide monitor, and the state director
      out of the production bundle by construction

**Exit:** a person in Deggendorf who reads no German points a phone at a bin and
gets a correct answer in Ukrainian.

No longer blocked on the service — that exists. Blocked on four things, and it
is worth being exact about which, because they have different owners:

| Blocker | Owner | Note |
|---|---|---|
| **No model at all** | the maintainer, then this phase | Was "no identifier". It is now both: the identifier still needs the 403-crop human pass in `data/legacy/pool/crops/`, and the validator run failed on 2026-08-17 with no log. Until one artefact passes its gates the service will not start, so nothing can be deployed that serves. |
| **Nothing is deployed** | this phase, *behind the above* | The Cloud Run path is built, budgeted and documented; it has nothing to serve. One command once a model exists. |
| **The Ukrainian bundle** | this phase | `en` is complete at 422 keys; `de`/`ar` are at 271 (64 %); six locales including `uk` are not started |
| **The Deggendorf pack is `draft`** | this phase | Every source now carries a deep link and a retrieval date, so `is_publishable` is true — that is the *sourcing* bar and nothing more. The 2026-08-17 pass found the operator routes packaging to a **Wertstoffinsel**, contradicting both packaging rules, and that no source states any container colour. It stays draft until a human resolves that. |

The first is the one that decides whether the exit criterion is reachable on
any particular date, and half of it is the only one no amount of engineering
shortens.

---

## Phase 4 – Registry

- [ ] Supabase Postgres + PostGIS; cluster and sighting schema
- [ ] `POST /api/sighting` with Turnstile + rate limits
- [ ] Clustering and dedup on write
- [ ] Nightly tile bake; static serving
- [ ] Device keypair identity; trust ladder levels 1–2
- [ ] Staleness decay and the "still here? / gone" control
- [ ] Contribution queue with offline flush

**Exit:** two people independently map a street and get one coherent map.

---

## Phase 5 – Escalation and closing the loop

- [ ] `POST /api/escalate`, strict JSON contract, citation required
- [ ] Project-wide daily ceiling; queue-not-autoscale behaviour
- [ ] Desktop moderation queue; trust levels 3–4
- [ ] Approved escalations → pack entries
- [ ] Approved escalations → labelled-data candidates → human review → dataset revision
- [ ] Second training run proving the loop closes

**Exit:** escalation rate in Deggendorf measurably falls between two model versions.

---

## Phase 6 – Second city

The real test of the region abstraction. Success is defined as: **adding a city
requires no code change and no retraining.**

- [ ] Pick a city with a different colour convention (not Bavaria)
- [ ] Author the pack from published municipal guidance
- [ ] Measure held-out-city detector performance honestly
- [ ] Fix whatever the abstraction got wrong – there will be something

---

## Phase 7 – The civic layer *(v3)*

- [ ] Collection schedules: import adapters + manual entry; the schema slot
      already exists in the pack format
- [ ] Bin-bank composition ("6 containers: 2 clear glass, 1 green, …")
- [ ] Aperture-level detection for glass banks
- [ ] Access metadata (open / shed / locked) on the map
- [ ] Optional municipality-facing aggregate view

Phase 7 is where the deck's third next-step – *"partner with Deggendorf city /
THD to integrate services like pickup schedules"* – finally lands. It is last
because it is the only part that needs someone else to say yes.

---

## Kill criteria

Stated in advance, so they are not rationalised away later:

- **Phase 2 gate fails and cannot be recovered** → the free-tier serving thesis
  is wrong. Stop and cost a paid tier honestly rather than shipping something
  that falls over at launch.
  **FIRED, 2026-08-17, on the first half.** Measured 4 concurrent scanners at
  one bin per frame against a gate of 10, and 1 at six bins. *Cannot be
  recovered* is not yet established: the three cheap recoveries docs/05 § 7
  named in advance — validator at 384 px, the unexplained 15–40 ms, capping
  crops at 3 — are all untried. Run them, re-measure, and if it is still short
  of ten, cost the paid tier. Do not quietly restate the gate as four.
- **Novelty precision stays below 0.5** → the validator/identifier disagreement
  is not a usable signal and the improvement loop does not close. That is the
  load-bearing assumption of the whole design.
- **Held-out-city recall stays below 0.6 after two dataset expansions** → form
  factors do not generalise the way this design assumes. Revisit the class split.
- **The €0 constraint breaks at < 10 000 MAU** → the cost model is wrong
  somewhere; find it before adding features.

## Deliberately never

Accounts. Ads. Gamification. Paywalled disposal rules. In-app training. Runtime
LLM translation of safety-relevant advice.
