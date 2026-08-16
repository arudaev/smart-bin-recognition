# Documentation

Read in order on a first pass. After that, use the "read it when" column.

| # | Doc | Read it when |
|---|---|---|
| 00 | [Product requirements](00-product-requirements.md) | deciding whether something is in scope |
| 01 | [Architecture](01-architecture.md) | touching the runtime, device tiers, or the data plane |
| 02 | [Waste taxonomy](02-waste-taxonomy.md) | adding a stream, an item, or a city |
| 03 | [Registry, geo & trust](03-registry-geo-trust.md) | touching writes, geo, privacy or moderation |
| 04 | [ML pipeline](04-ml-pipeline.md) | training, exporting, evaluating |
| 05 | [Cost model](05-cost-model.md) | adding anything that scales with users |
| 06 | [Internationalisation](06-i18n.md) | adding user-visible text |
| 07 | [Roadmap](07-roadmap.md) | planning |
| 08 | [Legacy audit](08-legacy-audit.md) | wondering why something is the way it is |
| 09 | [Hackathon strategy](09-hackathon-strategy-2026-08-11.md) | deciding where to submit |
| 10 | [Hacksocial 2026](10-hacksocial-2026-participation.md) | the entry that is actually live |
| 11 | [Phase 2 results](11-phase2-results.md) | quoting a number about a model |
| 12 | [Validation protocol](12-validation-protocol.md) | **before hard-coding anything that is still a theory** |

## Research

[`research/`](research/) holds the evidence behind the numbers here — what
exists outside this repo and what it changes inside it. Every note names the doc
section it feeds. [`research/00-hardening-register.md`](research/00-hardening-register.md)
is the audit trail for the 2026-08-16 contradiction pass.

## Design

| Doc | For |
|---|---|
| [../handoff/DESIGN-FOUNDATION.md](../handoff/DESIGN-FOUNDATION.md) | the creative brief – attach to both Claude Design projects |
| [../handoff/README.md](../handoff/README.md) | how the handoff works, including both prompts |
| [../handoff/DECISIONS.md](../handoff/DECISIONS.md) | the design's answers – quoted colour, the wordmark, what was deferred |

## The short version

If you read nothing else, read these three claims and where they are argued:

1. **Inference runs on a server, streamed.** Nothing is downloaded to the
   device; two models run service-side and their disagreement drives the
   improvement loop. → [01](01-architecture.md#1-the-decision)
2. **The detector learns shapes, not meanings.** Colour is measured; meaning
   lives in a per-jurisdiction JSON file. Adding a country is a data change.
   → [02](02-waste-taxonomy.md#1-the-three-axes)
3. **Everything the user reads is static and translated at build time.** No
   runtime LLM translation of advice about what is safe to throw where.
   → [06](06-i18n.md#3-why-translations-are-static)
