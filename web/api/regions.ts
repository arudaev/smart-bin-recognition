/* GET /api/regions
 *
 * Which places this deployment has rules for, and what state each is in. Small
 * enough to be cheap to ask for and useful enough that the desk surface can say
 * "nothing mapped here" without guessing.
 *
 * The status field is the whole point of the list. Coverage has three states,
 * not two – published, draft, and no pack at all – and draft is the state every
 * new city passes through on its way to being trustworthy. A client that only
 * knew "have a pack / do not" would present a transcription nobody has checked
 * with the same confidence as an operator's own published guidance.
 */

import { JSON_HEADERS, listRegions } from "./_packs";

export const config = { runtime: "edge" };

export default function handler(request: Request): Response {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response(JSON.stringify({ error: "method not allowed" }), {
      status: 405,
      headers: { ...JSON_HEADERS, allow: "GET, HEAD" },
    });
  }

  const regions = listRegions();
  return new Response(request.method === "HEAD" ? null : JSON.stringify({ regions }), {
    status: 200,
    headers: {
      ...JSON_HEADERS,
      "cache-control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400",
    },
  });
}
