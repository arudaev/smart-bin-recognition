# Research

Notes that inform the design docs without being them. A note here is a **decision
input**: it surveys what exists outside this repo, and then says what it changes
inside it.

## The rule

**Every note ends with "What this changes for us", naming the doc and section it
feeds.** A note that changes nothing is deleted rather than kept for interest.
This directory is not a reading list; it is the evidence trail behind the numbers
in `docs/00`–`docs/12` and [`docs/business/`](../business/).

Notes are **dated and append-only**. A finding that turns out wrong gets a new
dated section saying so – it is not edited into looking correct, because then the
decision it produced has no visible cause.

## Index

| # | Note | Feeds |
|---|---|---|
| 00 | [Hardening register](00-hardening-register.md) | the 2026-08-16 contradiction pass – closed out and frozen |
| 01 | [Detection and segmentation](01-detection-and-segmentation.md) | docs/04 § 3, § 6 |
| 02 | [Novelty and abstention](02-novelty-and-abstention.md) | docs/04 § 7, docs/07 kill criteria, `identifier.yaml` |
| 03 | [Data-engine patterns](03-data-engine-patterns.md) | docs/04 § 2, docs/12 |
| 04 | [Labelling and VLMs](04-labelling-and-vlms.md) | docs/04 § 3, docs/05 § 5 |
| 05 | [Serving economics](05-serving-economics.md) | docs/01 § 2, docs/05 § 3 |
| 06 | [Colour measurement](06-colour-measurement.md) | docs/02 § 1, docs/04 § 1 |
| 07 | [Compliance and consent](07-compliance-and-consent.md) | docs/01 § 7, docs/03 § 4 |
| 08 | [Video as the capture format](08-video-ingestion.md) | docs/04 § 3 § 5, docs/07 phases 2 and 6, `prepare.py` |
| 09 | [Business and market audit](09-business-and-market-context.md) | docs/business market segments, EVC and go-to-market |
| 10 | [Product-name screen](10-name-screen.md) | docs/business name and brand |
| 11 | [What is in the Open Images bin frames](11-open-images-form-factors.md) | docs/12 P1, the identifier's coverage gap, whether a second human pass pays |

Probe results live in [`probes/`](probes/) – one file per probe from
[docs/12-validation-protocol.md](../12-validation-protocol.md).

## What this directory is not

It is not a substitute for measuring. Every note here describes what other people
found on other data. The probes in docs/12 exist because **none of it transfers
to our bins until we run it on our bins.**
