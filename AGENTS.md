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

**Status:** phase 1 (design) is done and phase 3's client half is done; the
vision spike (phase 2) and the service are not. See
[`docs/07-roadmap.md`](docs/07-roadmap.md) for the checklist. Docs, taxonomy and
the ML skeleton are in place. `web/` holds the design imported from Claude Design –
the design system, both surfaces, every designed state – running against the
real resolver and the real Deggendorf pack. On top of that it now has the
camera, the four gates, the streaming client, a service worker with the offline
split docs/01 § 6 states, an installable manifest, a settings surface, a
performance budget, and 188 tests.

**The one thing still missing is the service.** `service/` is empty, so with no
`VITE_DETECT_WS` configured the client talks to an in-process mock and says so
on the settings screen. Everything else on the client side is real: the loop
that mock drives is the same loop a socket will drive, and swapping one for the
other is one environment variable.

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
├── configs/                    default.yaml + detector.yaml (_defaults_ deep merge)
├── src/sbr/
│   ├── taxonomy.py             ontology + region packs + the resolver
│   ├── config.py               YAML inheritance, cloud guard
│   ├── dataset/legacy_import.py  2.15 GB / 4 German classes -> resized, remapped
│   ├── dataset/prepare.py        group-aware + region-holdout splits
│   ├── export/onnx_export.py     ONNX int8 + the four ship gates
│   ├── escalation/schema.py      stage-3 VLM contract
│   └── utils/hub.py              HF token, download, upload
├── kaggle/train_detector/      self-contained GPU kernel
├── scripts/                    dispatch.py, validate_taxonomy.py
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
├── src/transport/              the wire contract, socket, REST, and the in-process mock
├── src/perf/                   metric vocabulary, budgets, web vitals
├── src/pwa/                    registration, update flow, install prompt
├── src/app/                    session model: answered / confirmed / reported
├── src/components/             the 26 design-system components
├── src/features/               scan, answer, rules, contribute, firstrun, desk, settings
├── src/i18n/                   en (complete) + de/ar (~65%), and t()
├── src/styles/tokens/          the design system's token layer
├── src/test/                   fake clock, fake camera, fake service; the discipline test
└── src/dev/                    state director + metrics overlay – development only

service/                 FastAPI + ONNX inference service (HF Space) – EMPTY
docs/                    Architecture, PRD, cost model, i18n, roadmap, audit
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
| [web/CONVENTIONS](web/CONVENTIONS.md) | **any UI work – read this first** |
| [handoff/DESIGN-FOUNDATION](handoff/DESIGN-FOUNDATION.md) + [handoff/DECISIONS](handoff/DECISIONS.md) + [handoff/FLOW-NOTES](handoff/FLOW-NOTES.md) | why the UI is the way it is |

## Build & Run

```bash
# Web side
npm --prefix web install
npm --prefix web run dev          # http://localhost:5173
npm --prefix web run verify       # typecheck, tests, locales, build, bundle budget
npm --prefix web test             # 188 tests, no browser
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

# Import the predecessor's dataset (needs cv_garbage.zip from the v1.0.0 release)
python -m sbr.dataset.legacy_import --archive cv_garbage.zip --out data/legacy

# Training – Kaggle GPU only, never local
python scripts/dispatch.py push detector --version 1
python scripts/dispatch.py status detector
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
  Different blast radii.
- **Never add a per-inference paid API to the common path.** The €0 constraint
  is architectural. If a feature needs one, it is the wrong feature.
- **Never ship a model that misses its latency budget** (validator ≤ 50 ms
  @ 448, identifier ≤ 25 ms per crop, on service CPU). Concurrency is the cost
  ceiling, so latency is the budget. The build fails; it does not warn.
- **Never remove the client-side gates** (motion gate, 4 fps cap, result lock,
  20 s abort). They are load-bearing infrastructure, not polish – without them a
  single user can consume a third of total capacity.
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
