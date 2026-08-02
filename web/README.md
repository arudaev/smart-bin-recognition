# web/ – the client

React + TypeScript + Vite. The design was made in Claude Design and imported
here; see [`CONVENTIONS.md`](CONVENTIONS.md) for the component vocabulary and
the styling idiom, and [`../handoff/`](../handoff/) for why the design is the
way it is.

```bash
npm install
npm run dev          # http://localhost:5173
npm run build
npm test             # resolver + freshness, no browser needed
npm run typecheck
npm run check:locales
```

The lead camera frame is not committed – see
[`public/photos/README.md`](public/photos/README.md). The app runs without it.

## Layout

```
src/
├── domain/       resolver, types, freshness – framework-free, unit-tested
├── data/         taxonomy loader, region packs, camera frames, registry
├── app/          session model: what the user has answered, confirmed, reported
├── components/   the 26 design-system components
├── features/     screens – scan, answer, rules, contribute, firstrun, desk
├── i18n/         en / de / ar bundles and t()
├── styles/       the design system's token layer
└── dev/          the state director (development only)
```

Inference is **not** here. It lives in `service/` and is reached over a
WebSocket.

## What is real and what is staged

| Real | Staged |
|---|---|
| The resolver, mirroring `ml/src/sbr/taxonomy.py` | The camera – frames come from `data/frames.ts` |
| The Deggendorf region pack, read from `data/taxonomy/regions/` | The Munich pack, a demo fixture for the published state |
| The taxonomy: 22 streams, 10 form factors, 136 items | The map tiles and the registry entries |
| The English locale bundle, validated against the taxonomy | German and Arabic, about 60% complete |

## Constraints that will bite if ignored

- **`domain/` imports no framework.** The resolver is the piece most likely to
  be quietly wrong; it is tested without a browser. A Python mirror lives in
  `ml/src/sbr/taxonomy.py` and the two must agree – the docs are the
  specification, not either implementation.
- **Logical CSS properties only.** `margin-inline-start`, never `margin-left`.
  Arabic is a launch locale. The single documented exception is
  `DetectionMarker`, which overlays a photograph and a photograph does not
  mirror.
- **No hard-coded colour, and colour is quoted rather than worn.** A real bin
  colour appears only inside a `ColorQuote`. Never a coloured button, a tinted
  surface, or a status colour. `unknown` gets no swatch at all.
- **No camera code path on devices without a rear camera.** Not hidden – absent.
  Decided by capability probe, never by viewport width.
- **The client never runs a model.** It captures, gates, sends, and draws.
- **The gates are not optional.** Motion gate, 4 fps cap, result lock, 20 s
  abort. They are what keeps the service inside its free tier; removing one is a
  cost regression, not a UX tweak.
- **Scanning may require a network; the rules browser may not.** Every
  connection state is designed and honest.
