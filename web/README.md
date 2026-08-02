# web/ – the progressive web app

**Empty by design.** This directory is filled by Claude Design in phase 1, then
imported here via the MCP link. See [`docs/07-roadmap.md`](../docs/07-roadmap.md).

## What goes here

```
web/
├── src/
│   ├── capture/      camera, downscale, motion gate, WS client, result lock
│   ├── domain/       resolver, taxonomy types, geo – framework-free, unit-tested
│   ├── data/         region-pack client, IndexedDB cache, contribution queue
│   ├── features/     scan / result / map / registry / rules / contribute / settings
│   ├── components/   design-system components (generated)
│   ├── i18n/         <locale>.json bundles – 9 locales at launch
│   └── styles/       tokens, imported from the Claude Design system
└── api/              Vercel serverless: pack.ts, sighting.ts, escalate.ts

Inference is NOT here – it lives in service/ and is reached over a WebSocket.
```

## Before writing any code here

Read, in order:

1. [`handoff/DESIGN-FOUNDATION.md`](../handoff/DESIGN-FOUNDATION.md) – the
   creative brief the design was made from
2. the conventions file written after import – the component vocabulary and
   styling idiom actually available to you
3. [`docs/01-architecture.md`](../docs/01-architecture.md) – streaming protocol,
   client-side gating, device tiers
4. [`docs/02-waste-taxonomy.md`](../docs/02-waste-taxonomy.md) – the resolver
   contract this app must implement

## Constraints that will bite if ignored

- **`domain/` imports no framework.** The resolver is the piece most likely to
  be quietly wrong; it is tested without a browser. A Python mirror of it lives
  in `ml/src/sbr/taxonomy.py` and the two must agree – the docs are the
  specification, not either implementation.
- **Logical CSS properties only.** `margin-inline-start`, never `margin-left`.
  Arabic is a launch locale. A physical direction property anywhere is a bug.
- **No hard-coded colour, and colour is quoted rather than worn.** A real bin
  colour appears only inside a `ColorQuote` – a bounded swatch carrying its
  translated name. Never a coloured button, a tinted surface, or a status
  colour, and never a bare swatch without its name. `unknown` gets no swatch at
  all. See [`handoff/DECISIONS.md`](../handoff/DECISIONS.md) § 1.
- **No camera code path on devices without a rear camera.** Not hidden – absent.
- **The client never runs a model.** It captures, gates, sends, and draws. If a
  component imports an inference runtime, it is in the wrong repository.
- **The gates are not optional.** Motion gate, 4 fps cap, result lock, 20 s
  abort. They are what keeps the service inside its free tier; removing one is a
  cost regression, not a UX tweak.
- **Scanning may require a network; the rules browser may not.** Every
  connection state (connecting, waking, busy, offline) is designed and honest.
