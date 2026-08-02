import { describe, expect, it } from "vitest";

import { freshnessFrom, isStale } from "./freshness";
import { isPublishable, levelOf, resolve, UNRESOLVED } from "./resolver";
import type { Observation, RegionPack } from "./types";

/* These cases mirror ml/tests/test_taxonomy.py. If one implementation changes
   the other must change with it – they are two readings of the same
   specification, and a silent divergence is exactly the failure the split was
   meant to make visible. */

const pack: RegionPack = {
  region_id: "de-by-test",
  pack_version: "1.0.0",
  taxonomy_version: "1.0.0",
  status: "draft",
  name: "Test",
  country: "DE",
  local_names: { residual: "Restmülltonne", bio: "Biotonne", glass_mixed: "Altglas" },
  rules: [
    // Deliberately unsorted: file order is the last tie-break, not the first.
    { id: "any-wheelie", match: { form_factor: ["wheelie_small"] }, stream: "residual", confidence: 0.6 },
    {
      id: "brown-wheelie",
      match: { form_factor: ["wheelie_small"], lid_color: ["brown"] },
      stream: "bio",
      confidence: 0.95,
    },
    {
      id: "glass-bank",
      match: { form_factor: ["igloo"] },
      stream: "glass_mixed",
      confidence: 0.9,
      requires_disambiguation: true,
      disambiguation: {
        prompt_key: "disambiguation.glass_color",
        options: ["glass_clear", "glass_green", "glass_brown"],
      },
    },
  ],
};

const observe = (o: Partial<Observation> & Pick<Observation, "form_factor">): Observation => o as Observation;

describe("resolve", () => {
  it("returns unknown when there is no pack at all", () => {
    expect(resolve(null, observe({ form_factor: "wheelie_small" }))).toEqual(UNRESOLVED);
  });

  it("returns unknown when nothing matches", () => {
    expect(resolve(pack, observe({ form_factor: "sack" })).stream).toBe("unknown");
  });

  it("prefers the more specific rule over the earlier one", () => {
    const r = resolve(pack, observe({ form_factor: "wheelie_small", lid_color: "brown" }));
    expect(r.stream).toBe("bio");
    expect(r.rule_id).toBe("brown-wheelie");
  });

  it("falls back to the general rule when the specific one does not match", () => {
    const r = resolve(pack, observe({ form_factor: "wheelie_small", lid_color: "grey" }));
    expect(r.stream).toBe("residual");
  });

  it("never guesses on an unmeasured attribute", () => {
    // lid_color absent: brown-wheelie must not fire even though form_factor fits.
    const r = resolve(pack, observe({ form_factor: "wheelie_small" }));
    expect(r.rule_id).toBe("any-wheelie");
  });

  it("carries the local name from the pack when the rule has none", () => {
    expect(resolve(pack, observe({ form_factor: "wheelie_small" })).local_name).toBe("Restmülltonne");
  });
});

describe("levelOf", () => {
  it("asserts a confident match", () => {
    expect(levelOf(resolve(pack, observe({ form_factor: "wheelie_small", lid_color: "brown" })))).toBe("assert");
  });

  it("hedges a low-confidence match", () => {
    expect(levelOf(resolve(pack, observe({ form_factor: "wheelie_small" })))).toBe("hedge");
  });

  it("asks rather than hedging when the rule requires disambiguation", () => {
    // 0.9 would assert on confidence alone. The question outranks it.
    expect(levelOf(resolve(pack, observe({ form_factor: "igloo" })))).toBe("ask");
  });

  it("reports unknown for an unresolved observation", () => {
    expect(levelOf(UNRESOLVED)).toBe("unknown");
  });
});

describe("isPublishable", () => {
  it("refuses a pack with no sources", () => {
    expect(isPublishable(pack)).toBe(false);
  });

  it("refuses a source missing its retrieval date", () => {
    expect(isPublishable({ ...pack, sources: [{ name: "ZAW", url: "https://example.invalid" }] })).toBe(false);
  });

  it("accepts a pack where every source is traceable", () => {
    expect(
      isPublishable({ ...pack, sources: [{ name: "ZAW", url: "https://example.invalid", retrieved: "2026-05-12" }] }),
    ).toBe(true);
  });
});

describe("freshness", () => {
  const now = new Date("2026-08-03T12:00:00Z");

  it("is 0 when never confirmed", () => {
    expect(freshnessFrom(null, now)).toBe(0);
  });

  it("is 4 within the week", () => {
    expect(freshnessFrom("2026-08-01", now)).toBe(4);
  });

  it("is 3 within the month", () => {
    expect(freshnessFrom("2026-07-20", now)).toBe(3);
  });

  it("is 1 after three months, and reads as stale", () => {
    expect(freshnessFrom("2026-03-01", now)).toBe(1);
    expect(isStale(freshnessFrom("2026-03-01", now))).toBe(true);
  });

  it("does not call a never-confirmed fact stale – it is a different state", () => {
    expect(isStale(0)).toBe(false);
  });
});
