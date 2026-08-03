/* Loading and responsiveness, measured by the platform.
 *
 * No dependency. `web-vitals` is 2 kB of excellent library wrapped around four
 * PerformanceObserver calls, and this product's whole argument is that it does
 * not put things on a five-year-old phone that it could have left off. The
 * observers below are the same four calls with the same semantics: LCP is the
 * last candidate before the first interaction, CLS is the largest session
 * window of unexpected shifts, INP is the worst interaction latency so far.
 *
 * Everything lands in the same recorder as the scan metrics, so one report
 * covers both halves of what a user waits for: the app arriving, and the answer
 * arriving. Nothing is sent anywhere – docs/03 says there is no user identity
 * and no analytics endpoint, so these exist to be read on the device and
 * exported by hand from the metrics overlay.
 */

import { metrics as defaultMetrics } from "./metrics";
import type { Metrics } from "./metrics";

interface LayoutShift extends PerformanceEntry {
  value: number;
  hadRecentInput: boolean;
}

interface EventTiming extends PerformanceEntry {
  interactionId?: number;
  processingEnd: number;
}

let started = false;

/** Idempotent: StrictMode mounts twice in development and observers are cheap
 *  but not free, and a doubled CLS session window would be simply wrong. */
export function startVitals(sink: Metrics = defaultMetrics): () => void {
  if (started || typeof PerformanceObserver === "undefined") return () => {};
  started = true;

  const observers: PerformanceObserver[] = [];

  const observe = (type: string, callback: (entries: PerformanceEntryList) => void, extra?: PerformanceObserverInit) => {
    try {
      const observer = new PerformanceObserver((list) => callback(list.getEntries()));
      // `buffered` replays entries that happened before this ran, which is most
      // of them: the interesting paints are over before any script is executing.
      observer.observe({ type, buffered: true, ...extra });
      observers.push(observer);
    } catch {
      // An engine without this entry type. One missing series, not a failure.
    }
  };

  observe("navigation", (entries) => {
    for (const entry of entries) {
      const nav = entry as PerformanceNavigationTiming;
      if (nav.responseStart > 0) sink.sample("vitals.ttfb", nav.responseStart);
    }
  });

  observe("paint", (entries) => {
    for (const entry of entries) {
      if (entry.name === "first-contentful-paint") sink.sample("vitals.fcp", entry.startTime);
    }
  });

  /* LCP: only the final candidate counts, and candidates stop once the user
     interacts. Sampling every candidate would make the p50 a story about the
     spinner rather than about the screen. */
  let lcp = 0;
  observe("largest-contentful-paint", (entries) => {
    for (const entry of entries) lcp = Math.max(lcp, entry.startTime);
  });

  /* CLS: the largest session window, where a session is shifts less than a
     second apart and no more than five seconds long. Shifts within 500 ms of an
     input are the user's doing and do not count. */
  let clsValue = 0;
  let sessionValue = 0;
  let sessionFirst = 0;
  let sessionLast = 0;
  observe("layout-shift", (entries) => {
    for (const entry of entries as LayoutShift[]) {
      if (entry.hadRecentInput) continue;
      if (sessionValue && entry.startTime - sessionLast < 1000 && entry.startTime - sessionFirst < 5000) {
        sessionValue += entry.value;
        sessionLast = entry.startTime;
      } else {
        sessionValue = entry.value;
        sessionFirst = entry.startTime;
        sessionLast = entry.startTime;
      }
      clsValue = Math.max(clsValue, sessionValue);
    }
  });

  /* INP: the worst interaction so far, not the average. A single 800 ms tap on
     a bin marker is the whole complaint, and a mean would hide it. */
  let inp = 0;
  observe(
    "event",
    (entries) => {
      for (const entry of entries as EventTiming[]) {
        if (!entry.interactionId) continue;
        inp = Math.max(inp, entry.duration);
      }
    },
    { durationThreshold: 40 } as PerformanceObserverInit,
  );

  observe("longtask", (entries) => {
    for (const entry of entries) sink.sample("vitals.longtask", entry.duration);
  });

  /* The final values are only knowable when the page goes away, and `pagehide`
     is the last event that reliably fires on mobile Safari – `unload` does not.
     Reporting on hide as well as on hide-to-terminate means a phone that is
     backgrounded and never returned to has still recorded what it knew. */
  const flush = () => {
    if (lcp > 0) sink.sample("vitals.lcp", lcp);
    if (inp > 0) sink.sample("vitals.inp", inp);
    sink.sample("vitals.cls", clsValue);
    lcp = 0;
    inp = 0;
  };

  const onHide = () => {
    if (document.visibilityState === "hidden") flush();
  };
  document.addEventListener("visibilitychange", onHide);
  window.addEventListener("pagehide", flush);

  return () => {
    for (const observer of observers) observer.disconnect();
    document.removeEventListener("visibilitychange", onHide);
    window.removeEventListener("pagehide", flush);
    started = false;
  };
}
