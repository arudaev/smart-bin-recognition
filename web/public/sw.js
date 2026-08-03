/* The service worker.
 *
 * docs/01-architecture.md § 6 states plainly what works without a connection
 * and what does not, and says the app must not lie about it. This file is where
 * that paragraph becomes behaviour, so the split is enforced by routing rather
 * than by hope:
 *
 *   works offline    the shell, the rules browser, every locale bundle, and the
 *                    region pack for a place already visited
 *   does not         recognising a bin, the map, registry reads outside the cache
 *
 * The last line is the important one. A cached answer about which bin something
 * goes in is a rule, and rules change slowly. A cached *recognition* would be a
 * stale opinion about a scene the camera is looking at right now, which is the
 * one thing this product must never serve. So /detect is never cached, never
 * retried from cache, and never given a fallback that looks like an answer.
 *
 * Hand-written rather than generated. Workbox would add a build step and a
 * megabyte of runtime to express four routes, and the rules above are the kind
 * of thing that should be readable in the file that enforces them.
 */

/* Bumped by the build: BUILD is replaced with the precache manifest's hash, so
   a new deployment gets a new cache and the old one is dropped on activate. */
const BUILD = "dev";
const SHELL = `sbr-shell-${BUILD}`;
const ASSETS = `sbr-assets-${BUILD}`;
const PACKS = "sbr-packs-v1";

/** Region packs outlive a deployment: they are data, not code. */
const KEEP = new Set([SHELL, ASSETS, PACKS]);

/** How long to wait for the network on a navigation before serving the shell. */
const NAV_TIMEOUT_MS = 3500;

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL);
      // The build emits the exact list, so a first offline launch has every
      // hashed asset rather than only the ones a previous visit happened to hit.
      let list = ["/", "/index.html", "/manifest.webmanifest"];
      try {
        const response = await fetch("/precache.json", { cache: "no-cache" });
        if (response.ok) list = await response.json();
      } catch {
        // No manifest in dev. The shell entries above are still worth having.
      }
      await Promise.all(
        list.map((url) =>
          cache.add(new Request(url, { cache: "reload" })).catch(() => {
            // One 404 in the list must not fail the whole install and leave the
            // user with no worker at all.
          }),
        ),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      if (self.registration.navigationPreload) {
        await self.registration.navigationPreload.enable();
      }
      const names = await caches.keys();
      await Promise.all(names.filter((n) => n.startsWith("sbr-") && !KEEP.has(n)).map((n) => caches.delete(n)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  // The page asks for the update, from a button the user pressed. A worker that
  // swaps itself out mid-scan would replace the interface while somebody is
  // reading an answer off it.
  if (event.data === "skip-waiting") void self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;

  // Recognition is never cached and never faked. Let it fail honestly; the
  // interface has a designed state for a service that cannot be reached.
  if (isInference(url)) return;

  if (request.mode === "navigate") {
    event.respondWith(navigation(event));
    return;
  }

  if (!sameOrigin) {
    // Third-party requests are left entirely alone. Caching a font from another
    // origin would persist a transfer this product has already decided it must
    // stop making: see tokens/fonts.css.
    return;
  }

  if (isPack(url)) {
    event.respondWith(staleWhileRevalidate(request, PACKS));
    return;
  }

  if (isImmutable(url)) {
    event.respondWith(cacheFirst(request, ASSETS));
    return;
  }

  event.respondWith(staleWhileRevalidate(request, ASSETS));
});

function isInference(url) {
  return url.pathname === "/detect" || url.pathname.startsWith("/api/detect") || url.pathname.endsWith("/stream");
}

function isPack(url) {
  return url.pathname.startsWith("/api/pack/");
}

/** Vite content-hashes everything under /assets, so it can never go stale. */
function isImmutable(url) {
  return url.pathname.startsWith("/assets/") || url.pathname.startsWith("/icons/");
}

async function navigation(event) {
  const cache = await caches.open(SHELL);
  try {
    const preloaded = await event.preloadResponse;
    if (preloaded) {
      void cache.put("/index.html", preloaded.clone());
      return preloaded;
    }
    const response = await withTimeout(fetch(event.request), NAV_TIMEOUT_MS);
    void cache.put("/index.html", response.clone());
    return response;
  } catch {
    // Offline, or a network slow enough to be indistinguishable from it. The
    // shell boots and the rules browser works; the scanner says why it cannot.
    const cached = (await cache.match("/index.html")) ?? (await cache.match("/"));
    if (cached) return cached;
    return new Response("Offline, and this page has not been visited before.", {
      status: 503,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) void cache.put(request, response.clone());
  return response;
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  const network = fetch(request)
    .then((response) => {
      if (response.ok) void cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);

  if (hit) {
    // Refresh in the background; the user reads the cached copy now.
    void network;
    return hit;
  }
  const response = await network;
  if (response) return response;
  return new Response("", { status: 504, statusText: "Offline and not cached" });
}

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("network timeout")), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}
