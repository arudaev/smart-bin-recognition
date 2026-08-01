# Smart Bin – Design System

> Attach this file to a **Claude Design → Design System** project.
> Self-contained: everything needed to build the system is here.

---

## 1. What this system is for

A civic utility used outdoors, one-handed, in a hurry, by people who cannot read
the local language. Every decision serves that.

The user is standing next to a bin, holding rubbish, in whatever weather, on
whatever phone they own. They need one answer fast and they need to trust it.

## 2. The one idea

> **The interface is monochrome. The only colour in the product is the colour of
> the bin.**

This is the identity. It is inherited from the source presentation this project
grew out of, which was pure black on white with colour appearing only inside
photographs.

It works because it is also functionally correct:

- Bin colour is the highest-signal feature of the real object, so putting only it
  in colour makes the screen a direct mirror of what the user is looking at.
- It is unmistakable – a screenshot is instantly identifiable as this product.
- It is honest about uncertainty: when the system does not know, **there is no
  colour**, and that absence reads instantly without any text.
- Accessibility falls out for free: with nothing else competing, every colour
  chip can carry a text label and a distinct icon, so colour is never the sole
  carrier of meaning.

**Rules, absolute:**

- No brand colour. No accent colour. No gradient. No coloured buttons.
- Black, white and a short grey ramp are the entire chrome palette.
- Bin colour appears in exactly three places: a solid chip, a detection box
  stroke, and a thin leading rule on the result card.
- Semantic colour is permitted only in the ✅ / ❌ rule lists, where the glyph and
  the label carry meaning and colour merely reinforces.

## 3. Visual language

Swiss/International Typographic: structure carried by typographic weight and
whitespace, never by boxes or shadows.

**Signature moves, all from the source deck:**

- Small bold **eyebrow** above a very large bold heading.
- **Generous leading margin** – content starts well inside the frame, never
  centred (except on first-run and empty states).
- **Hairline rules** as the primary divider. Rules and space, not borders and
  elevation.
- One full-strength rule used as a horizontal spine, with items hung above and
  below it.
- Occasional *italic + underline* on a single word as the only text accent.

### Typography

**Inter** (variable) for Latin/Cyrillic/Greek. **Noto Sans Arabic** and **Noto
Sans Devanagari** for the scripts Inter does not cover.

| Role | Size | Weight | Notes |
|---|---|---|---|
| Display | clamp(2.25rem, 7vw, 3.5rem) | 800 | tracking −0.02em, line-height 1.05 |
| Title | clamp(1.5rem, 4.5vw, 2rem) | 700 | |
| Heading | 1.25rem | 700 | card headings |
| Body | 1rem | 400/500 | line-height **1.55** |
| Small | 0.9375rem (15px) | 400 | **the floor** |
| Eyebrow | 0.8125rem | 700 | sentence case |
| Micro | 0.75rem | 400 | timestamps and metadata only |

**Never set body text below 15 px on mobile.** Much of the audience is reading a
second or third language and needs the room.

### Colour tokens

Chrome (light):
`--ink #000` · `--ink-secondary rgba(0,0,0,.62)` · `--ink-tertiary rgba(0,0,0,.42)`
`--surface #fff` · `--surface-sunken #f4f4f4`
`--rule rgba(0,0,0,.12)` · `--rule-strong rgba(0,0,0,.9)`

Dark is a **true dark** (`--surface #000`), not grey – it is used outdoors at
night and on OLED phones.

Bin colours (the only colour):
`blue #1F4FA8` · `green #1E7A3C` · `brown #6B4423` · `black #1A1A1A` ·
`grey #8A8A8A` · `yellow #F2C200` · `orange #E8720C` · `red #C1272D` ·
`white #F2F2F2` · `metal #9BA3A8` · `transparent` · **`unknown` = no colour**

In dark mode `black` lightens to `#4A4A4A` so a black bin stays visible on black.

Semantic, rule lists only: `--yes #14722F` · `--no #A81E1E` · `--caution #8A6100`.

### Space, shape, motion

4 px base scale. Leading margin `clamp(1rem, 6vw, 4rem)`. Body measure 68ch.

Radii: 0 / 4 / 10 (image cards) / 16 (sheets) / full (chips).
**Exactly one shadow exists**, for the bottom sheet. Everything else uses rules.

Motion: 120 ms (detection box settle) / 180 ms / 240 ms, ease-out, no bounce, no
spring. Detection boxes **ease into place rather than snapping per frame** –
raw per-frame jitter reads as broken even when the result is right. Under
`prefers-reduced-motion`, boxes update without transition and nothing else moves.

Full token file: `handoff/tokens.css` in the repository.

## 4. Components

Build these. Names are suggestions; behaviour is not.

**Primitives** – Button (primary/secondary/quiet, min 48 px target) · IconButton ·
Chip · **BinColorChip** (solid swatch + always a text label; renders as a dashed
outline when unknown) · Rule · Eyebrow · Skeleton · Toggle · Stepper ·
LanguageSelect (endonyms only, no flags, no translated language names).

**Composites** –

- **ResultCard** – colour chip · stream name (user's language, large) · local name
  (secondary, the word printed on the bin) · ✅ list · ❌ list · ⚠ commonly
  confused · footer with staleness + source + report link.
  States: confident · hedged · asking · unknown · stale · pending.
- **DetectionOverlay** – boxes in bin colour, eased, with short labels; grey when
  low confidence; dashed grey when unknown.
- **ResultSheet** – bottom sheet, collapsed (count + summary) → expanded (cards).
- **StatusPill** – the connection/quality state. Quiet, persistent, never alarming.
- **StalenessLabel** – relative time + a consistent visual weakening.
- **ItemRow** – icon + label for an accepted/rejected item.
- **MapPin** – bin colour, clustered, staleness-aware.
- **EmptyState** – always paired with the one useful action available.

**Icons** – single-weight line, monochrome, legible at 20 px. Needed: 10 bin form
factors (two-wheel bin, four-wheel container, bottle bank, underground column,
textile bank, street basket, sack, crate, wall unit, container bank), ~21 waste
streams, and UI chrome. **No emoji anywhere** – the predecessor used 🗑️ 🥬 📰 and
that must not survive.

## 5. Non-negotiables

A system that misses any of these cannot ship.

1. **RTL and non-Latin at v1.** Arabic (RTL), Hindi (Devanagari), Ukrainian and
   Russian (Cyrillic) are launch locales. **Logical CSS properties only** –
   `margin-inline-start`, never `margin-left`. Any physical direction property is
   a bug. German compounds run ~40 % longer than English; layouts must absorb it.
2. **Outdoor legibility.** Direct sunlight, wet screen, gloved hands. High
   contrast, 48 px minimum targets, no thin light-grey text on anything that
   matters.
3. **One-handed reach.** Every primary action on mobile sits in the bottom third.
   The other hand is holding rubbish. This is literal.
4. **WCAG 2.2 AA.** Full keyboard path, screen-reader-complete result cards, and
   a text-only route to every rule – the product must be fully usable by someone
   who never opens the camera.
5. **Colour is never the only signal.** Every bin colour is accompanied by a text
   label and a form-factor icon.
6. **No dark patterns.** No streaks, points, badges, or engagement machinery. This
   is a utility people should use rarely and successfully.

## 6. Tone

Plain, calm, short. The reader is mildly stressed and in a foreign language.

✅ "Paper and cardboard" · "No, not here" · "We don't know this bin yet" ·
"Scanning needs a connection"

❌ "Detection successful!" · "Oops! Something went wrong 😅" · "Analyzing…"

No exclamation marks. No emoji. Never say *model*, *confidence score*,
*inference*, *class*, *YOLO*, or *AI* in user-facing copy.

Uncertainty is spoken, and it gradates:

| Certainty | Voice |
|---|---|
| high | "This is a paper bin." |
| medium | "This looks like a paper bin." |
| low | "This might be a glass container – which slot are you at?" |
| none | "We don't know this bin yet." |

## 7. Avoid

Green "eco" branding, leaves, recycling arrows, earth tones, sustainability
gradients – the monochrome rule exists partly to make these impossible.
Also: dashboards, metric tiles, FPS or technical readouts, emoji icons,
onboarding carousels, modals for routine actions.
