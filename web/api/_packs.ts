/* The packs this deployment is allowed to serve.
 *
 * A static map rather than a directory read, and that is the point rather than
 * a limitation of the runtime. AGENTS.md: "Never assert a disposal rule without
 * a region-pack entry", and "A region pack reaching status: published requires
 * every source to carry a URL and a retrieval date." A handler that globbed a
 * directory would serve whatever happened to be on disk; this one serves what
 * somebody committed, and adding a city is a reviewable diff.
 *
 * The import reaches out of web/ into data/taxonomy/ on purpose. The taxonomy
 * is the product's spine and it has exactly one copy: ml/ reads it, the client
 * reads it, and this reads it. A second copy inside web/ would drift, and the
 * drift would be silent.
 */

import deggendorf from "../../data/taxonomy/regions/de-by-deggendorf.json";

export interface ServedPack {
  region_id: string;
  status: string;
  [key: string]: unknown;
}

export const PACKS: Record<string, ServedPack> = {
  "de-by-deggendorf": deggendorf as unknown as ServedPack,
};

export function listRegions(): { region_id: string; status: string; name: string; country: string }[] {
  return Object.values(PACKS).map((pack) => ({
    region_id: pack.region_id,
    status: pack.status,
    name: String(pack.name ?? pack.region_id),
    country: String(pack.country ?? ""),
  }));
}

/* Region ids are lower-case, hyphenated and come from the taxonomy. Anything
   else is not a miss, it is somebody probing – answered the same way, but never
   used to build a path. */
export function normaliseRegionId(raw: string | null): string | null {
  if (!raw) return null;
  const id = raw.trim().toLowerCase();
  return /^[a-z]{2}(-[a-z0-9]{1,12}){1,3}$/.test(id) ? id : null;
}

/** Weak validator over the served bytes, so a repeat visit is a 304. */
export async function etagFor(body: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
  const hex = Array.from(new Uint8Array(digest).slice(0, 8))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `"${hex}"`;
}

/* Packs are data, and data that changes on a scale of weeks. Five minutes of
   freshness with a day of stale-while-revalidate means a phone in a dead spot
   serves yesterday's rules instantly rather than nothing at all, and a
   correction still reaches everybody the same afternoon. */
export const PACK_CACHE_CONTROL = "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400";

export const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  // The pack is public reference data. Any origin may read it; nothing here is
  // about a user, so there is nothing for a cross-origin read to leak.
  "access-control-allow-origin": "*",
};
