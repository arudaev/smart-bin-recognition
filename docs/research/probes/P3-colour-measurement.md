# P3 – Colour measurement, body and lid

*Ran 2026-08-22. Raw data:
[`data/P3-colour-measurement.json`](data/P3-colour-measurement.json). Protocol in
[docs/12 P3](../../12-validation-protocol.md), **amended and committed at
`c25582d` before a single label was written**. Tooling:
`ml/scripts/colour_labels.py`.*

> ## PROVISIONAL. The labels were written by an agent.
>
> P3 says *hand-label*, and the maintainer was away for this run. The 160 labels
> scored below carry **`labeller: claude`** and are stored as
> `provisional_proposals: true`. **P3 does not close on them**, and no number on
> this page may be quoted without the word PROVISIONAL beside it.
>
> A **25-crop random spot-check** is pre-registered for the maintainer's return
> (`colour_labels.py spot-check`), and `--label` re-runs the full blinded pass
> over the same frozen 160 if the spot-check warrants it. Human rows win over
> agent rows automatically wherever both exist.

**Question.** Does illuminant normalisation beat naive sampling, is SAM needed —
and, added on 2026-08-22 because it became the product's binding constraint, can
a lid be measured at all?

---

## The verdict, in one table

| | measured | budget | fires |
|---|---:|---:|---|
| **body**, best of four variants | **0.5625** | ~0.75 | P3's **third** row |
| **lid**, upper band, wheelies with a visible lid | **0.1966** | 0.75 / 0.60 | the amendment's **third** row |

**Both halves miss, and they miss for different reasons.** That distinction is
the useful part of this probe and it took one extra measurement to establish.

---

## 1. Illuminant normalisation does not beat naive sampling. It loses to it.

P3's first question, answered directly. Body agreement over 160 crops:

| variant | agreement | unmeasurable (> ΔE 20) |
|---|---:|---:|
| (1) mean over the whole crop | 0.4500 | 1 |
| **(2) centre-weighted, no normalisation** | **0.5625** | 5 |
| (3) (2) + Gray World | 0.4875 | 2 |
| (4) (2) + Shades of Gray, *p* = 6 | 0.5437 | 2 |

**The variant the service actually ships — (4) — is not the best one, and (3) is
the worst of the three centre-weighted variants.** research/06 § 2 predicted
Shades of Gray would beat Gray World, and it does. It also predicted
normalisation would help, and on this corpus it does not: the plain centre sample
wins by 1.9 points over (4) and 7.5 over (3).

Why: these are overcast Bavarian street scenes, and the estimated gains are
tiny — measured per-channel gains cluster around `[1.01, 0.97, 1.03]`. There is
almost no illuminant to remove, so normalisation contributes noise rather than
correction. It would very likely earn its place at dusk or under sodium light;
this corpus contains neither, and **that is a gap in the corpus, not a finding
about the method**.

**SAM stays off the critical path.** P3's first decision row is *"(2) or (3)
within 5 points of the best → remove the mask dependency"*. (2) **is** the best.
No mask variant was needed to establish that, and none should be added:
segmentation cannot help a step whose failure is downstream of segmentation, as
section 2 shows.

## 2. The body geometry is right. The reference colours are wrong.

0.5625 looks like "colour is not measurable". It is not. Every scored sample was
also compared against **centroids measured from real bins** instead of the
taxonomy's `hex_ref` swatches, scored **leave-one-capture-cluster-out** over 99
held-out groups:

| | against `hex_ref` | against measured centroids |
|---|---:|---:|
| **body** | 0.5625 | **0.9125** |
| **lid** | 0.1966 | 0.5214 |

The audit says why. For each labelled colour, where real Deggendorf bins actually
sit in CIELAB against the swatch that names them:

| label | n | measured L\*a\*b\* | `hex_ref` L\*a\*b\* | ΔE | nearest reference to the measured centroid |
|---|---:|---|---|---:|---|
| `black` | 57 | 30.5, 0.0, −4.5 | 9.3, 0.0, 0.0 | 15.3 | `black` |
| `blue` | 28 | 44.3, 1.8, −38.7 | 35.4, 17.7, −52.4 | 9.9 | `blue` |
| `brown` | 31 | 44.3, 7.3, 12.0 | 32.7, 13.3, 26.5 | 12.8 | `brown` |
| **`green`** | 42 | 64.7, −10.8, 7.2 | 45.0, −40.9, 26.4 | **24.1** | **`metal`** |
| `grey` | 2 | 48.8, 1.6, −6.8 | 57.5, 0.0, 0.0 | 10.5 | `grey` |

**Read the `green` row twice.** A real ZAW glass igloo, measured through the
shipping pipeline, is closer to the `metal` swatch than to the `green` one. The
vocabulary describes **paint chips**; the objects are weathered plastic and
powder-coated steel under flat cloud. That is the single largest source of the
body error — `green->metal` is 29 of the 70 body mistakes.

**This is not a proposal.** `hex_ref` feeds every rule match in every region
pack, so changing it changes every resolution outcome the product has ever
produced. It is a taxonomy decision and the maintainer's. What this probe
contributes is the measurement of what it would buy: **0.5625 → 0.9125**, on
held-out clusters.

## 3. The lid cannot be measured by geometry, and it is not because lids are hidden

The obvious explanation is that a bin photographed head-on shows no lid. It is
wrong:

| | |
|---|---:|
| wheelies in the sample | 119 |
| **wheelies with a visible lid** | **117 (0.9832)** |
| lid agreement, strict | **0.1966** |
| lid agreement, neutrals collapsed | 0.4359 |
| lid agreement, recalibrated references, leave-one-cluster-out | 0.5214 |

**Lids are visible in 98 % of these frames.** The band also lands on them — the
overlay was rendered and inspected before this was written, and in twelve
sampled cases the red band sits squarely on the lid in every one. So this is not
a cropping failure and not a visibility failure.

It is that a lid is a **small, glossy, strongly-shaded** surface: it catches sky
at a grazing angle, and averaging a rectangle over it returns something
desaturated. 59 of 117 lids resolve to `metal` or `grey` regardless of their true
colour. And **recalibrating the references — which rescues the body completely —
takes the lid only to 0.5214, still below the 0.60 floor.**

### The rule fires, and it is the third row

> **< 0.60 → do not wire it.** Report that the Deggendorf pack matches wheelies
> on an axis this geometry cannot measure — which is a pack question, and the
> maintainer's.

**So `lid_color` stays `None` in `service/pipeline.py`.** Wiring in a sampler
that is right one time in five would take the product from *"answers `unknown`"*
to *"answers confidently wrong four times out of five"*, on disposal advice, in a
pack whose colour halves are already marked uncorroborated. `unknown` is a
designed state; a wrong `Restmüll` is the failure AGENTS.md names as this
product's worst.

**A wheelie in Deggendorf therefore still resolves to `unknown`, and this probe
is the reason it is allowed to.**

---

# Second act, 2026-08-22 — P3 answered the wrong question first

*Raw data: [`data/P3-rule-axis.json`](data/P3-rule-axis.json). Tool:
`ml/scripts/probe_rule_axis.py`. Same 119 wheelies, same sampler, same crops.*

Everything above is a correct answer to *"can the service measure a lid?"* The
prior question is **"what does the pack need to know, and what is the cheapest
measurable thing that supplies it?"** — and it was never asked. Two facts that
arrived from elsewhere make it unavoidable:

1. **[research/12](../12-deggendorf-packaging-evidence.md) found the
   municipality naming the containers**: *„die **graue** Restmülltonne, die
   **braune** Biotonne und die **blaue** Papiertonne"*, and *„**grüne**
   Wertstoffinseln"*. **That is a statement about the bin, not about its lid.**
   The pack's `lid_color` rules were never what the source says.
2. **The lid is also the worse axis**, on P3's own labels, before measurability
   enters the argument at all:

| stream | by **body** colour | purity | by **lid** colour | purity |
|---|---|---:|---|---:|
| `bio` | brown | **100 %** | brown | 100 % |
| `paper` | blue | **90 %** | blue | 90 % |
| `residual` | black | **96 %** | grey | **74 %** |

Restmüll bins in Deggendorf are black-bodied with grey lids about three times in
four, and black-lidded the rest of the time. **The body is the more constant
surface.** The pack chose the axis that is both harder to see and less
informative.

## What happens if the rules move to `body_color`

The whole chain, measured: real frame → real crop → **the shipping sampler** →
a candidate rule carrying the *same streams and same colours the pack already
has* → scored against the **legacy archive's own stream label**, which is human
and entirely independent of the colour labels.

| the rule matches on | resolves | **correct stream** |
|---|---:|---:|
| `lid_color` — what the pack does today | **0 / 119 (0 %)** | **0 / 119 (0 %)** |
| `body_color`, sampler as deployed, `hex_ref` unchanged | 114 / 119 (95.8 %) | 92 / 119 (77.3 %) |
| `body_color`, sampler + **recalibrated references** | **119 / 119 (100 %)** | **113 / 119 (95.0 %)** |
| `body_color`, with perfect colour — the ceiling | 119 / 119 | 116 / 119 (97.5 %) |

**Two data edits — an axis and a set of reference swatches — take wheelies from
"never answers" to "answers, and is right 95 % of the time".** No new model, no
segmentation, no schema change: `body_color` is already in
`region-pack.schema.json` and already used by `deg-packaging-sack`.

### This also validates the provisional labels

The recalibrated centroids are fitted to agent-written colour labels, but they
are scored against **`legacy_class`**, which no part of this pipeline touched.
A badly wrong label set could not produce centroids that predict an independent
variable at 95 %. That is not a substitute for the pre-registered spot-check —
it is evidence the spot-check is likely to confirm rather than overturn.

### The 5 % that is still wrong, and why it matters

| n | what happened |
|---:|---|
| 3 | `paper` bins that are genuinely **black-bodied** — measured black, routed to residual |
| 3 | `bio` bins measured grey or black instead of brown |

**Five per cent confidently wrong about where rubbish goes is not automatically
acceptable**, and this probe does not decide that it is. Three of the six errors
are bins that a *person* could not classify by colour either — a black Papier
bin is black. Those need the `text_hint` axis, which is already in the wire and
in the schema and is measured by nothing. Whether 95 % ships, or ships behind a
confidence floor with `unknown` below it, is a **product decision and the
maintainer's**.

## What this leaves the maintainer

Three decisions, none of them taken here:

1. **Recalibrate `hex_ref` against measured centroids?** Worth 0.5625 → 0.9125 on
   the body. Changes every pack's resolution behaviour. Needs the human labels
   first.
2. **Drop illuminant normalisation from the shipping path?** It currently costs
   1.9 points on this corpus. But the corpus is all overcast daylight, so the
   honest answer may be *"keep it and get a dusk corpus"* rather than *"remove
   it"*.
3. **The pack matches wheelies on `lid_color`. Nothing can measure that.** Either
   the rules move to an axis that is measurable, or wheelies stay `unknown` in
   Deggendorf. This is the one that decides whether the product answers for the
   commonest bin in its pilot city.

## What this probe did not do

- **It did not close.** Agent labels, disclosed as such, spot-check pre-registered.
- **It did not touch the region pack**, `waste-streams.json`, or any form-factor id.
- **It did not try segmentation.** Section 2 shows the failure is downstream of
  where a mask would help, so SAM would have been an expensive way to not fix it.
- **It has no dusk, rain or sodium-light frames**, because the corpus has none.
  Every number here is *overcast Bavarian daylight* and should be quoted that way.
