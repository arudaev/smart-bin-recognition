# Hackathon strategy: August–September 2026

Decision date: 11 August 2026.

## Decision

**Participation selected: Hacksocial 2026, solo.** The commitment and binding
requirements are recorded in
[`10-hacksocial-2026-participation.md`](10-hacksocial-2026-participation.md).
This selection supersedes the earlier suggestion to use VoltHacks as the
current milestone. The future Devpost playbook will define the submission
scope; this screening document continues to describe the canonical product
boundary, hosting and later competition route.

> Historical-screening note: references below to VoltHacks are not current
> participation requirements and must not be implemented unless a later
> playbook explicitly reauthorizes that event.

The plausible environment/social-good listings were not good enough:

- Hack the Habitat has contradictory eligibility text and placeholder dates;
- Hacksocial's advertised value is largely software, courses, domains, and
  credits rather than cash, so it is an optional 31 August packaging deadline;
- VoltHacks requires significant new development for an existing project and
  inflates its headline with memberships and vendor credits, so it is useful as
  a product deadline rather than an expected source of prize income;
- AI Builders and several larger events require a project created during the
  event.

Before starting, ask VoltHacks whether the planned inference service,
Deggendorf pack, abstention flow and pilot evidence satisfy its significant-new-
development rule, and ask whether a private inference core may be shared with
judges. Ask Hacksocial whether the pre-existing client is eligible. Changing the
architecture to chase either event is not justified.

## Previously considered VoltHacks slice

The following was the screened VoltHacks option and is not the selected 2026
entry. It remains useful as a description of canonical product evidence:

1. a working server-streamed inference path from PWA to service;
2. a verified Deggendorf region pack with source provenance;
3. an honest abstention/unknown-bin result;
4. German guidance for the demonstrated flow;
5. fixed evaluation fixtures plus latency, false-bin and abstention results;
6. a short live-camera demonstration and a no-camera fallback.

Estimate **40–65 focused hours** and **USD 0–9 personal spend**. If the working
service is not connected by 24 August, skip VoltHacks and continue the canonical
roadmap without a submission.

## Canonical next milestone

1. Complete the validator/identifier vision spike on the existing feature
   branch.
2. Select models using the frozen out-of-distribution gates, not only mAP.
3. Implement the FastAPI/ONNX WebSocket service and connect the existing client
   transport.
4. Verify the Deggendorf pack against operator-published guidance.
5. Complete German and retain the honest fallback status for unfinished
   locales.
6. Run a consented pilot and measure latency, abstention, false-bin rate, and
   municipality-rule misses.

## PRD reconciliation required before public launch

`docs/00-product-requirements.md` still contains on-device/no-frame-upload
language, while the README, architecture, cost model, and canonical agent guide
define server-streamed inference. Before a public demo, update the PRD to state
one consistent design:

- frames are downscaled and gated on device before transmission;
- inference frames leave the device only after explicit camera/inference
  consent;
- transport is encrypted and the service does not persist frames by default;
- telemetry contains derived operational metrics, not raw images;
- a clearly labelled opt-in path is required for donating difficult examples;
- offline mode provides rules browsing and cached data, not camera inference;
- retention, deletion, abuse-rate limits, and municipality-data provenance are
  acceptance criteria.

This document proposes that reconciliation; it does not modify the PRD.

## Hardware and hosting update

Training can remain public and reproducible on Kaggle. Its current documentation
describes a weekly GPU quota of roughly 30 P100 hours, subject to demand. Export
ONNX artifacts to the Hugging Face Hub with dataset/model cards and licenses.

The original “free Hugging Face Space” cost assumption needs qualification.
Hugging Face now states that creating a Gradio or Docker Space requires a PRO
account at **USD 9/month**, although CPU Basic has no hourly compute charge. The
8-vCPU CPU Upgrade is **USD 0.03/hour** while running.

Recommended pilot alternatives:

| Layer | Zero-cost-first choice | Paid fallback |
|---|---|---|
| PWA | Vercel Hobby/static host | Existing provider's paid tier only if traffic requires it |
| Inference | Google Cloud Run, minimum instances `0`, 1 CPU model, capped concurrency | HF PRO CPU Basic at USD 9/month or HF 8-vCPU at USD 0.03/hour plus PRO |
| Registry | Supabase Free with municipality pack cache | Supabase Pro from USD 25/month only after a measured need |
| Training | Kaggle free GPU quota | Short rented GPU run only for a failed quota window |
| Artifacts | Public Hugging Face model/dataset repositories | Paid storage only after published limits are measured |

Target pilot spend: **USD 0–9/month**. Set a hard ceiling of **USD 20 for the
first month**, including one temporary GPU experiment. Do not put a paid VLM on
the normal recognition path.

## Future hackathon entry standard

Enter only an event that explicitly permits existing projects and for which the
new work is canonical, such as a verified new city pack, measurable model
improvement, accessibility/offline enhancement, or municipality feedback loop.
Tag the pre-event baseline and disclose the predecessor dataset, contributors,
and every metric's evaluation distribution.

## Public product/private core note

The public PWA should build in demo mode without access to a private repository.
Use a versioned WebSocket/HTTP boundary to the private inference service. Do not
compile private weights into browser JavaScript or WASM, and do not make a
private Git submodule mandatory for public contributors. A project-specific
GitHub Sponsors tier can grant read access to an organization-owned private core
for individual self-hosters; SaaS billing and API limits remain separate.

## Product classification and final direction

Smart Bin Recognition has a **B2C entry surface** and a **B2G/B2B2C scale
model**. The citizen-facing PWA is a free public-good application. The durable
platform is the municipality registry, verified region-pack system, inference
service, contribution workflow, and later deployment/support surface.

It is not primarily a consumer subscription SaaS and it is not a generic
photograph-your-trash classifier. If it develops revenue, the credible buyers
are municipalities, waste operators, campuses, housing providers, and mobility
or city-service platforms. They may pay for onboarding, verified data
maintenance, integrations, analytics, deployment, or support while resident
access remains free.

The competition transition is:

> coursework waste classifier -> city-aware bin recognition application ->
> multilingual municipal disposal decision infrastructure

## 2027 competition route

1. **Prototypes for Humanity 2027** is the primary target. The 2026 call was
   free, accepted individual university students, evaluated impact,
   technological application, and academic rigor, and supported selected
   projects attending its summit. The 2027 call and dates are not yet
   published.
2. **WSA Young Innovators 2027** is a later validation target if the age rule is
   met. It requires a launched, market-ready digital solution with proven
   social or environmental impact; a prototype is not enough.
3. **Imagine Cup 2027** is conditional. Registration is open and solo teams are
   allowed, but the current requirement for two operational Microsoft AI
   services may distort the zero-cost canonical architecture. Do not add those
   dependencies until the definitive 2027 rules and deadlines are checked.

The competition version must show a verified Deggendorf pack, honest
abstention, multilingual guidance, latency and recognition measurements, and a
consented user pilot. It may claim improved user decision accuracy only when
measured; it may not infer citywide contamination reduction from a small demo.
