# 07 – Roadmap

Phases are gated on outcomes, not dates. Sole maintainer; estimates are honest
about that.

---

## Phase 0 – Foundation ✅ *(this commit)*

- [x] Audit the predecessor; extract what carries forward → [08-legacy-audit](08-legacy-audit.md)
- [x] Canonical waste-stream taxonomy + JSON schemas
- [x] Region-pack format + Deggendorf draft pack
- [x] Architecture, PRD, cost model, i18n strategy
- [x] Python ML package skeleton (import, config, export, dispatch, kernel)
- [x] Claude Design brief + tokens + screen inventory

**Exit:** a designer or an agent can start work from documents alone.

---

## Phase 1 – Design

- [ ] Claude Design builds the system, then the app, from [`handoff/`](../handoff/README.md)
- [ ] Review against the device-capability matrix – especially: does the
      no-camera desktop surface stand on its own?
- [ ] Verify RTL (Arabic) and Devanagari at every breakpoint before accepting
- [ ] Import generated components into `web/` via the Claude Design MCP link
- [ ] Extract design tokens into `web/src/styles/`

**Exit:** a clickable prototype whose empty, unknown and stale states are all designed.

---

## Phase 2 – Vision spike *(highest risk – do it early)*

- [ ] `legacy_import.py` → resized, remapped dataset on HF Hub
- [ ] Human pass: `wheelie_small` vs `wheelie_large` on ambiguous legacy labels
- [ ] First YOLO11n training run on a Kaggle kernel
- [ ] ONNX export for both models; enforce the latency budgets
- [ ] Colour extraction from SAM 2 masks, validated against the legacy class labels
- [ ] **Load-test the service: how many concurrent scanners before degradation?**

**Gate:** validator ≤ 50 ms @ 448 and identifier ≤ 25 ms per crop on service
CPU, and ≥ 10 concurrent scanners on the free tier. If this fails, the free-tier
thesis needs revisiting – which is why it is phase 2 and not phase 5.

---

## Phase 3 – Core app

- [ ] Vite + React + TS scaffold; service worker for the offline rules browser
- [ ] FastAPI inference service on an HF Space: WS `/stream` + `POST /detect`
- [ ] Capability probe; three device tiers
- [ ] Scan loop: motion gate, 4 fps cap, **result lock**, 20 s abort, tap-to-scan
- [ ] Resolver in `domain/`, framework-free, unit-tested against the pack schema
- [ ] Multi-bin result cards
- [ ] Nine locales, including RTL
- [ ] Desktop surface: map, registry browser, rules search
- [ ] Deploy to Vercel

**Exit:** a person in Deggendorf who reads no German points a phone at a bin and
gets a correct answer in Ukrainian.

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

## Phase 5 – Escalation and the flywheel

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
