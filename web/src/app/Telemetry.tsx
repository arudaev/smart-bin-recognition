import { lazy, Suspense } from "react";

/* VERCEL ANALYTICS AND SPEED INSIGHTS - PREVIEW ONLY, AND THAT IS THE WHOLE
   DESIGN.
 *
 * READ THIS BEFORE MOVING IT TO PRODUCTION. It contradicts two decisions this
 * repository holds on purpose, and the contradiction is resolved by scope rather
 * than by ignoring it:
 *
 *   web/CONVENTIONS.md: "There is no analytics. perf/ records to a ring buffer
 *   on the device and exports a JSON file when a person asks. Nothing is sent
 *   anywhere, because there is no user identity in this architecture and adding
 *   an endpoint would be the first thing in the product to transmit anything
 *   about anybody."
 *
 *   tokens/fonts.css refuses to hotlink Google Fonts because "a font request to
 *   a third party is a personal-data transfer the user has not consented to - a
 *   German court has already awarded damages over exactly this."
 *
 * Both still stand for the thing residents use. What changed is that a **beta**
 * exists: a preview deployment, given to a handful of named testers who know
 * they are testing, whose whole purpose is to report what breaks. Measuring that
 * is not surveillance of a public; it is instrumentation of a test.
 *
 * So the gate is `__BETA__`, derived in vite.config.ts from Vercel's own
 * `VERCEL_ENV`. On the production deployment these components are not rendered
 * AND the modules are never imported - the branch folds and the dynamic import
 * becomes unreachable, the same mechanism `src/dev/` uses.
 *
 * **If this ever moves to production it needs a consent gate**, not a code
 * change: Vercel Analytics is cookieless but still a transfer to a US processor,
 * and Germany is the launch market. That is a product decision and is the
 * maintainer's.
 *
 * What each buys, so the trade is legible:
 *   - Analytics: page views and referrers per deployment. Tells you whether a
 *     tester ever reached the scanner.
 *   - Speed Insights: real-device Core Web Vitals. Complements src/perf/, which
 *     measures the SCAN LOOP and cannot see paint or layout shift.
 */

const Analytics = __BETA__ ? lazy(() => import("@vercel/analytics/react").then((m) => ({ default: m.Analytics }))) : null;

const SpeedInsights = __BETA__
  ? lazy(() => import("@vercel/speed-insights/react").then((m) => ({ default: m.SpeedInsights })))
  : null;

/** Renders nothing at all on a production build. */
export function Telemetry() {
  if (!Analytics || !SpeedInsights) return null;
  return (
    <Suspense fallback={null}>
      <Analytics />
      <SpeedInsights />
    </Suspense>
  );
}
