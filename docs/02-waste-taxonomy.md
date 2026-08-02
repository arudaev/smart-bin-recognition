# 02 – Waste Taxonomy

> The taxonomy is the product. The neural network is a lookup key.

Files:
- [`data/taxonomy/waste-streams.json`](../data/taxonomy/waste-streams.json) – canonical ontology
- [`data/taxonomy/waste-streams.schema.json`](../data/taxonomy/waste-streams.schema.json)
- [`data/taxonomy/region-pack.schema.json`](../data/taxonomy/region-pack.schema.json)
- [`data/taxonomy/regions/*.json`](../data/taxonomy/regions/) – one pack per jurisdiction

---

## 1. The three axes

The predecessor had one axis – four German words – and every problem it had
follows from that collapse. Smart Bin Recognition separates three:

| Axis | Question | Who owns it | Changes when |
|---|---|---|---|
| **Form factor** | What shape is this object? | The detector | Rarely. A 1100 L container looks the same in Munich and Málaga. |
| **Colour** | What colour is its body / lid? | Classical CV, measured per-pixel | Never – it is a measurement |
| **Waste stream** | What does that mean *here*? | The region pack | Per jurisdiction, per contractor, sometimes per street |

A resolution is a join across all three:

```
(form_factor, body_colour, lid_colour)  ×  region  ──►  stream  ──►  rules  ──►  locale
        └── from the device ──┘             └ GPS ┘      └── static data, no network ──┘
```

The vision model never learns what a colour means. That single boundary is what
lets a new country ship as a **pull request against a JSON file** rather than a
retraining run.

## 2. Canonical streams

21 streams across 6 families. Ids are permanent – once published, a stream id is
never renamed or repurposed, because region packs, the HF dataset, and users'
cached data all reference it.

| Family | Streams |
|---|---|
| `residual` | `residual`, `cigarette`, `dog_waste`, `street_litter` |
| `recyclable` | `paper`, `packaging`, `glass_clear`, `glass_green`, `glass_brown`, `glass_mixed`, `metal` |
| `organic` | `bio`, `garden` |
| `special` | `ewaste`, `batteries`, `bulky`, `hazardous`, `cooking_oil`, `medicines` |
| `reuse` | `textiles`, `deposit_return` |
| `meta` | `unknown` |

**`unknown` is a real stream, not an error.** It has a UI, a design, and a
call to action. A large share of scans in an uncovered city will land here, and
the app has to be good when it does. See
[handoff/DESIGN-FOUNDATION](../handoff/DESIGN-FOUNDATION.md).

### Why glass is split by colour

Because it is the case the predecessor explicitly flagged as its hardest, and
because in most of Europe the colour separation is the *entire point* of a glass
bank. Modelling `glass` as one stream would reproduce the original bug at a
different level. `glass_mixed` exists for jurisdictions that genuinely do not
separate.

## 3. The closed item vocabulary

`accepted`, `rejected` and `common_mistakes` hold **item ids**, never prose.
Every id must appear in the top-level `items` array, and every id in `items`
must have a translation in every shipped locale. The schema enforces the first
half; CI enforces the second.

This closure is the whole i18n cost model. ~130 item ids + ~21 stream names +
~10 form factors + UI chrome ≈ 400 strings. Nine locales at launch ≈ 3 600
strings, translated **once**, at build time, shipped as static JSON.

The alternative – translating rules at runtime with an LLM – would cost money on
every scan, in every language, forever, and would be non-deterministic about
safety-relevant advice. It is rejected on both counts. See [06-i18n](06-i18n.md).

## 4. Region packs

A region pack answers one question: *in this jurisdiction, what does this
appearance mean?* It is static JSON on the CDN, cached on device, and versioned
independently of the app.

```jsonc
{
  "region_id": "de-by-deggendorf",
  "status": "draft",
  "sources": [ /* municipal guidance, with retrieval date */ ],
  "rules": [
    { "id": "deg-paper-wheelie",
      "match": { "form_factor": ["wheelie_small","wheelie_large"], "lid_color": ["blue"] },
      "stream": "paper", "local_name": "Papiertonne", "confidence": 0.94 }
  ],
  "local_names": { "paper": "Papier" },
  "overrides": { "packaging": { "accepted_add": [], "rejected_add": [] } }
}
```

### Rule evaluation

Deterministic, pure, unit-tested, framework-free – it lives in `web/src/domain/`:

1. Filter to rules whose every `match` constraint is satisfied.
2. Sort by **specificity** (number of constraints), descending.
3. Break ties by `confidence`, then by array order.
4. If the winner has `requires_disambiguation`, do **not** assert – ask. The glass
   bank is the canonical case: green shell, three colour-coded slots.
5. If nothing matches, return `unknown` and offer stage-3 escalation.

### Rules for rules

- **Additive overrides only.** A region may add accepted/rejected items and a
  note. It may not redefine what a canonical stream means. If a region needs a
  genuinely different concept, that is a new canonical stream, reviewed centrally.
- **`local_name` is the word on the object**, shown *alongside* the translation,
  never instead of it. A user standing at a bin needs to match the German word
  they can see – and needs to know what it means. Both, always.
- **`status: published` requires provenance.** Every source needs a URL and a
  retrieval date. Nothing reaches a user as authoritative without a citation to
  the municipality's own guidance. This is the guardrail against the single worst
  failure mode in this product: confidently telling someone the wrong thing.
- **Confidence is honest.** A `0.55` rule renders differently from a `0.94` one.
  The UI degrades from assertion → hedge → question as confidence drops.

### Adding a city

1. Copy `regions/de-by-deggendorf.json`, set `region_id`, `bbox`, `geohash_tiles`.
2. Find the municipality's waste guide. Fill `sources` with URL + retrieval date.
3. Write `rules` mapping local colours/forms to canonical streams.
4. Fill `local_names` for streams that exist there.
5. `python ml/scripts/validate_taxonomy.py` – schema, referential integrity,
   locale coverage.
6. PR. Review checks provenance, not just JSON validity.
7. Flip `status` to `published`.

No retraining. No model change. No deploy of the app itself.

## 5. Known gaps

- **Aperture-level colour** (v2). Glass banks with per-slot coding are stuck at
  `requires_disambiguation` until the detector can box individual apertures.
- **Text hints** (v2). `match.text_hint` is reserved for OCR tokens. It will
  always be optional – the app must work for someone who cannot read the local
  script, which is precisely the user it exists for.
- **Sub-municipal variation.** Some cities differ by district or contractor. The
  geohash tiling supports it; no pack uses it yet.
- **Deggendorf pack is `draft`.** Its rules were transcribed from the
  predecessor's four hard-coded classes plus general German practice. They are a
  starting point and are **not** verified against ZAW Donau-Wald's published
  guidance. That verification is the first task before any launch.
