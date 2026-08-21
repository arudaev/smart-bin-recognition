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
- [x] **The human pass itself — DONE 2026-08-21.** All 403 crops, reviewer
      `alex`, run with `--blind` so the pool's stream→shape proposals were
      withheld; every verdict is `authored` rather than `confirmed`, and none
      was rejected. That was necessary rather than fastidious: against the
      finished pass the shipped proposals are **wrong on 116 of 403 crops
      (28.8 %)**, of which **111 are `wheelie_small` where the answer is
      `wheelie_large`** — precisely the pair P1 tests. Primed, the pass would
      have measured the mapping table. Result: `wheelie_small` 247,
      `wheelie_large` 115, `igloo` 40, `street_basket` **1**, and six form
      factors at **zero**. Committed at `data/legacy/pool/adjudication.json`,
      which nothing can regenerate.
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
- [x] **Probe P1 — ANSWERED 2026-08-21.** Its amendment ran it *after* the pass
      rather than before, because the pass finished first and the rule it was
      written against could not fire on the result. Pairwise
      `wheelie_small`/`wheelie_large` is **0.9834** out-of-fold under
      `GroupKFold` on capture cluster, against a 0.75 threshold and a **0.6823**
      majority-class baseline, on the **embedding alone** — so box area does not
      become a service feature. Six errors in 402, all between the two wheelie
      sizes; not one crop crossed between a wheelie and an igloo.
      [P1](research/probes/P1-form-factor-separability.md).
- [x] **Open Images form-factor survey — DONE 2026-08-21.** 384 boxes, seed
      20260821, frozen before a crop was opened. Open Images is a **street-litter
      corpus**: `street_basket` is 35 % of the sample against a legacy archive
      holding exactly one. It does **not** close the coverage gap, which is the
      more useful answer — zero `underground`, zero `textile_bank`, zero
      `wall_unit`. [research/11](research/11-open-images-form-factors.md).
- [x] **Model B trained, exported and gated on accuracy — 2026-08-21.**
      Three classes, decided by the maintainer on P1's evidence.
      int8 costs **0.0000** top-1 against a 0.02 budget, so the pre-registered
      sweep never ran. `test` top-1 is 1.0000 **on 47 crops**, of which `igloo`
      is three from two clusters — the 95 % lower bound is 0.936 and P1's
      out-of-fold 0.9834 is the better estimate.
      [P11](research/probes/P11-identifier-int8.md).
- [x] **First training run on a Kaggle kernel — COMPLETED 2026-08-18**, after
      two failures and a six-rung diagnosis. yolo11n @ 448, 80 epochs, on a
      requested T4: **test mAP@0.5 = 0.7524**, specificity on 2 662 background
      frames **0.9793** (the `min_precision_on_negatives` target, MET). **It
      may not ship**: int8 quantisation costs **0.727 mAP@0.5** against a 0.02
      budget, so `may_ship: false` and the service's refusal holds. The gate
      that had no owner until 2026-08-16 fired on the first real run and
      caught a model that would have served noise. Full numbers in
      [docs/11](11-phase2-results.md).
- [x] **Probe P9 — why int8 destroys it. ANSWERED 2026-08-21.** **Quantising the
      detection head is what causes the collapse**: excluding `/model.23/` moves
      the model from 0.015 to **0.7481** on `val`, a 50-fold recovery, for
      +5.7 ms on a Kaggle x86 proxy and +1.2 MB. It does **not** follow that
      nothing outside the head matters — that graph is still quantised
      everywhere else and still loses 0.0252, and the residual is unattributed. Every format remedy onnxruntime documents
      — S8S8, `reduce_range`, U8U8, per-tensor — stays at collapse, and S8S8 is
      additionally 2.5× slower. The pre-registered combined run made things
      worse. **The best configuration is 0.0252 below the PyTorch fp32 reference
      against a 0.02 budget: the gate is missed by 0.0052, and the gate does not
      move.** The latency figure is a proxy (`representative: false`) and does
      not close the latency gate either. So the blocker is **diagnosed and not cleared** — v1 still cannot
      ship, and whether to take a 0.025 trade is a product decision that is not
      the probe's to make. There is deliberately **no `test` measurement** of that
      configuration: nothing was eligible, so nothing was confirmed, and the test
      split is unspent. [P9](research/probes/P9-int8-quantisation.md).
- [x] **Probe P10 — where the residual lives. ANSWERED 2026-08-21, and the
      answer is "nowhere findable".** The corrected SQNR diagnostic ran for the
      first time and named `/model.10/m/m.0/attn/Softmax_output_0` at 23.90 dB,
      the worst tensor in the graph by 1.65 dB — the same C2PSA block a 1517×
      weight-scale anomaly had independently pointed at. **Excluding it removes
      75 QDQ nodes, 12 % of everything still quantised, and buys +0.000914 mAP**,
      which is below the 0.005 this project treats as noise. The other two ranked
      modules made it worse. So the ranking and the sweep disagreed, the
      pre-registered rule says believe the sweep, and the conclusion is that **no
      module outside the detection head accounts for the residual by a
      distinguishable amount** — the 0.0254 is spread across the remaining 544
      QDQ nodes. Best configuration on `val`: **0.7480 against 0.7734, missing
      the gate by 0.0054.** `test` untouched, gate unmoved, no v2 published.
      Quantisation-aware training is the only remaining route and is the
      maintainer's decision, not attempted.
      [P10](research/probes/P10-where-the-residual-lives.md).
      *The original failure, for the record:*
      The kernel pulled the pinned pool, built the dataset (18 954 images, split
      13 265/2 823/2 866) and started Ultralytics, then ended with status
      `ERROR`, **no weights, an empty log and an empty failure message**.
      **The 2026-08-17 diagnosis narrowed this a long way and did not close it**
      ([11 § what the ladder found](11-phase2-results.md)). A six-rung ladder of
      smoke kernels, each changing one thing, showed that the account and the
      platform are fine, that the attached secrets dataset — the leading
      hypothesis — is not the cause, that a Kaggle Secret is *not* an
      alternative to it, and that `bench_latency`'s matching failure was its own
      `SystemExit("no artefacts to measure")` working correctly rather than a
      shared symptom. It also found a real latent bug: **the bundle unpacked
      `data/taxonomy` one directory too high**, so every kernel calling
      `load_taxonomy` failed — which `train_identifier` would have hit on its
      first line of work. Fixed and pinned by a test.
      **The validator's own cause was then found, and it is the platform's:**
      the Kaggle image ships **torch 2.10.0+cu128**, which dropped `sm_60`,
      while Kaggle allocates **P100 (sm_60)** as well as T4. `is_available()`
      returns True and the first tensor move raises — pool pulled, dataset
      built, `args.yaml` written, no weights, which is the 2026-08-16 signature
      exactly. Established by a rung that installs **nothing**. The remedy is a
      run on a **T4**, and that is requestable rather than luck:
      `machine_shape: "NvidiaTeslaT4"` in the kernel metadata, which every GPU
      kernel here now sets. **Verified 2026-08-18** — the request was honoured
      and the image's torch runs on the allocated T4, so the training path is
      unblocked. The capability check (`sbr.utils.gpu`) backs it up and runs
      **before the pool is pulled**, so a bad allocation is refused without
      paying for the download and the tree build. It still follows dependency
      installation, so it is not instant - it is cheap.
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
      Built and run 2026-08-17, and the instrument outlived its first answer.
      It reported **4 at one bin per frame, 1 at six**; P8 later showed the
      host cannot hold that figure still, so the absolute number is
      **unresolved** and the harness now compares configurations in pairs.
      Its lasting finding stands: the degradation ladder had never been
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

### Gate status, 2026-08-21: BOTH LATENCY HALVES PASS. THE CONCURRENCY HALF FAILS AT 5 AGAINST 10.

| half | budget | measured | verdict |
|---|---|---|---|
| validator @ 448 | ≤ 50 ms | **18.3 ms** p50 | **PASS**, 63 % headroom |
| identifier @ 320 per crop | ≤ 25 ms | **9.9 ms** p50 | **PASS**, 60 % headroom |
| **concurrent scanners @ 1 bin** | **≥ 10** | **5** | **FAIL** |
| concurrent scanners @ 6 bins | – | **2** | the PRD's normal input |

**Measured on a controlled host, `representative: true`** — GCE
`n2-standard-4`, `europe-west3-a`, CPU platform pinned, the service on CPUs 0–1
and the load-test client on 2–3, three repeats agreeing to within ~3 ms.
Created for the measurement and destroyed after.
[P12](research/probes/P12-the-controlled-host.md).

**This is the first admissible absolute concurrency figure the project has had**,
and it replaces the withdrawn 4 and 1 of 2026-08-17. Those were not wildly
wrong — P4's corrected arithmetic predicted 4.3–5.1 and 1.8–2.2, and the
measurements land at 5 and 2, inside both ranges. They were simply not
reproducible, which is what [P8](research/probes/P8-recovery-measurements.md)
actually established.

**What it would take.** The frame costs 49 ms and would have to cost ~25.
Validator 18.3, identifier 9.9, and ~21 ms of decode, letterbox, colour and
wire. P8b's shared onnxruntime thread pool — the one recovery ever shown to
work — was **already active**, so 5 is the figure with it applied. Of the two
still unmeasured, 384 px takes at best ~6 ms off 49, and capping crops does
nothing at one bin per frame, which is the level the gate is stated at.
**The gate fails on compute rather than on tuning.**

**Whether that kills the free-tier thesis is the maintainer's call**, and the
kill criterion below is deliberately left as it stands rather than being
declared fired by the probe that produced the number.

### The history, kept because the reasoning still holds


> **Revised 2026-08-18.** This section read *"ANSWERED … the kill criterion
> fires"* on the strength of the concurrency row below. [Probe
> P8](research/probes/P8-recovery-measurements.md) then bracketed that same
> measurement and found the host could not sustain it: the identical baseline
> gave 7 and then 4 in one evening. **The 4 is not a measured ceiling**, so it
> cannot carry a kill criterion. Nothing has ever been observed at ten either,
> so the gate has certainly not passed. The status is *unresolved*, and the
> thing that resolves it is a controlled 2-vCPU x86 host.

| half | budget | measured | verdict |
|---|---|---|---|
| validator @ 448 | ≤ 50 ms | 26.6 – 33.0 ms | **pass**, ~40 % headroom |
| identifier @ 320 per crop | ≤ 25 ms | 17.4 – 21.7 ms | **pass** |
| concurrent scanners @ 1 bin | ≥ 10 | ~~4~~ **not reliably measured** | **unresolved** — never observed above 8 |
| concurrent scanners @ 6 bins | – | **1** | the PRD's normal input |

No longer a prediction. Measured 2026-08-17 by `service/loadtest/run.py` against
`docker run --cpus 2`, virtual scanners at 3 fps in strict request-response,
ramped until p95 crossed 250 ms. Full curve and hardware in
[11-phase2-results](11-phase2-results.md).

> ### ⚠ SUPERSEDED 2026-08-18 — everything from here to the end of this section
> was written on the strength of the **4**, and
> [P8](research/probes/P8-recovery-measurements.md) has since shown that figure
> is not one this host can sustain. It is kept because the reasoning is still
> the right reasoning; only its input turned out to be unreliable. **Read the
> recoveries section below it for the current status**, which is *unresolved*.

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
figure short of ten, cost the paid tier honestly.

Nothing about this is blocked on a trained model. It was measurable without one,
and it was.

### The recoveries, measured 2026-08-18 — [probe P8](research/probes/P8-recovery-measurements.md)

**One of the three is real, and the measuring host turned out to be the bigger
finding.**

| | |
|---|---|
| gate | **≥ 10 concurrent scanners at one bin** |
| highest figure observed, any configuration | **8** |
| the same baseline, twice in one evening | **7, then 4** |
| verdict | **not established either way.** Nothing was observed at 10, and no admissible absolute measurement exists |

**P8b found the 15–40 ms and it is one line of configuration.** A frame carries
15.3 ms that belongs to neither graph, and the cause is exact: the service holds
**two onnxruntime sessions, each with its own intra-op thread pool, and both
spin while idle** — four threads contending for two cores, so the idle model
burns the running model's cycles. Holding the session count as the only variable
(one session called twice, versus two sessions of the *same* graph) measures
switching at **+36.9 ms**; one shared pool removes it and takes the two-graph
call from **57.1 ms to 26.3 ms**. Under load it is worth a median **−105 ms at
p95** across four ABBA cycles, in both orderings. The concurrency levels
within a cycle are correlated, so that is a consistent direction rather than
48 independent samples.

**P8a (384 px) and P8c (capping crops) are not established.** 384 sat inside the
drift; the crop cap was never reached. The cap's *cost* is established without a
measurement, though: the remainder is **not deferred to the next frame** — that
was never built — so at a six-container bank a cap of three leaves three
containers permanently unidentified.

**And the absolute number is not measurable on this laptop.** The identical
baseline configuration measured **7 at 22:30 and 4 at 23:48** on one evening,
with the whole curve stepping ~50 % worse partway through. The cause was the
machine itself: host CPU at ~50 % with the agent tooling on it, and
`docker run --cpus 2` is a cgroup **ceiling, not a floor**. The service's own
reported `ms` rose from a flat 33 ms to 46–55 ms — the container being starved,
not the service getting slower.

**That applies backwards.** The **4** recorded on 2026-08-17 came from the same
protocol on the same laptop, so it is not a measured ceiling either.

**Which means the kill criterion is not established, in either direction.**
Nothing was ever observed at ten, so the gate has certainly not *passed* — but
the evidence that it *failed* is a number this probe has just shown to be
unreliable. The honest status is **unresolved** — with one observation worth
keeping. In the quiet window, ten scanners measured **p95 366–369 ms in all
three repeats**, against a 250 ms budget, while the service's own frame cost
held flat at 32–33 ms. So ten is not marginal on this host; it is comfortably
outside, and closing that gap needs a materially cheaper frame rather than a
steadier laptop. **Whether x86 provides one is exactly what nobody has
measured**, and it is the only thing that can settle the gate.

**So the next step is a host, not another recovery.** A controlled 2-vCPU x86
box that is not also running the tooling is now the only way to get any absolute
figure at all. It was planned as a contingency if ARM reached ten; it is the
critical path.

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
  **Recorded as FIRED on 2026-08-17 and downgraded to UNRESOLVED on
  2026-08-18.** It fired on a measurement of 4 concurrent scanners that P8
  has since shown the host could not sustain - the same configuration gave 7
  hours later. A criterion cannot fire on a number that is not a measurement.
  **The recoveries were measured anyway, 2026-08-18
  ([P8](research/probes/P8-recovery-measurements.md)), and the reason has
  changed.** One recovery is real — a shared onnxruntime thread pool, worth
  −105 ms at p95 — and the highest figure ever observed under any configuration
  is **8**. *Cannot be recovered* is still not established, because the
  measuring host cannot supply an absolute number: the identical baseline gave 7
  and then 4 within one evening. **What the criterion now waits on is a
  controlled 2-vCPU x86 host**, not another idea. Do not quietly restate the
  gate as four, or as eight.
  **THE HOST RAN, 2026-08-21 ([P12](research/probes/P12-the-controlled-host.md)),
  and the gate FAILS at 5 against 10** — 2 at the six-bin frame the PRD calls
  normal. `representative: true`, three repeats within ~3 ms, on a box created
  for the measurement and destroyed after. The first half of the criterion is
  now established on evidence that can be quoted.
  **The second half — *cannot be recovered* — is NOT declared here.** What P12
  establishes is narrower and worth stating exactly: the frame costs 49 ms and
  would need ~25; P8b's shared thread pool was already applied; and of the two
  remaining recoveries on docs/05 § 7's list, 384 px is worth at best ~6 ms and
  capping crops is worth nothing at one bin per frame. **So the gate is not
  recoverable by anything currently on the list**, which is a statement about
  the list rather than about the thesis. Whether to fire this criterion — and
  therefore whether to cost a paid tier, shrink the validator, or revise the
  gate — is the maintainer's decision, and is deliberately left open rather than
  taken by the probe that produced the number.
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
