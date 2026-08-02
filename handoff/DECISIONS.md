# Design decisions

Answers to the questions Claude Design raised on delivering the first design
system, 2026-08-02. This file records what was **ratified** and what is still
open. [DESIGN-FOUNDATION.md](DESIGN-FOUNDATION.md) stays as written – it is the
brief, not a log, and it deliberately did not answer these.

---

## 1. Quoted colour – **ratified**

> The interface owns no colour. A real bin colour may appear only inside a
> **ColorQuote**: a bounded swatch carrying its translated name and a glyph.
> Colour is quoted like a citation, never worn.
>
> The one owned hue is **violet `#5B2E91`**, chosen as the gap in the real-world
> bin palette (blue, green, brown, black, grey, yellow, orange, red, white,
> metal – never violet), so the interface cannot be mistaken for the object.

This is kept, and it is stronger than the monochrome rule it replaced. The
reason it earns its place is not aesthetic:

**It makes it structurally impossible for the interface to assert a bin colour
it has not measured.** Colour only ever appears bound to a measured observation
and labelled with its own name. That is the same guarantee
[`RegionPack.is_publishable`](../ml/src/sbr/taxonomy.py) gives the rules layer,
expressed visually – and being confidently wrong is this product's worst failure
([AGENTS.md § Guardrails](../AGENTS.md)).

**Consequence, accepted:** no semantic green or red, because green is a glass
bank and red is hazardous. Yes / no / careful are carried by shape plus a word.

### What must not drift

- Colour never appears outside a ColorQuote. No coloured buttons, no tinted
  surfaces, no status colour.
- A ColorQuote always carries its translated name. A bare swatch asserts, which
  is the thing this rule exists to prevent.
- `unknown` has no ColorQuote at all. Absence is the signal.

### Caveat to keep in mind

Violet is the gap in the *German* palette. Some UK council schemes and other
systems do use purple containers, so "no bin is ever violet" weakens as the app
generalises. The mechanism does not depend on it – a quoted swatch is
structurally distinct from chrome regardless – but do not lean on that argument
in front of a municipality.

## 2. Wordmark – **Which Bin.** on the phone, **Smart Bin Recognition** formally

Two tiers, kept deliberately:

| Name | Where |
|---|---|
| **Which Bin.** | the app, the icon, anything a resident sees |
| **Smart Bin Recognition** | repo, docs, anything put in front of a city |

*Which Bin.* is the user's own question in two syllables, and the full stop
turns it from a query into an answer. It is better than *Smart Bin*.

**Open before this is final:** check domain availability and what the phrase
currently returns in search. "Which bin" is generic, and a public-good utility
people cannot find has a distribution problem. If findability is bad, the
two-tier split still stands – only the consumer half changes.

## 3. Contributor tools – **deferred, deliberately**

Not built out further in this round. Split/merge and pack editing are roadmap
phases 4–5, they depend on a registry schema and moderation flow that do not
exist yet, and dense data-manipulation UI is the least design-risky part of the
system – settled conventions already exist for it.

The next design round goes to the two screens that are neither settled nor
cheap to get wrong:

1. **Six bins in one frame.** A bank of containers is a normal input here, and
   it is where the ColorQuote rule is under most pressure – six bounded swatches
   with six translated names either stays calm or becomes a swatch grid.
2. **Unknown → contribute.** The most common result for months in any new city,
   and the entire growth engine.

---

## Handed back to the design

- **What colour is the detection box?** The camera view is the largest colour
  surface in the app and it is completely uncontrolled – the real bin, full
  bleed. If the box is violet, that is the one place the owned hue touches the
  object. Possibly the most interesting screen in the system.
- **Yes/no glyphs are the weak link.** A filled square against an outlined
  square, for the two states that matter most and must never be confused, is the
  lowest-salience encoding available – fill state reads poorly in sunlight on a
  cracked screen. The triangle for "careful" is right because its *shape*
  differs. Dropping semantic colour does not force weak shapes; three maximally
  distinct monochrome glyphs are available. Worth revisiting.

## Follow-ups outside the design

| Item | Why it matters |
|---|---|
| **Self-host IBM Plex; remove the Google Fonts `@import`** | A 2022 Munich district-court ruling found that hotlinking Google Fonts transmits the user's IP without consent in breach of GDPR, and set off a wave of warning letters in Germany. One district ruling is not settled law everywhere, but this is a German-facing civic app intended for municipal adoption – the wrong place to carry that risk. IBM Plex is OFL, so self-hosting is free and changes nothing visually. It also removes a render-blocking third-party request for users on poor connections. |
| **Test layout with real German strings** | German is the highest-risk *untested* locale, not the six flagged as Latin/Cyrillic – compounds run far longer than English and we have real strings today. Use `Verpackungsabfälle`, `Altkleidercontainer`, `Elektrokleingeräte`. |
| **Icons: Lucide is fine for now** | ISC licensed, ships without attribution obligations, and excluding the recycling triangle and leaf was the right instinct. A bespoke set is worth doing eventually; it is nowhere near the top of the list. |
| **Map and camera `<image-slot>` placeholders** | Expected. Real photography lands with the vision spike. |
