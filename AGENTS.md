# Smart Bin Recognition – Development Guide

> Canonical agent guide for this repo. Read by Codex, Claude Code (via
> `@AGENTS.md` in `CLAUDE.md`), and anything else that loads `AGENTS.md`.
> Edit **this** file – `CLAUDE.md` is a pointer.

## Project Overview

Point your phone at a waste bin; learn what it is and what goes in it, in your
language, anywhere. A web app plus the ML pipeline behind it. Free to users and
free to run at pilot scale; the binding constraint is inference concurrency, not
bandwidth – see [`docs/05-cost-model.md`](docs/05-cost-model.md).

Successor to the *Deggendorf Waste Sorting Assistant*
(`PROJECTS/06-Painfully-Trivial`), a TH Deggendorf computer-vision project. The
name comes from that project's own presentation, slide 3: *"Our Solution – Smart
Bin Recognition."* Full analysis of what carried over and what did not:
[`docs/08-legacy-audit.md`](docs/08-legacy-audit.md).

**Status:** phase 1 is done. Phase 3's two halves are built and joined: the wire
is pinned to shared byte fixtures across both languages, the degradation ladder
runs end to end, and CI covers `ml/`, `service/` and `web/`.

**Phase 2's gate was measured on a controlled host on 2026-08-21
([P12](docs/research/probes/P12-the-controlled-host.md)). Both latency halves
PASS and the concurrency half FAILS.**

| half | budget | measured, `representative: true` | verdict |
|---|---|---|---|
| validator @ 448 | ≤ 50 ms | **18.3 ms** p50 | **pass** |
| identifier @ 320 per crop | ≤ 25 ms | **9.9 ms** p50 | **pass** |
| concurrent scanners @ 1 bin | ≥ 10 | **5** | **FAIL** |
| concurrent scanners @ 6 bins | – | **2** | the PRD's normal input |

GCE `n2-standard-4`, CPU platform pinned, service on CPUs 0–1 and the load-test
client on 2–3, three repeats within ~3 ms, box destroyed after. **These replace
the withdrawn 4 and 1 — quote 5 and 2, and name the host.** P4's corrected
arithmetic predicted 4.3–5.1 and 1.8–2.2; both measurements land inside.
The frame costs 49 ms and would need ~25, with P8b's shared thread pool already
applied, so **the gate fails on compute rather than on tuning**. Whether that
fires the kill criterion is the maintainer's decision and is left open.
See [`docs/07-roadmap.md`](docs/07-roadmap.md).

**Two things changed on 2026-08-18, and both are about believing numbers**
([probe P8](docs/research/probes/P8-recovery-measurements.md)):

- **The concurrency figure had no trustworthy absolute value.** Bracketing a
  measurement block with the same baseline at both ends gave **7 at 22:30 and 4
  at 23:48**. `docker run --cpus 2` is a cgroup ceiling rather than a floor, and
  the laptop was also running the development tooling, so the container was
  starved. **Superseded 2026-08-21**: the controlled host ran and the figure is
  **5 at one bin, 2 at six**. Do not quote 4, 7 or 8 — they were never
  measurements. Quote 5 and 2 and name the host.
- **The training run's failure is understood, and it is not ours.** The Kaggle
  image ships **torch 2.10.0+cu128**, which dropped `sm_60`, and the platform
  allocates **P100 (sm_60)** as well as T4 (sm_75). `torch.cuda.is_available()`
  returns `True` and the first tensor move then raises — which is why the
  2026-08-16 run pulled the pool, built the dataset, wrote `args.yaml` and died
  with no weights and no log. Established by a rung that installs **nothing**
  (`smoke_gpu`: `installed_anything: false`), after the first explanation —
  that `pip install ultralytics` had replaced torch — turned out to be wrong.
  **The remedy is to ask for a T4, and asking works.** `machine_shape:
  "NvidiaTeslaT4"` in `kernel-metadata.json` (equivalently
  `kaggle kernels push --accelerator`) was honoured on 2026-08-18: *Tesla T4,
  capability sm_75, torch 2.10.0+cu128 - usable*. **The training path is
  unblocked.** Every GPU kernel here requests one. An earlier version of this
  note said no such field existed; that was wrong. The capability check
  (`sbr.utils.gpu`) stays as the belt to those braces and runs **before the
  pool is pulled**, so a bad allocation does not pay for the download.

**Both models now exist, and one of them passes every gate.**

**Say it precisely, because the two halves differ.** The identifier passes all
four ship gates when `gate.py` is run against P12's measurement, and the local
sidecar reads `may_ship: true`. **The sidecar published in the model repo still
reads `may_ship: false`**, with latency unmeasured — publishing that verdict is
the maintainer's decision and was deliberately withheld. So the accurate claim
is *"passes every gate and is eligible for publication"*, not *"ships"*.

- **Identifier — passes every gate as of 2026-08-21.** Three classes
  (`wheelie_small`, `wheelie_large`, `igloo`), decided by the maintainer on
  [P1](docs/research/probes/P1-form-factor-separability.md)'s evidence. int8
  costs **0.0000** top-1 against a 0.02 budget, and 9.9 ms per crop against a
  25 ms budget on representative hardware. **Its evidence is thin and says so**:
  `test` top-1 is 1.0000 on **47 crops**, of which `igloo` is three from two
  capture clusters, and the 95 % lower bound is 0.936. P1's 0.9834 out-of-fold
  over all 403 crops is the better estimate.
  [P11](docs/research/probes/P11-identifier-int8.md).
- **Validator — still cannot ship.** Trained 2026-08-18, test mAP@0.5 0.7524,
  specificity 0.9793 on 2 662 background frames. int8 costs it 0.727 mAP.

**So the service still refuses to start on gated artefacts**, because it loads
the validator unconditionally and the validator's sidecar says `may_ship: false`.
Nothing is deployed, and that remains correct rather than pending.

*(Retained for the record:)* The service refuses to start without an
artefact whose sidecar says `may_ship`, and the validator **trained on
2026-08-18 and cannot ship**. It is a real model — test mAP@0.5 0.7524, specificity 0.9793 on
2 662 background frames — and **int8 quantisation costs it 0.727 mAP against a
0.02 budget**, collapsing it to 0.025. The service serves int8 by construction,
so `may_ship: false` stands and the refusal is correct.

**That is now diagnosed and still not cleared** ([P9](docs/research/probes/P9-int8-quantisation.md),
2026-08-21). **Quantising the detection head is what collapses it**: leaving
`/model.23/` in fp32 takes the model from 0.015 to **0.7481** on `val` — a
50-fold recovery — for +5.7 ms on a Kaggle x86 proxy and +1.2 MB. It does *not*
follow that nothing outside the head matters: that graph is still quantised
everywhere else and still loses 0.0252, and the residual is unattributed. The
three remedies onnxruntime names for this failure mode (S8S8, `reduce_range`,
U8U8) all stay at collapse, as does per-tensor, so this is not the x86 saturation
case it resembled, and the pre-registered combined run made things worse. **The best configuration is 0.0252 below the PyTorch fp32 reference
against a 0.02 budget — missed by 0.0052, and the gate does not move.** Whether to
take a 0.025 trade is a product decision; it would need a `test` measurement,
and there deliberately is none, because nothing was eligible and the split was
left unspent. Post-training int8 over the whole graph is not viable for this
architecture: any future YOLO11 export here starts from `exclude_head=True`.

Google Cloud is provisioned, budgeted and documented, and nothing is deployed,
because deploying a graph that scores 0.025 would make the product confidently
wrong.

**Verified by deployment on 2026-08-22, not by reading the flag.** A
production-equivalent private Cloud Run deploy of `detect@sha256:cd52b20b` was
attempted and **the container refused to start**:
`UngatedArtefactError: validator v1 ... failures: int8 quantisation cost 0.727
map50 (max 0.02)`. That is the gate working. A separate, clearly-labelled
*temporary* private revision with `SBR_ALLOW_UNGATED=1` then confirmed the
infrastructure — authenticated `/health` and `/detect` return 200, anonymous
returns **403 proven by request** — and was deleted; `gcloud run services list`
is empty. **The web client still cannot be pointed at anything**, because
`web/src/transport/rest.ts` sends no `Authorization` header, so it needs a
*public* service, and a public service serving disposal answers needs a validator
that genuinely passes.

**fp32 is the open route, and it is now measured.**
[P13](docs/research/probes/P13-fp32-validator-viability.md), 2026-08-22, both
formats paired on one Cascade Lake instance with the arms alternated:

| | int8 | fp32 | budget |
|---|---:|---:|---:|
| validator p50 | 17.921 ms | **24.605 ms** | ≤ 50 ms — **both pass** |
| concurrent scanners @ 1 bin | 5 | **4** | ≥ 10 |
| accuracy cost | −0.727 mAP | 0.0 | ≤ 0.02 |

The ship gate at `ml/src/sbr/export/onnx_export.py:319` refuses unquantised
artefacts with the rationale *"it will not meet the latency budget"*. **That
rationale is false by a factor of two at 448 on this architecture.** The trade is
**one concurrent scanner for a validator that is actually correct**, in a gate
that fails either way. The split is implemented, tested and **staged unmerged on
`feat/fp32-ship-profile`** with a memo at
[`docs/research/FP32-PROFILE-MEMO.md`](docs/research/FP32-PROFILE-MEMO.md);
`max_accuracy_drop` stays `0.02` in every profile and the config raises if a
profile tries to loosen it.

**Where to look without a terminal:** `python ml/scripts/build_dashboard.py`
regenerates [`docs/dashboard.html`](docs/dashboard.html) from the repository's
own evidence files — every artefact, gate, curve and coverage gap, each figure
beside the split and hardware it came from, and `unknown` wherever a source file
is missing.

**Phase 2's data is done and pinned, for both roles.**

- **validator** — `arudaev/smart-bin-detect` at `8666aa23`: 18 954 frames, 370
  legacy, 1 110 Open Images bins including the only frames with four or more
  bins, 17 474 background.
- **identifier** — `arudaev/smart-bin-identify` at `cda374c9`, **private**: the
  same legacy pool with `crops/` and the human pass applied. 403 crops, all 403
  adjudicated, 0 pending, 0 rejected. Its contract asserts the **per-class
  counts**, not just the totals, because 403 crops can stay 403 crops while
  every label underneath them changes.

**The human pass is DONE** — all 403 crops, reviewer `alex`, run `--blind`, and
the pool's shipped stream→shape proposals are wrong on **116 of 403**. What is
left on the validator is an int8 export that survives quantisation, and
[P10](docs/research/probes/P10-where-the-residual-lives.md) established that no
module outside the detection head accounts for the residual.

**Coverage gap, and it does not close from data on hand.** B knows three of ten
form factors. `street_basket` is dropped at n=1 in one cluster; six ids have no
data at all. [research/11](docs/research/11-open-images-form-factors.md)
surveyed 384 Open Images boxes and found **zero** `underground`, `textile_bank`
or `wall_unit` — that corpus is 35 % `street_basket` and cannot close the gap.
`sack` and `textile_bank` both carry Deggendorf pack rules, so a pilot there
will meet bins B cannot name.

**A working pipeline still answers `unknown` for wheelies, and since
2026-08-22 there is a measurement saying why rather than a gap.**
[P3](docs/research/probes/P3-colour-measurement.md) ran against 160 labels on a
frozen, cluster-stratified sample:

| | measured | rule | fires |
|---|---:|---:|---|
| body colour, best of four variants | **0.5625** | ~0.75 | P3's third row |
| lid colour, upper band | **0.1966** | 0.60 | *do not wire it in* |

- **`lid_color` is deliberately NOT wired into the service.** Lids are *visible
  in 98 %* of the 117 scored wheelie frames and the band lands on them, so this
  is neither a cropping nor a visibility failure. A sampler right one time in
  five would take the product from "answers `unknown`" to "answers confidently
  wrong four times in five", on disposal advice, in a pack whose colour halves
  are already marked uncorroborated. `service/colour.py` has the sampler and
  `service/tests/test_lid_colour.py` pins the omission as deliberate.
- **Illuminant normalisation loses to naive sampling** on this corpus — 0.5625
  plain, 0.5437 Shades-of-Gray, 0.4875 Gray World — because the gains are ~1.0
  under flat cloud. **SAM stays off the critical path.**
- **The failure is the reference swatches, not the geometry.** Against centroids
  measured from real bins, leave-one-capture-cluster-out over 99 groups, body
  agreement goes **0.5625 → 0.9125**; the lid reaches only 0.5214. Real ZAW
  igloos measure closer to the `metal` swatch than to `green`. **Recalibrating
  `hex_ref` is a taxonomy decision and the maintainer's** — it changes every
  resolution outcome in every pack.
- **P3 is PROVISIONAL and does not close.** The labels were written by an agent
  (`labeller: claude`, `provisional_proposals: true`) because the maintainer was
  away. A 25-crop spot-check is pre-registered:
  `python ml/scripts/colour_labels.py spot-check`.

`web/` holds the design imported from Claude Design –
the design system, both surfaces, every designed state – running against the
real resolver and the real Deggendorf pack. On top of that it now has the
camera, the four gates, the streaming client, a service worker with the offline
split docs/01 § 6 states, an installable manifest, a settings surface, a
performance budget, and **281 unit tests plus 13 browser tests**. The browser
tests exist because two bugs reached this repository by somebody looking at a
screen — a Surface Pro 11 opening its selfie camera, and the scanner drawn as a
phone on a 1440-wide tablet — and neither was reachable from vitest, which has no
layout. Both are fixed; the camera fallback is unit-tested against an injected
`MediaDevices` because Chromium's fake device cannot emulate two *labelled*
cameras, so the claim there is **"implemented and browser-tested, Surface
hardware confirmation pending"** and not more. The shell around all of it is a real
application shell as of `refactor/web-app-shell`: real URLs on a hand-rolled
History API router, the theme on `<html>`, `100dvh` and safe-area insets rather
than a drawn phone, and the state director dynamically imported so it leaves
the production bundle entirely.

The client defaults to the in-process mock and **says so on the settings
screen** — the transport is named there, `mock` or `rest` or `socket`. Swapping
one for the other is one environment variable.

**It has now been run against the real thing.** On 2026-08-21, with
`VITE_DETECT_URL` pointed at a local service serving the real validator and the
gated identifier, the settings screen named **`rest`** and the browser reached
`/detect` from `http://localhost:5173` over CORS. Real Deggendorf frames through
that path return real detections — a glass bank resolves to
`glass_mixed` / "Glascontainer"; a wheelie is detected and named and then
resolves to `unknown`, because the pack's wheelie rules need a lid colour
nothing measures. Nothing is deployed, and the default is still the mock.

## The three decisions that define this repo

Understand these before changing anything structural.

1. **Inference runs on a server, streamed over a WebSocket.** No model is
   downloaded to any device. The client captures frames, gates them hard
   (motion, cadence cap, result lock), and draws boxes. Two models run
   server-side: a **validator** ("is there a bin?") and an **identifier**
   ("which bin?"). Their disagreement is the active-learning signal.
   → [`docs/01-architecture.md`](docs/01-architecture.md)

2. **The detector learns shapes, not meanings.** Its ten classes are *form
   factors* (`wheelie_small`, `igloo`, `textile_bank`, …). Colour is **measured**
   from pixels, not learnt. Meaning comes from a per-jurisdiction **region pack**
   – a JSON file. Adding a country is a data change, not a retrain.
   → [`docs/02-waste-taxonomy.md`](docs/02-waste-taxonomy.md)

3. **Everything the user reads is static, translated at build time.** Closed
   item vocabulary, ~390 strings, 9 locales. No runtime LLM translation of
   safety-relevant advice – it would cost money per scan and be
   non-deterministic about what is safe to throw where.
   → [`docs/06-i18n.md`](docs/06-i18n.md)

## Repository Layout

```
data/taxonomy/           The product's spine – the vision model is a lookup key
├── waste-streams.json          21 canonical streams, 10 form factors, closed item vocabulary
├── waste-streams.schema.json
├── region-pack.schema.json
└── regions/*.json              one per jurisdiction; de-by-deggendorf is DRAFT

ml/                      Python: dataset, training dispatch, export
├── configs/                    default.yaml + validator/identifier/open_images/legacy_archive
├── src/sbr/
│   ├── taxonomy.py             ontology + region packs + the resolver
│   ├── config.py               YAML inheritance, cloud guard
│   ├── dataset/pool.py           the on-disk layout: shards, and the Hub's 10k-file cap
│   ├── dataset/archive.py        the legacy archive's contract; refuses a short copy
│   ├── dataset/legacy_import.py  370 usable frames -> resized, provenance, crops
│   ├── dataset/open_images.py    negative corpus + out-of-city bins
│   ├── dataset/prepare.py        group-aware + region-holdout splits, per role
│   ├── export/onnx_export.py     ONNX int8 + the four ship gates
│   ├── escalation/schema.py      stage-3 VLM contract
│   └── utils/hub.py              HF token, download, upload
├── kaggle/                     train_validator, train_identifier, build_negatives
├── scripts/                    dispatch, adjudicate, gate, push_dataset, inventory_legacy
│   ├── colour_labels.py          docs/12 P3: sample, label, spot-check, score
│   └── build_dashboard.py        docs/dashboard.html, from tracked evidence only
└── tests/

web/                     React + TS + Vite PWA – design imported from Claude Design
├── CONVENTIONS.md              READ FIRST for any UI work: vocabulary + idiom
├── api/                        Vercel edge functions: pack/[region], regions
├── public/sw.js                the offline policy, hand-written and readable
├── public/manifest.webmanifest installable; icons any / maskable / monochrome
├── scripts/                    build-icons, check-locales, check-bundle
├── src/domain/                 resolver, freshness, geohash – no framework, ever
├── src/data/                   taxonomy, region packs + offline cache, frames, registry
├── src/capture/                capability probe, camera, the four gates, encoder, loop
├── src/transport/              the wire, socket, REST, mock, and __fixtures__/ -
|                               bytes shared with service/tests/test_wire_contract.py
├── e2e/                        Playwright: the tablet composition, both themes, RTL
├── src/perf/                   metric vocabulary, budgets, web vitals
├── src/pwa/                    registration, update flow, install prompt
├── src/app/                    what spans screens: routes, theme, preferences, session
│   ├── routes.ts               the URL map and every redirect – no framework
│   ├── useRoute.ts             the History API half, and only that
│   ├── theme.ts                data-theme / dir / lang / theme-color on <html>
│   ├── preferences.ts          mode + locale + onboarded, localStorage, guarded
│   └── answers.ts              answered / confirmed / reported
├── src/components/             the 26 design-system components
├── src/features/               scan, answer, rules, contribute, firstrun, desk, settings
├── src/i18n/                   en (complete, 422 keys) + de/ar (64%), and t()
├── src/styles/tokens/          the design system's token layer
├── src/test/                   fake clock, fake camera, fake service; the discipline test
└── src/dev/                    state director + metrics overlay – development only,
                                and enforced so: dynamically imported behind a DEV
                                branch, and check-bundle.mjs fails if it reaches dist

service/                 FastAPI + ONNX inference service (Cloud Run)
├── app.py                      the two transports, /health, the load-shedding edge
├── artefacts.py                sidecar loading and the refusal on may_ship
├── shed.py                     the degradation ladder's three rungs
├── wire.py                     the framing; pinned to web/ by shared byte fixtures
├── loadtest/                   the concurrency measurement – a client, not in the image
└── deploy/                     cloudrun.sh, cloudbuild.yaml, and the runbook
    └── gce-fp32.sh + gce-latency-paired.sh   P13: both weight formats, one host
docs/                    Architecture, PRD, cost model, i18n, roadmap, audit
├── business/                   market, model, EVC, go-to-market, validation, naming
└── research/                   dated evidence notes and probe results
handoff/                 Claude Design handoff: DESIGN-FOUNDATION.md + the two prompts
```

## Documentation map

| Doc | Read it when |
|---|---|
| [00-product-requirements](docs/00-product-requirements.md) | deciding whether something is in scope |
| [01-architecture](docs/01-architecture.md) | touching the runtime, device tiers, or the data plane |
| [02-waste-taxonomy](docs/02-waste-taxonomy.md) | adding a stream, an item, or a city |
| [03-registry-geo-trust](docs/03-registry-geo-trust.md) | touching writes, geo, privacy or moderation |
| [04-ml-pipeline](docs/04-ml-pipeline.md) | training, exporting, evaluating |
| [05-cost-model](docs/05-cost-model.md) | adding anything that scales with users |
| [06-i18n](docs/06-i18n.md) | adding user-visible text |
| [07-roadmap](docs/07-roadmap.md) | planning |
| [08-legacy-audit](docs/08-legacy-audit.md) | wondering why something is the way it is |
| [11-phase2-results](docs/11-phase2-results.md) | quoting a number about a model |
| [12-validation-protocol](docs/12-validation-protocol.md) | **before hard-coding anything still theoretical** |
| [docs/business/](docs/business/README.md) | deciding who uses, buys, pays, how value is measured, how the product goes to market, or what it is called |
| [docs/research/](docs/research/README.md) | the evidence behind the numbers, and the 2026-08-16 hardening register |
| [web/CONVENTIONS](web/CONVENTIONS.md) | **any UI work – read this first** |
| [handoff/DESIGN-FOUNDATION](handoff/DESIGN-FOUNDATION.md) + [handoff/DECISIONS](handoff/DECISIONS.md) + [handoff/FLOW-NOTES](handoff/FLOW-NOTES.md) | why the UI is the way it is |

## Build & Run

```bash
# Web side
npm --prefix web install
npm --prefix web run dev          # http://localhost:5173
npm --prefix web run verify       # typecheck, tests, locales, build, bundle budget
npm --prefix web test             # 281 tests, no browser
npm --prefix web run test:e2e     # 13 browser tests; needs `npx playwright install chromium`
npm --prefix web run preview      # a real build, so the service worker registers

# Point the client at a service. With neither set it uses the in-process mock
# and says so on the settings screen.
#   VITE_DETECT_WS=wss://…/stream     live streaming scan
#   VITE_DETECT_URL=https://…/detect  one frame per request

# Python side
cd ml && pip install -e ".[dev]"
python -m pytest tests/ -q
python scripts/validate_taxonomy.py --locales en   # de/ar bundles are incomplete
ruff check src/ scripts/ tests/

# Import the predecessor's dataset (needs cv_garbage.zip from the v1.0.0 release).
# Refuses to run against a copy that does not match ml/configs/legacy_archive.yaml.
python scripts/inventory_legacy.py --archive-dir cv_garbage
python -m sbr.dataset.legacy_import --archive-dir cv_garbage --out data/legacy/pool

# The human pass: form factors for the legacy crops. Blocks the identifier only.
python scripts/adjudicate.py --pool data/legacy/pool
python scripts/adjudicate.py --pool data/legacy/pool --apply

# docs/12 P3: body and lid colour. `sheets` is the agent's front door and
# `label` the human's; both write to one record tagged with who wrote each row.
python scripts/colour_labels.py sample
python scripts/colour_labels.py spot-check --reviewer alex -n 25   # <- the pending one
python scripts/colour_labels.py score

# The evidence dashboard, generated from tracked files. Nothing is hand-typed.
python scripts/build_dashboard.py --out ../docs/dashboard.html

# Training – Kaggle only, never local
python scripts/dispatch.py push negatives  --version 1   # CPU: corpus + OOD bins
python scripts/dispatch.py push validator  --version 1
python scripts/dispatch.py push identifier --version 1
python scripts/dispatch.py status validator

# Ship gate: latency measured on the 2-vCPU bench Space, not here
python scripts/gate.py --role validator --version 1
```

## Conventions

**Python** – inherited from CheXVision because they worked there:
- 3.10+, type hints throughout, ruff (`E,F,I,N,W,UP,B`, line length 120), mypy.
- `pathlib.Path` everywhere; never raw string paths.
- All hyperparameters in `configs/*.yaml`. Nothing that affects a run is
  hard-coded in source.
- Seed `torch`, `numpy`, `random`, CUDA in every training run.
- **No notebooks.** The predecessor's central artefact was a notebook that could
  not reproduce its own model. Logic lives in `src/` or `scripts/`.
- No local GPU training – `sbr.config.assert_cloud()` enforces it.

**TypeScript** – the full account is [`web/CONVENTIONS.md`](web/CONVENTIONS.md);
read it before any UI work. In short:
- Layering `features → components → data → domain`; **`domain/` imports no
  framework**. The resolver lives there and is unit-tested without a browser.
- Style with inline style objects referencing the design system's CSS custom
  properties. Never a hard-coded colour, size, radius or duration.
- **Logical CSS properties only** (`margin-inline-start`). Arabic is a launch
  locale; a physical direction property is a bug everywhere except
  `DetectionMarker`, which overlays a photograph and documents why.
- Colour is **quoted, never worn**: a real bin colour appears only inside a
  `ColorQuote` swatch carrying its translated name.
- One `t()` key per string. Never concatenate translated fragments.
- Every state has a **URL**, and every correction to one is `replaceState`.
- The theme goes on `<html>`, never on a wrapper. `app/theme.ts` is the only
  thing that writes it.

**Data:**
- Stream ids and form-factor ids are **permanent**. Never rename a published id
  – packs, datasets and users' cached data all reference them.
- Detector class order is the ONNX class index. Reordering silently invalidates
  every deployed model. It is pinned by a test.
- A region pack reaching `status: published` requires every source to carry a
  URL and a retrieval date. Enforced in `RegionPack.is_publishable`.

## Guardrails

Things that must not happen, and why:

- **Never assert a disposal rule without a region-pack entry.** Being
  confidently wrong about what goes in which bin is this product's worst
  failure. `unknown` is a designed state – use it.
- **Never let user input reach training data without human label review.**
  Consensus is enough to publish a pack entry; it is not enough to train on.
  Different blast radii. This is absolute and turns on the **provenance of the
  image**, not the confidence of the label: high-agreement machine labels may
  auto-accept over a *public corpus we harvested*, never over a frame a user
  contributed, and never for a form factor that has no data yet
  ([04 § 4](docs/04-ml-pipeline.md)).
- **Never add a per-inference paid API to the common path.** The €0 constraint
  is architectural. If a feature needs one, it is the wrong feature.
- **Never state a claim as measured when it is assumed.** A number needs the
  split and the hardware it came from, and a gate needs something that actually
  measures it — int8 accuracy had no owner until 2026-08-16 and no artefact could
  ship. Anything still theoretical gets a probe in
  [docs/12](docs/12-validation-protocol.md) before it gets hard-coded.
- **Never ship a model that misses its latency budget** (validator ≤ 50 ms
  @ 448, identifier ≤ 25 ms per crop, on service CPU). Concurrency is the cost
  ceiling, so latency is the budget. The build fails; it does not warn.
- **Never remove the client-side gates** (motion gate, 4 fps cap, result lock,
  20 s abort). They are load-bearing infrastructure, not polish – without them a
  single user can consume a third of total capacity.
- **Never choose the surface by viewport width or user-agent.** It is
  `routes.ts:surfaceFor` over the capability probe, and only `tier: "viewer"`
  gets the viewer. A tablet with a rear camera at narrow width is a scanner and
  a phone in landscape is still a scanner; deciding on width gives the right
  answer for the wrong reason and is wrong the first time somebody rotates a
  device. The override in `dev/DevTools.tsx` is the single exception and cannot
  reach a build.
- **Never let development-only code into the bundle.** Not "rendered only in
  dev" – *absent*. Panels that return null still carry their props, and the
  director's labels are every state name in the product. Dynamic import behind
  an `import.meta.env.DEV` branch; `scripts/check-bundle.mjs` fails the build.
- **Never quote the predecessor's 95.2 % mAP** as this project's baseline. It
  was measured on a random split of one week's photos in one city. See
  [08-legacy-audit § 6](docs/08-legacy-audit.md#6-numbers-to-treat-with-suspicion).

## Git & Commits

**Before committing:** `pytest`, `ruff check`, and
`python ml/scripts/validate_taxonomy.py` all pass.

- **Never commit directly to `main`.** Branch with a typed prefix – `feat/`,
  `fix/`, `chore/`, `docs/`, `ci/`, `refactor/`, `test/` – and open a PR.
- Conventional Commits: `type(scope): summary`, imperative, lower-case, no
  trailing period, ≤ 72 chars.
- One logical change per commit; each commit should build.
- **No AI attribution.** No `Co-Authored-By:` trailers, no "Generated with…"
  lines, no bot signatures. Commits are authored solely by the human maintainer.

## External Resources

| Resource | Id |
|---|---|
| Dataset | `arudaev/smart-bin-detect` (HF, planned) |
| Model | `arudaev/smart-bin-detect` (HF, planned) |
| Kaggle kernel | `hlexnc/sbr-train-detector` (planned) |
| Predecessor | [`arudaev/Painfully-Trivial`](https://github.com/arudaev/Painfully-Trivial) |
| Legacy assets | release `v1.0.0`: `waste_detector_best.pt` (22.5 MB), `cv_garbage.zip` (2.15 GB) |

Tokens live in `.env` at the repo root (gitignored): `HF_TOKEN`,
`KAGGLE_API_TOKEN`, `GITHUB_TOKEN`.
