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
| `app/` | what spans screens: the router, the theme, preferences, the session | `answerFor` lives here because it joins resolver output to session state. `routes.ts`, `theme.ts` and `preferences.ts` are framework-free for the same reason `domain/` is – all three are policy, and policy is worth testing without a browser. |
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

Three modes, set with `data-theme` **on `<html>`**: unset (paper), `sun`,
`night`. `sun` is not a light-mode default – it is a higher-contrast, heavier-
ruled mode for reading outdoors at noon. `dir` and `lang` go on the same
element; `lang` drives the font stack.

The document element and not a wrapper div, because the browser reads it for
everything the app does not draw: the scrollbar, the overscroll gutter past the
end of a list, the rubber-band background, and the platform's own form
controls. `app/theme.ts` writes all three, plus `--theme-color` to **every**
`meta[name="theme-color"]` – there are two, media-scoped, and writing one means
the mode changes and the browser chrome does not.

Mode and locale persist in `sbr.prefs` and are applied at the top of
`main.tsx`, before `createRoot().render()`. Not from an inline `<script>`:
`vercel.json` sets `script-src 'self'` with no `unsafe-inline` and no hashes,
so one would work in dev and be blocked in production. The frame before that
line runs is covered by a `prefers-color-scheme` background in
`tokens/modes.css`, which is a guess and says so.

### Routing

Real paths, hand-rolled over the History API in `app/routes.ts` (all the
policy, no framework) and `app/useRoute.ts` (the History API, forty lines). No
router dependency: ~10 kB gzip against a 115 kB budget buys nested routes and
loaders that nothing here wants.

`/` `/scan` `/rules` `/contribute` `/settings` are the scanner's;
`/viewer` `/viewer/rules` `/viewer/queue` `/viewer/settings` are the viewer's.
The names are the surfaces – scanner and viewer, never phone and desktop – and
a URL keeps whatever word it is given.

Corrections are **always `replaceState`**. A redirect written with `pushState`
leaves the wrong URL in the history stack, and the back button lands on it and
is bounced off again.

**Every path is the app, and `web/vercel.json`'s rewrite is what makes that true
in production:**

```json
{ "source": "/:path((?!api/).*)", "destination": "/" }
```

**The destination is `/`, not `/index.html`, and that is the whole bug.** Until
2026-08-22 it rewrote to `/index.html` and every route except `/` returned **404
on both preview and production** – deep links, shared URLs and the PWA start path
all broken. `cleanUrls: true` makes `/index.html` **redirect (308)** rather than
serve, so the rewrite pointed at a path that bounces. Verified directly: `curl
/index.html` against the deployment returns 308.

*Recorded because the first two attempts fixed the wrong half.* The `source` was
rewritten twice on a theory that path-to-regexp rejects an unnamed lookahead
group. That may even be true, but it is not what broke this – with a redirecting
destination, a correctly matching rewrite 404s in exactly the same way. **Test
the destination before rewriting the source.**

Two more things not to do to that file. It is strict JSON, so **no comment
keys**: a `_comment` inside a rewrite fails Vercel's config validation and the
deployment errors *before the build starts*, which appears as a deployment with
no build log at all. And keep the `api/` exclusion – measured, a bare `/(.*)`
swallows `api/pack/[region]` and serves the SPA instead of the function.

**None of this is reproducible locally.** `vite dev` and `vite preview` serve the
SPA fallback themselves, so this routing only becomes real on a deployment.

### Filling the viewport

The shell is `.sbr-app-root`: `100dvh` with a `100vh` line above it as the
fallback, in `tokens/base.css` rather than an inline style because a style
object cannot declare a property twice. `dvh` matters because `vh` is measured
with the mobile URL bar retracted.

Safe-area insets have logical names – `--safe-block-start` and the other three,
with the inline pair swapped under `[dir="rtl"]` – because `env()` is defined
in physical terms and there is no logical form of it. The scanner takes none of
them at the shell: it is full-bleed and the camera runs under the notch, so the
controls pinned over it carry their own insets instead.

Breakpoints live in the token layer. `--desk-shell`, `--desk-split` and
`--desk-split-rev` are `grid-template` shorthands redefined at 1100px and
880px, so a component reads one custom property and a media query stays
possible inside an inline-style idiom.

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
`de.json` and `ar.json` are at 65% and fall back to English; run
`npm run check:locales` for the gap.

## Prose

En dashes (–), never em dashes (—). This holds in comments and copy alike.

The exception is Arabic, which keeps its own dash conventions – three strings in
`ar.json` use an em dash, correctly. Do not "fix" them.

## Offline, and not lying about it

`public/sw.js` is hand-written so the policy is readable in the file that
enforces it. It implements docs/01 § 6 as routing:

| Route | Strategy | Why |
|---|---|---|
| navigation | network-first, 3.5 s, then the cached shell | the app opens with no signal |
| `/assets/*`, `/icons/*` | cache-first | content-hashed, so never stale |
| `/api/pack/*` | stale-while-revalidate, in a cache that survives deploys | rules are data, not code |
| `/detect`, `/stream` | **never intercepted** | a cached recognition is a stale opinion about a scene the camera is looking at *now* |

That last row is the rule worth defending. A cached rule is a rule; a cached
answer about what is in front of somebody is the product's worst failure with a
timestamp on it.

Updates are never applied on their own – a waiting worker raises a flag and
settings offers a button. Reloading the page underneath somebody who is reading
an answer off it is worse than being one deployment behind.

### And not lying about the mock

With neither `VITE_DETECT_URL` nor `VITE_DETECT_WS` set, `createClient` returns
`MockClient`, which answers out of `data/frames.ts` – boxes measured off archive
photographs of Deggendorf. **Every other part of the path is genuine.** The
gates fire, the wire is encoded, the resolver runs, the region pack answers. So
the screen shows a live camera with markers on it and a real disposal rule under
each, and none of it has anything to do with what the lens is pointed at.

That shipped. A preview went out with no endpoint configured, and a tester
pointed a phone at their own living room and was told bin 1 was Biomüll under
the caption *Connected · Deggendorf*. It is this product's worst failure –
confidently wrong about which bin – arrived at through a configuration rather
than through a model.

So the rule is: **whatever names the transport must be where the claim is made.**
The settings row was not enough; nobody reads settings while holding a phone up
at a bin. `Scanner`'s `demo` prop takes the `live` connection state and rewrites
it, and the notice sits above *every* branch of the sheet including the answer
panel, because that is where a disposal rule is actually asserted.

Pinned in `src/features/scan/demo.test.ts` (logic and wiring) and
`e2e/demo-honesty.spec.ts` (what a person is actually told). The e2e config
empties both endpoint variables so a developer's `.env.local` cannot make the
suite pass locally for a reason CI does not share.

**The fix for a beta is to point it at a service, not to quiet the banner.**

## Performance

`perf/metrics.ts` holds a **closed vocabulary**: add a metric there or not at
all, because a typo'd name that silently creates a new series is how
instrumentation stops being trusted. Budgets are judged at p95 (`vitals.cls` and
`vitals.inp` at max, since both are already extremes).

`scripts/check-bundle.mjs` is the transfer budget and it exits non-zero. Either
growth is worth it and the budget moves in the same commit, or it is not.

**It also asserts the dev/beta split in both directions**, which is what keeps
the metrics overlay out of production without anybody having to remember:

| build | the `src/dev/` sentinel | exits |
|---|---|---|
| production – `npm run build` | must be **absent** | 1 if present |
| beta – `npm run build:beta`, or `VERCEL_ENV=preview` | must be **present** | 1 if absent |

Asserting both is the point: a check that merely *skipped* on a beta build would
let a broken beta – one where the overlay silently failed to ship – pass as a
clean production build. Neither mode can quietly become the other.

## Commands

```bash
npm --prefix web run dev            # localhost:5173
npm --prefix web run preview        # a real build; the service worker only registers here
npm --prefix web run verify         # typecheck, tests, locales, build, bundle budget
npm --prefix web run build:icons    # regenerate the app icon from its geometry
npm --prefix web run check:bundle
npm --prefix web run check:locales
```

The taxonomy validator is on the Python side and covers the locale bundles:

```bash
python ml/scripts/validate_taxonomy.py --locales en
```

## The camera path

`Scanner` renders from one of two sources and the same code draws both.

| | Where the bins come from | When |
|---|---|---|
| Fixtures | `data/frames.ts`, played out on a timer | no camera, or the director panel's `Frames from: fixtures` |
| Live | `capture/loop.ts` → `binsFromDetections` | a scanner-tier device with permission |

If a live detection ever needs different markup from a fixture, the fixtures
were lying about what the camera produces. Keep them the same type.

**`capture/loop.ts` is the piece to be careful with.** It holds the four gates
AGENTS.md calls load-bearing – motion, the 4 fps cap, the result lock, the 20 s
abort – and it takes its clock, its scheduler, its pixels and its transport as
arguments so all of it runs in `loop.test.ts` with no camera and no network.
Adding a branch there means adding a test there; the awkward sequences (the lock
closing and then the user turning around, a service shedding load mid-scan, the
phone going into a pocket) are each one line in that file.

**`transport/` never leaks upward.** Screens see `ScanState`, never a WebSocket.
The mock is not scaffolding to delete: it is what lets the whole client be run,
reviewed and tested before `service/` answers, and what the settings screen
names honestly when nothing is configured.

## What this is not

- **There is no model.** If anything here imports an inference runtime it is in
  the wrong repository. Enforced in `test/discipline.test.ts`.
- **There is no analytics *in production*.** `perf/` records to a ring buffer on
  the device and exports a JSON file when a person asks. Nothing is sent
  anywhere, because there is no user identity in this architecture and adding an
  endpoint would be the first thing in the product to transmit anything about
  anybody.

  **Amended 2026-08-22, narrowed rather than dropped.** Vercel Analytics and
  Speed Insights are mounted in `app/Telemetry.tsx` behind `__BETA__`, which
  `vite.config.ts` derives from Vercel's own `VERCEL_ENV`. They run on **preview
  deployments only** – a beta given to named testers who know they are testing.
  On a production build the branch folds, the dynamic import is unreachable, and
  neither package reaches `dist`: 124.3 kB production against 131.7 kB beta, and
  `grep vercel dist/assets/*.js` finds nothing in the former.

  **Moving them to production needs a consent gate, not a code change.** Vercel
  Analytics is cookieless but is still a transfer to a US processor, and Germany
  is the launch market – the same reasoning that keeps Google Fonts out of
  `tokens/fonts.css`. That is a product decision and the maintainer's.
- **There is no surface switch.** The surface is `routes.ts:surfaceFor` applied
  to the capability probe, and nothing else – never a viewport query, never a
  user-agent. Only `tier: "viewer"` gets the viewer; `capture` gets the scanner,
  because it means either a phone that has not been asked for permission yet or
  a laptop whose front-facing camera the scanner already has a designed state
  for. The switch survives in `dev/DevTools.tsx` alone, where it overrides the
  probe so a reviewer on a machine with the camera blocked can still see both
  surfaces. `import.meta.env.DEV` folds it out of anything shipped.
- **`de-by-muenchen-demo` is not a real region pack.** It exists in
  `data/regions.ts` so the published-coverage state can be seen, and it must
  never be moved into `data/taxonomy/regions/`.
