# Business model

## Model in one sentence

Residents use the product free; an institution pays a fixed fee for verified
coverage and an operated service, or a software vendor licenses the proven
capability.

That is a hypothesis. There is no customer, price, or conversion evidence.

## What the institution would buy

Not "AI" and not an app download. The sellable unit is:

- source-backed setup for a named site or jurisdiction;
- mapping from physical bin appearance to the local rule pack;
- reviewed translations and accessible presentation;
- managed inference, monitoring, updates, and support;
- a documented abstention and correction process;
- optional integration into an existing resident surface.

The public PWA is the proof and access surface. The institutional product is the
work and accountability required to keep an answer local, current, and safe.

## Two credible routes

### 1. Managed-site service

Sell directly to a residence, housing operator, campus facilities owner, or
waste operator with a bounded deployment.

```text
fixed setup + annual maintenance/support
```

This route is easier to test and can fund a small service. Its ceiling may be
low because each site has limited budget and region-pack work may remain manual.

### 2. Vendor integration

After the capability is proven, offer it to a municipal-app vendor as a module
or API integrated into its existing apps and content systems.

```text
integration fee + annual licence/support
```

This route has leverage because vendors already hold municipal distribution and
contracts. It is also harder: vendors can decline, copy the feature, or require
security, service levels, and integration capacity this project does not yet
have.

Direct municipal sales are not a third strategy by default. In Deggendorf, ZAW
already uses Abfall+. A direct sale must solve a gap the incumbent and operator
both recognise.

## Offer ladder

| Offer | Contains | Commercial evidence required |
|---|---|---|
| Discovery | workflow review and baseline definition | recent problem and named owner |
| Design partnership | fixed demonstration, source review, pilot design | site access, authority participation, baseline data, decision date |
| Bounded pilot | one site/cohort, support, evaluation and error process | written scope and either a fee or a concrete procurement path |
| Managed service | verified coverage, hosting, maintenance and support | measured user outcome and budget owner |
| Vendor module | documented boundary, integration, service level and support | proven capability, repeatable pack process and vendor demand |

A free pilot is acceptable only if it purchases otherwise unavailable evidence:
site access, authority review, baseline data, a publishable case study, or a
budgeted continuation decision. It is time-boxed.

## Free and paid boundary

| Always free to residents | Potential institutional service |
|---|---|
| Scan and receive an evidence-backed answer | establish and verify coverage |
| Browse cited local rules | maintain sources and translations |
| Use accessibility and supported languages | integrate with institutional systems |
| Use cached rules offline | managed capacity, service levels and support |
| Contribute only with explicit consent | deployment and staff enablement |

No municipal dashboard is offered. It remains post-v3 and has no customer.
Anonymous operational counters may prove service quality; they are not an
analytics product.

## Pricing logic

Do not publish price bands before the work and customer value are known.

```text
delivery floor = setup labour + recurring labour + infrastructure
                 + support/risk reserve

value ceiling = customer-specific EVC

test price must be > delivery floor and < value ceiling
```

The first price should be fixed by scope and term. Do not charge per resident or
per scan: it makes access a cost to suppress and gives the buyer an unpredictable
bill. Do not price from hosting cost alone; cheap infrastructure does not mean
the verified service is valueless.

## Costs that decide whether this works

- authority-source acquisition and review;
- human verification of each region pack;
- translation maintenance;
- site photography or form-factor coverage gaps;
- integration, security and procurement work;
- inference, monitoring and incident response;
- support when the model abstains or the rule is disputed;
- onboarding labour for the second and later sites.

The technical cost model remains in
[`../05-cost-model.md`](../05-cost-model.md). The business case fails if human
onboarding and maintenance grow roughly one-for-one with sites while customers
will not fund that work.

## Non-models

- consumer subscription;
- advertising;
- selling user, image, or location data;
- paywalled public rules;
- a paid runtime LLM in the normal path;
- a speculative analytics dashboard;
- revenue based on unreviewed user-contributed training data;
- GitHub sponsorship presented as customer validation.

## Decision table

| Evidence | Direction |
|---|---|
| Managed site owns measurable cost and funds continuation | pursue direct managed service |
| Operator values the capability and incumbent vendor can integrate it | pursue vendor partnership |
| Users benefit but no operational owner or budget exists | keep it grant/sponsor-funded and stop calling it SaaS |
| Bin-first task does not beat the existing alternative | stop commercialisation of this product scope |
| Revenue requires weaker privacy, evidence, or abstention | reject the revenue path |
| Second-site labour is not repeatable | narrow geography or charge the real setup cost |
