import deggendorf from "@taxonomy/regions/de-by-deggendorf.json";

import type { RegionPack } from "@/domain";

/* Coverage has three states, not two: published, draft, and no pack at all.
   Draft is the state every new city passes through and the interface says so.

   Deggendorf is the real pack from data/taxonomy/regions/. It is genuinely
   status: draft and genuinely not publishable – its sources carry no retrieval
   date. The screens are therefore showing a true state of the product rather
   than a mock of one.

   Munich and Plattling below are DEMONSTRATION FIXTURES and live here rather
   than in data/taxonomy/regions/ on purpose. `de-by-muenchen-demo` is not a
   transcription of AWM Munich's guidance and must never be treated as one; it
   exists so the published-coverage state can be seen. Anything that ships to a
   user has to come from a real pack with a real citation. */

export type Coverage = "published" | "draft" | "none";

export interface Region {
  key: Coverage;
  pack: RegionPack | null;
  /** Registry entries claimed for this region – count shown on first run. */
  bins: number;
  operator: string | null;
  /** How the provenance line ends: a retrieval date, or an admission. */
  checkedKey: string | null;
}

const deggendorfPack = deggendorf as unknown as RegionPack;

/* Rules mirror the Deggendorf shapes so the two regions differ in coverage
   status, not in behaviour – the point being demonstrated is the status. */
const munichDemoPack: RegionPack = {
  region_id: "de-by-muenchen-demo",
  pack_version: "0.0.0-demo",
  taxonomy_version: "1.0.0",
  status: "published",
  name: "München",
  country: "DE",
  local_names: {
    residual: "Restmüll",
    paper: "Papier",
    bio: "Biomüll",
    packaging: "Wertstofftonne",
    glass_clear: "Weißglas",
    glass_green: "Grünglas",
    glass_brown: "Braunglas",
    glass_mixed: "Altglas",
    textiles: "Altkleider",
    street_litter: "Papierkorb",
  },
  sources: [{ name: "AWM München", url: "https://www.awm-muenchen.de/", retrieved: "2026-05-12" }],
  rules: deggendorfPack.rules.map((r) => ({ ...r, id: r.id.replace(/^deg-/, "muc-") })),
};

export const REGIONS: Record<Coverage, Region> = {
  published: {
    key: "published",
    pack: munichDemoPack,
    bins: 1240,
    operator: "AWM München",
    checkedKey: "provenance.retrieved",
  },
  draft: {
    key: "draft",
    pack: deggendorfPack,
    bins: 41,
    operator: "ZAW Donau-Wald",
    checkedKey: "provenance.notChecked",
  },
  none: {
    key: "none",
    pack: null,
    bins: 0,
    operator: null,
    checkedKey: null,
  },
};

/** Place names are content, not pack data – the pack carries `name` in its own language. */
export const REGION_PLACE: Record<Coverage, string> = {
  published: "München",
  draft: "Deggendorf",
  none: "Plattling",
};

export const REGION_ID: Record<Coverage, string> = {
  published: munichDemoPack.region_id,
  draft: deggendorfPack.region_id,
  none: "de-by-plattling",
};

export function localNameFor(region: Region, stream: string): string | null {
  return region.pack?.local_names?.[stream] ?? null;
}
