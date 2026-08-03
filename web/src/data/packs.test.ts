import { describe, expect, it, vi } from "vitest";

import { BUNDLED, PACK_CACHE, cachedRegions, loadPack, packUrl } from "./packs";

/* Every path has to report where the rules came from, because "these are from
   the copy in the app", "…from a copy saved three weeks ago" and "…from the
   server just now" are three different claims about how current an answer is,
   and being confidently wrong about which bin is this product's worst failure. */

/** Enough of Cache Storage to exercise the fallback, and no more. */
function fakeCaches() {
  const entries = new Map<string, Response>();
  const cache = {
    async put(key: RequestInfo | URL, value: Response) {
      entries.set(String(key), value);
    },
    async match(key: RequestInfo | URL) {
      return entries.get(String(key));
    },
    async keys() {
      return [...entries.keys()].map((url) => new Request(`https://example.test${url}`));
    },
  };
  return { store: { open: async () => cache } as unknown as CacheStorage, entries };
}

const packBody = (regionId: string) =>
  JSON.stringify({ region_id: regionId, status: "published", name: regionId, country: "DE", rules: [] });

describe("loadPack", () => {
  it("answers the launch region with no network at all", async () => {
    const fetchImpl = vi.fn();
    const result = await loadPack("de-by-deggendorf", { fetchImpl: fetchImpl as unknown as typeof fetch });

    expect(result.source).toBe("bundled");
    expect(result.pack?.region_id).toBe("de-by-deggendorf");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("ships the launch region as a genuine draft, not a demonstration", async () => {
    // data/taxonomy/regions/de-by-deggendorf.json is status: draft and its
    // sources carry no retrieval date. The screens show a true state of the
    // product rather than a mock of one.
    expect(BUNDLED["de-by-deggendorf"].status).toBe("draft");
  });

  it("fetches a region it does not carry, and says so", async () => {
    const { store, entries } = fakeCaches();
    const fetchImpl = vi.fn(async () => new Response(packBody("de-by-muenchen"), { status: 200 }));

    const result = await loadPack("de-by-muenchen", {
      fetchImpl: fetchImpl as unknown as typeof fetch,
      caches: store,
    });

    expect(result.source).toBe("network");
    expect(result.pack?.region_id).toBe("de-by-muenchen");
    expect(fetchImpl).toHaveBeenCalledWith(packUrl("de-by-muenchen"), { signal: undefined });
    // Kept for the next time there is no signal, whether or not a service
    // worker exists on this browser.
    expect(entries.has(packUrl("de-by-muenchen"))).toBe(true);
  });

  it("falls back to the kept copy when the network is gone", async () => {
    const { store } = fakeCaches();
    await loadPack("de-by-muenchen", {
      fetchImpl: (async () => new Response(packBody("de-by-muenchen"), { status: 200 })) as unknown as typeof fetch,
      caches: store,
    });

    const offline = await loadPack("de-by-muenchen", {
      fetchImpl: (async () => {
        throw new TypeError("Failed to fetch");
      }) as unknown as typeof fetch,
      caches: store,
    });

    expect(offline.source).toBe("cache");
    expect(offline.pack?.region_id).toBe("de-by-muenchen");
  });

  it("treats a 404 as the no-pack coverage state, not as a failure", async () => {
    const result = await loadPack("de-by-plattling", {
      fetchImpl: (async () => new Response("{}", { status: 404 })) as unknown as typeof fetch,
      caches: fakeCaches().store,
    });

    expect(result.source).toBe("none");
    expect(result.pack).toBeNull();
    expect(result.error).toBeUndefined();
  });

  it("does not cache a 404, so a city becoming covered is picked up", async () => {
    const { store, entries } = fakeCaches();
    await loadPack("de-by-plattling", {
      fetchImpl: (async () => new Response("{}", { status: 404 })) as unknown as typeof fetch,
      caches: store,
    });
    expect(entries.size).toBe(0);
  });

  it("reports having nothing rather than inventing rules", async () => {
    const result = await loadPack("fr-75-paris", {
      fetchImpl: (async () => {
        throw new TypeError("Failed to fetch");
      }) as unknown as typeof fetch,
      caches: fakeCaches().store,
    });

    expect(result.pack).toBeNull();
    expect(result.source).toBe("none");
    expect(result.error).toBeTruthy();
  });

  it("survives a browser with no Cache Storage", async () => {
    const result = await loadPack("de-by-muenchen", {
      fetchImpl: (async () => new Response(packBody("de-by-muenchen"), { status: 200 })) as unknown as typeof fetch,
      caches: undefined,
    });
    expect(result.source).toBe("network");
  });
});

describe("cachedRegions", () => {
  it("lists the bundled region even before anything has been fetched", async () => {
    expect(await cachedRegions(fakeCaches().store)).toEqual(["de-by-deggendorf"]);
  });

  it("adds regions kept from earlier visits", async () => {
    const { store } = fakeCaches();
    await loadPack("de-by-muenchen", {
      fetchImpl: (async () => new Response(packBody("de-by-muenchen"), { status: 200 })) as unknown as typeof fetch,
      caches: store,
    });
    expect(await cachedRegions(store)).toEqual(["de-by-deggendorf", "de-by-muenchen"]);
  });
});

describe("the cache bucket", () => {
  it("is the one the service worker writes, so they share a copy", () => {
    // sw.js keeps this bucket across deployments on purpose: packs are data,
    // not code, and evicting them on every release would drop the offline copy
    // of the rules every time a button moved.
    expect(PACK_CACHE).toBe("sbr-packs-v1");
  });
});
