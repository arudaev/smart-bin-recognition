<h1 align="center">Smart Bin Recognition</h1>

<p align="center">
  Point your phone at a bin. Learn what it is and what goes in it –<br/>
  in your language, anywhere.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-client_built_%7C_service_pending-1A1A1A?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/inference-streamed-1A1A1A?style=for-the-badge" alt="Streamed inference">
  <img src="https://img.shields.io/badge/models-validator%20%2B%20identifier-1A1A1A?style=for-the-badge" alt="Two models">
  <img src="https://img.shields.io/badge/License-MIT-1A1A1A?style=for-the-badge" alt="MIT">
</p>

---

## The problem

Colour coding for waste bins is not standardised. It changes by country, by
state, sometimes by contractor within one city. The rules exist – every
municipality publishes them – as a PDF, in the local language, which is no help
when you are standing outside in the rain holding a yoghurt pot.

For someone who has just moved to a new country, this is a daily, low-grade,
entirely solvable problem.

## The product

Point the camera. Every bin in frame gets boxed and labelled. Each one gets a
card: what it is, what it is called locally, what goes in, what does not, and the
mistakes people actually make. In your language.

If it does not recognise a bin, it says so plainly and offers to find out – which
is how coverage grows.

Devices without a rear camera never see a camera interface. They get the map, the
registry, the rules browser and, for contributors, moderation tools.

## How it works

The phone captures frames and streams them over a WebSocket. Nothing is
downloaded to the device – no model, no cache. Two models run on the server:

| | Question | Trained on | Failure mode |
|---|---|---|---|
| **A · Validator** | "Is there a bin, and where?" | bins **+ a 30:1 negative corpus** | misses a bin (rare) |
| **B · Identifier** | "What kind of bin?" | curated crops from A | says `unknown` (useful) |

**Their disagreement is the product's engine.** The premise is that finding a
bin generalises across cities while identifying one does not – so when A says
*"definitely a bin"* and B says *"no idea"*, that is not an error: it is a bin
type nobody has seen before, and it goes straight into the collection queue. New
geographic cell, or a user correcting the answer, does the same.

Identification is also decoupled from geography. Model B learns **physical form
factors** – a 240 L wheelie bin, a bottle bank, a textile container. Colour is
*measured* from pixels, never learnt. What a blue lid *means* lives in a
per-jurisdiction JSON file, so adding a country is a pull request against a data
file rather than a retraining run.

Flagged frames are auto-labelled offline (GroundingDINO → SAM 2 → a vision model
for semantics, clustered so a human adjudicates a group rather than an image),
then folded into the next training round. The more it is used, the fewer unknowns
it has.

## Where this came from

The **Deggendorf Waste Sorting Assistant**, a TH Deggendorf computer-vision
project by Sameer, Fares and Alex – 466 hand-captured photos, a fine-tuned
YOLOv8, and a Streamlit app. It worked as coursework and stalled as a product:
inference ran request-per-frame against a sleeping free container, so live camera
was unusable; labels were German-only because the model's class names *were* the
interface strings; and the rules were a hard-coded dict with no notion of
location.

Its own closing slide listed the fixes: multi-language support, mobile or web
integration, and municipal pickup schedules. Those are, in order, this project's
requirement, architecture and roadmap.

The name is from slide 3 of that same deck: *"Our Solution – Smart Bin
Recognition."* It was always the better name.

Full analysis: [`docs/08-legacy-audit.md`](docs/08-legacy-audit.md).

## Repository

```
data/taxonomy/    21 canonical waste streams, 10 form factors, region packs
ml/               Python – dataset import, auto-labelling, Kaggle dispatch, export
service/          FastAPI + ONNX inference service (pending)
web/              React + TypeScript PWA – both surfaces, offline rules, the scan loop
docs/             architecture, PRD, cost model, i18n, roadmap, legacy audit
handoff/          Claude Design handoff – design system, prototype spec, tokens
```

## Documentation

| | |
|---|---|
| [Product requirements](docs/00-product-requirements.md) | scope, personas, success criteria, risks |
| [Architecture](docs/01-architecture.md) | streaming topology, the two models, device tiers |
| [Waste taxonomy](docs/02-waste-taxonomy.md) | the ontology, region packs, adding a city |
| [Registry, geo & trust](docs/03-registry-geo-trust.md) | clustering, staleness, privacy, abuse |
| [ML pipeline](docs/04-ml-pipeline.md) | the two models, auto-labelling, the improvement loop, evaluation |
| [Cost model](docs/05-cost-model.md) | what is free, and where the concurrency ceiling really is |
| [Internationalisation](docs/06-i18n.md) | 9 locales, static bundles, why not runtime translation |
| [Roadmap](docs/07-roadmap.md) | phases, gates, kill criteria |
| [Legacy audit](docs/08-legacy-audit.md) | what the predecessor was, what survived |
| [Design handoff](handoff/README.md) | design system, prototype spec, and the prompts |

## Development

```bash
npm --prefix web install
npm --prefix web run dev        # http://localhost:5173
npm --prefix web run verify     # typecheck, tests, locales, build, bundle budget
npm --prefix web run preview    # a real build, so the service worker registers
```

```bash
cd ml
pip install -e ".[dev]"
python -m pytest tests/ -q
python scripts/validate_taxonomy.py --skip-locales
```

Agent guide: [`AGENTS.md`](AGENTS.md). Before any UI work,
[`web/CONVENTIONS.md`](web/CONVENTIONS.md).

## Status

**The client is built; the service is not.** `web/` is an installable PWA with
both surfaces, real URLs, the camera path and its four gates, the offline rules
browser, a performance budget that fails the build, and 236 tests that need no
browser. It
runs today against an in-process mock and the settings screen says so, because a
client that implies a service exists is worse than one that admits it does not.
`service/` is empty; swapping the mock for a socket is one environment variable.

Documentation, taxonomy and the ML skeleton are in place. The predecessor's
model has been independently re-validated on CPU against the complete archive
([results](docs/08-legacy-audit.md#7-measured-2026-08-01)): it scores 0.987
mAP@0.5 in-distribution, and also hallucinates a glass container on a slide of
plain text while missing three real bins in a photograph – which is the evidence
the two-model design rests on. The vision spike is next.

Known gaps, stated rather than discovered later: `de` and `ar` are at 65 % and
fall back to English, six locales are not started, and the Deggendorf region
pack is `draft` – not servable until its rules are verified against the
operator's published guidance.

## Licence

MIT. The disposal rules are a public good and will never sit behind a paywall.

## Acknowledgements

TH Deggendorf; Prof. Dr. Glauner (Computer Vision); Sameer and Fares, who
collected and labelled the 466 photographs this project is still built on.
