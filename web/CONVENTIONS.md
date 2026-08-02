# web/ conventions

Written after importing the design from Claude Design. This is the equivalent of
Kaffeelisten's `.design-sync/conventions.md`: it records the vocabulary and the
idiom that actually exist here, so later sessions build *with* the system rather
than around it.

Read [`../handoff/DESIGN-FOUNDATION.md`](../handoff/DESIGN-FOUNDATION.md) for
why the design is the way it is, and
[`../handoff/DECISIONS.md`](../handoff/DECISIONS.md) for what was ratified.

**Source of truth for the design:** Claude Design project
`74e61a2c-69e3-4758-b83e-8d0f3ce4c5a3`, bound to design system
`3b3cb5ca-7fa0-4985-95aa-c785cde0f2be`.

---

## Layering

```
features/  →  components/  →  data/  →  domain/
```

Imports point one way only.

| Directory | What lives there | Rule |
|---|---|---|
| `domain/` | resolver, types, freshness | **No framework.** No React, no DOM, no fetch. Unit-tested without a browser. |
| `data/` | taxonomy loader, region packs, fixtures | Reads JSON. No components. |
| `components/` | the 26 design-system components | No domain logic, no `t()` calls – strings arrive as props. |
| `features/` | screens | Composes everything. Where `t()` is called. |
| `app/` | session model that spans screens | `answerFor` lives here because it joins resolver output to session state. |
| `dev/` | the state director | Dev-only. Not part of the system; styled deliberately unlike it. |

`domain/resolver.ts` is a mirror of `ml/src/sbr/taxonomy.py`. **The docs are the
specification, not either implementation.** If you change one, change both, and
`docs/02-waste-taxonomy.md` first.

## Styling idiom

The design system uses **inline style objects referencing CSS custom
properties**. There is no CSS-in-JS library, no utility framework, and no
component stylesheet. This is Claude Design's own idiom and it was kept so the
components stay diffable against their source.

```tsx
style={{ padding: "var(--space-5)", borderRadius: "var(--radius-2)" }}
```

Rules that are not negotiable:

- **No hard-coded colour, size, radius or duration.** Every value is a token
  from `src/styles/tokens/`. The one exception is `DetectionMarker`, which hard-
  codes `#16181C` / `#FCFBF8` in a `drop-shadow` filter because filters cannot
  read custom properties.
- **Logical properties only.** `marginInlineStart`, never `marginLeft`;
  `inlineSize`, never `width`. Arabic is a launch locale.
  - *One exception, documented in the file:* `DetectionMarker` positions its box
    with physical `left`/`top`, because it overlays a photograph and a
    photograph does not mirror under RTL.
- **Colour is quoted, never worn.** A real bin colour appears only inside
  `<ColorQuote>` – a bounded swatch carrying the colour's translated name. Never
  a background, never a border, never a status. `unknown` gets no swatch.
- **Meaning is never carried by colour alone.** Verdicts differ in outline class
  first (disc / struck box / bare triangle), and `RuleGroup` states the verdict
  in words above the rows.
- **The one owned colour is `--signal` violet**, and it never touches the
  camera surface.

### Theming

Three modes, set with `data-theme` on an ancestor: unset (paper), `sun`,
`night`. `sun` is not a light-mode default – it is a higher-contrast, heavier-
ruled mode for reading outdoors at noon. Direction comes from `dir` on the same
element and `lang` drives the font stack.

## The component set

| Group | Components |
|---|---|
| core | `Button` `IconButton` `Card` `Tag` `Icon` |
| domain | `ResultCard` `RuleGroup` `ItemRule` `ColorQuote` `LocalName` `StreamGlyph` `Freshness` `DetectionMarker` |
| feedback | `StatusStrip` `Notice` `EmptyState` `Sheet` |
| forms | `TextField` `ChoiceTile` `Stepper` `LanguageList` |
| navigation | `TopBar` `SegmentedControl` `ListRow` |

Import from `@/components`, never from the file. Icons are Lucide (ISC), inlined
in `components/core/Icon.tsx` – add a glyph by pasting its SVG body, not by
adding a dependency.

`STREAM_GLYPH` maps every waste stream to a literal object glyph. It deliberately
avoids recycling triangles and leaf motifs; those are anti-references.

## Copy

- **One `t()` key per string.** Never concatenate translated fragments.
- Interpolate by name: `t("desk.mapTitle", { place })`.
- Sentence case everywhere except the mono register voice
  (`.sbr-register`, `<Tag>`), which is uppercase because it states a fact about
  the record rather than answering the user.
- No exclamation marks.
- Use `t.has(key)` for genuinely optional copy so an intentional absence is not
  logged as a gap.

`en.json` is complete and is verified by `ml/scripts/validate_taxonomy.py`.
`de.json` and `ar.json` are about 60% and fall back to English; run
`npm run check:locales` for the gap.

## Prose

En dashes (–), never em dashes (—). This holds in comments and copy alike.

The exception is Arabic, which keeps its own dash conventions – three strings in
`ar.json` use an em dash, correctly. Do not "fix" them.

## Commands

```bash
npm --prefix web run dev
npm --prefix web run build
npm --prefix web test
npm --prefix web run typecheck
npm --prefix web run check:locales
```

The taxonomy validator is on the Python side and covers the locale bundles:

```bash
python ml/scripts/validate_taxonomy.py --locales en
```

## What this prototype is not

- **There is no camera.** `Scanner` renders fixtures from `data/frames.ts`. The
  real client captures frames, gates them (motion, 4 fps cap, result lock, 20 s
  abort) and streams them to the service over a WebSocket.
- **There is no model.** If anything here imports an inference runtime it is in
  the wrong repository.
- **The surface switch is a prototype affordance.** It is labelled by capability
  – scanner or viewer – rather than by screen size, because real detection is a
  probe for an environment-facing camera and never a viewport query. A shell
  that switched on width would teach the wrong model to whatever is built from
  it.
- **`de-by-muenchen-demo` is not a real region pack.** It exists in
  `data/regions.ts` so the published-coverage state can be seen, and it must
  never be moved into `data/taxonomy/regions/`.
