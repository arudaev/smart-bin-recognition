/* GET /api/pack/:region_id
 *
 * Serves one region pack, which is the file that decides what every answer in
 * this product means. docs/01-architecture.md puts this on Vercel rather than
 * on the inference service because it is static reference data with no camera
 * anywhere near it, and it has to keep working when the service is asleep.
 *
 * Edge runtime: no filesystem, no cold Node boot, and the pack is a static
 * import so there is nothing to read at request time anyway. It also keeps this
 * inside the free tier, which docs/05-cost-model.md treats as a constraint
 * rather than a preference.
 *
 * A region with no pack gets a 404 with a body that says so plainly. That is
 * not an error path: "no pack" is one of the three coverage states the
 * interface draws, and the client turns this response into the screen that
 * explains which rules it can still give you.
 */

import { JSON_HEADERS, PACK_CACHE_CONTROL, PACKS, etagFor, normaliseRegionId } from "../_packs";

export const config = { runtime: "edge" };

export default async function handler(request: Request): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response(JSON.stringify({ error: "method not allowed" }), {
      status: 405,
      headers: { ...JSON_HEADERS, allow: "GET, HEAD" },
    });
  }

  const url = new URL(request.url);
  const requested = normaliseRegionId(url.pathname.split("/").pop() ?? null);
  const pack = requested ? PACKS[requested] : undefined;

  if (!pack) {
    return new Response(
      JSON.stringify({
        error: "no pack",
        region_id: requested,
        // Said in the response rather than only in the interface, so anything
        // else reading this API inherits the same honesty.
        detail: "No rules have been written for this region yet.",
        available: Object.keys(PACKS),
      }),
      {
        status: 404,
        headers: { ...JSON_HEADERS, "cache-control": "public, max-age=60, stale-while-revalidate=600" },
      },
    );
  }

  const body = JSON.stringify(pack);
  const etag = await etagFor(body);

  if (request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers: { etag, "cache-control": PACK_CACHE_CONTROL } });
  }

  return new Response(request.method === "HEAD" ? null : body, {
    status: 200,
    headers: {
      ...JSON_HEADERS,
      etag,
      "cache-control": PACK_CACHE_CONTROL,
      // The client draws a different provenance line for each of these, so it
      // is worth knowing without parsing the body.
      "x-pack-status": String(pack.status),
    },
  });
}
