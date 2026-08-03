/* Getting a region pack, and being honest about where it came from.
 *
 * The launch region ships inside the bundle. That is not a shortcut: a scanner
 * standing in Deggendorf with no signal still has to be able to answer, and a
 * pack is a few kilobytes of JSON against a product whose whole argument is
 * that it works on a bad connection. Anything beyond the launch region is
 * fetched once and then kept.
 *
 * Every path reports its `source`, and settings shows it. "These rules came
 * from the copy in the app", "…from a copy saved three weeks ago" and "…from
 * the server just now" are three different claims about how current an answer
 * is, and the product's one unforgivable failure is being confidently wrong
 * about what goes in which bin.
 */

import deggendorf from "@taxonomy/regions/de-by-deggendorf.json";

import type { RegionPack } from "@/domain";

/** Packs compiled into the app. Available with no connection, ever. */
export const BUNDLED: Record<string, RegionPack> = {
  "de-by-deggendorf": deggendorf as unknown as RegionPack,
};

export type PackSource = "bundled" | "cache" | "network" | "none";

export interface PackResult {
  pack: RegionPack | null;
  source: PackSource;
  /** When this copy was obtained, where that is knowable. */
  fetchedAt: string | null;
  /** Set when the pack could not be had at all, for the debug overlay. */
  error?: string;
}

export interface LoadPackOptions {
  fetchImpl?: typeof fetch;
  /** The Cache Storage bucket the service worker also writes. */
  cacheName?: string;
  caches?: CacheStorage;
  signal?: AbortSignal;
}

export const PACK_CACHE = "sbr-packs-v1";

export function packUrl(regionId: string): string {
  return `/api/pack/${encodeURIComponent(regionId)}`;
}

/**
 * Load one region's rules.
 *
 * Bundled first, then the network, then whatever was kept from last time. The
 * order matters: going to the network before falling back means a correction
 * published this morning reaches somebody with a signal, and a phone in a lift
 * still gets an answer rather than a spinner.
 */
export async function loadPack(regionId: string, options: LoadPackOptions = {}): Promise<PackResult> {
  const bundled = BUNDLED[regionId];
  if (bundled) return { pack: bundled, source: "bundled", fetchedAt: null };

  const doFetch = options.fetchImpl ?? (typeof fetch === "function" ? fetch : undefined);
  const store = options.caches ?? (typeof caches !== "undefined" ? caches : undefined);
  const url = packUrl(regionId);

  if (doFetch) {
    try {
      const response = await doFetch(url, { signal: options.signal });
      if (response.status === 404) {
        // Not a failure. "No pack" is one of the three coverage states, and the
        // interface has a screen for it that says which rules it can still give.
        return { pack: null, source: "none", fetchedAt: null };
      }
      if (response.ok) {
        const pack = (await response.clone().json()) as RegionPack;
        // Written even when a service worker is also caching this: the worker
        // is absent on a first visit and on every browser that has none.
        void keep(store, url, response);
        return { pack, source: "network", fetchedAt: new Date().toISOString() };
      }
    } catch (error) {
      // Offline, or a network slow enough not to matter. Fall through.
      void error;
    }
  }

  const cached = await fromCache(store, url);
  if (cached) return cached;

  return { pack: null, source: "none", fetchedAt: null, error: "no copy of these rules is available" };
}

async function keep(store: CacheStorage | undefined, url: string, response: Response): Promise<void> {
  if (!store) return;
  try {
    const cache = await store.open(PACK_CACHE);
    await cache.put(url, response.clone());
  } catch {
    // A full or unavailable cache costs a later offline read, not this one.
  }
}

async function fromCache(store: CacheStorage | undefined, url: string): Promise<PackResult | null> {
  if (!store) return null;
  try {
    const cache = await store.open(PACK_CACHE);
    const hit = await cache.match(url);
    if (!hit) return null;
    return {
      pack: (await hit.json()) as RegionPack,
      source: "cache",
      fetchedAt: hit.headers.get("date"),
    };
  } catch {
    return null;
  }
}

/** Which regions have been kept on this device. Shown in settings. */
export async function cachedRegions(store: CacheStorage | undefined = typeof caches !== "undefined" ? caches : undefined): Promise<string[]> {
  if (!store) return Object.keys(BUNDLED);
  try {
    const cache = await store.open(PACK_CACHE);
    const keys = await cache.keys();
    const fetched = keys
      .map((request) => new URL(request.url).pathname.split("/").pop())
      .filter((id): id is string => Boolean(id))
      .map(decodeURIComponent);
    return [...new Set([...Object.keys(BUNDLED), ...fetched])].sort();
  } catch {
    return Object.keys(BUNDLED);
  }
}
