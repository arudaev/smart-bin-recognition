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

**Status:** Phase 0 – foundation. Docs, taxonomy and ML skeleton exist; `web/`
is empty pending design.

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

web/                     React + TS + Vite client – EMPTY, pending Claude Design
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
| [handoff/DESIGN-FOUNDATION](handoff/DESIGN-FOUNDATION.md) + [handoff/DECISIONS](handoff/DECISIONS.md) | any UI work |

## Build & Run

```bash
# Python side
cd ml && pip install -e ".[dev]"
python -m pytest tests/ -q
python scripts/validate_taxonomy.py --skip-locales   # drop the flag once web/ exists
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

**TypeScript** (once `web/` exists):
- Layering `features → components → data → domain`; **`domain/` imports no
  framework**. The resolver lives there and is unit-tested without a browser.
- Style via the design system's own tokens, never hard-coded colour. The token
  set is Claude Design's to define; record it in a conventions file after import.
- **Logical CSS properties only** (`margin-inline-start`). Arabic is a launch
  locale; a physical direction property anywhere is a bug.
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
