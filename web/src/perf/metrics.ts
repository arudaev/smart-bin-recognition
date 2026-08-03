/* Measurement, so that optimisation later is arithmetic rather than opinion.

   Everything the scan loop spends is recorded here: how long a frame took to
   encode, how big it was, how long the round trip took, how much of that was
   the server's own admission, how long until the user had an answer. The point
   is not a dashboard. The point is that docs/01-architecture.md § 4 states a
   latency budget as a *target*, and a target nobody measures is a wish.

   This module imports no framework and touches no DOM beyond `performance.now`,
   so it runs in a test and in a worker. It allocates nothing per sample after
   the first: each metric is a fixed ring buffer, because a scan that ran for
   twenty minutes must not grow a leak out of its own instrumentation. */

export type Unit = "ms" | "bytes" | "count" | "fps" | "score";

export interface MetricSpec {
  unit: Unit;
  /** What a good value looks like. Read by perf/budget.ts, not enforced here. */
  budget?: number;
  description: string;
}

/* The metric vocabulary is closed on purpose. A typo'd metric name that
   silently creates a new series is how instrumentation stops being trusted. */
export const METRICS = {
  "capture.grab": { unit: "ms", budget: 4, description: "Pull one frame off the video element" },
  "capture.encode": { unit: "ms", budget: 15, description: "Downscale to 448 and JPEG-encode" },
  "capture.gate": { unit: "ms", budget: 2, description: "Luma diff against the previous frame" },
  "frame.bytes": { unit: "bytes", budget: 45_000, description: "Encoded size of one frame" },
  "net.rtt": { unit: "ms", budget: 165, description: "Send to matching result" },
  "net.server": { unit: "ms", description: "Server-reported inference time" },
  "net.overhead": { unit: "ms", budget: 100, description: "Round trip minus server time" },
  "net.connect": { unit: "ms", budget: 1500, description: "Socket open, including a cold service" },
  "scan.ttfa": { unit: "ms", budget: 1500, description: "Scan start to first answer on screen" },
  "scan.ttl": { unit: "ms", budget: 6000, description: "Scan start to result lock" },
  "scan.frames": { unit: "count", budget: 20, description: "Frames actually sent in one scan" },
  "scan.bytes": { unit: "bytes", budget: 600_000, description: "Total uplink for one scan" },
  "scan.fps": { unit: "fps", budget: 4, description: "Achieved send rate" },
  "ui.render": { unit: "ms", budget: 16, description: "Detection overlay commit" },

  /* Loading, as the platform measures it rather than as we would like to. The
     budgets are the Core Web Vitals "good" thresholds, unmodified: this app is
     read on a cheap phone on mobile data, which is the population those
     thresholds were drawn from, so softening them would only flatter us. */
  "vitals.ttfb": { unit: "ms", budget: 800, description: "Time to first byte" },
  "vitals.fcp": { unit: "ms", budget: 1800, description: "First contentful paint" },
  "vitals.lcp": { unit: "ms", budget: 2500, description: "Largest contentful paint" },
  "vitals.inp": { unit: "ms", budget: 200, description: "Interaction to next paint, worst so far" },
  "vitals.cls": { unit: "score", budget: 0.1, description: "Cumulative layout shift" },
  "vitals.longtask": { unit: "ms", budget: 50, description: "Main thread blocked in one task" },
} as const satisfies Record<string, MetricSpec>;

export type MetricName = keyof typeof METRICS;

export interface Summary {
  name: MetricName;
  unit: Unit;
  count: number;
  min: number;
  p50: number;
  p95: number;
  p99: number;
  max: number;
  mean: number;
  budget?: number;
}

/** Ring capacity per metric. 512 samples at 4 fps is a bit over two minutes. */
const CAPACITY = 512;

class Series {
  private readonly buf = new Float64Array(CAPACITY);
  private n = 0;
  private total = 0;

  push(value: number): void {
    this.buf[this.n % CAPACITY] = value;
    this.n += 1;
    this.total += value;
  }

  get count(): number {
    return this.n;
  }

  get sum(): number {
    return this.total;
  }

  /** Sorted copy of the retained window. Only ever called for a summary. */
  sorted(): Float64Array {
    const held = Math.min(this.n, CAPACITY);
    return this.buf.slice(0, held).sort();
  }

  reset(): void {
    this.n = 0;
    this.total = 0;
  }
}

function quantile(sorted: Float64Array, q: number): number {
  if (sorted.length === 0) return 0;
  // Nearest-rank. With a few hundred samples the interpolated variants argue
  // about a value that the measurement noise already swamps.
  const rank = Math.ceil(q * sorted.length) - 1;
  return sorted[Math.min(Math.max(rank, 0), sorted.length - 1)];
}

export class Metrics {
  private readonly series = new Map<MetricName, Series>();
  private readonly listeners = new Set<() => void>();
  /** Coalesces notifications: the scan loop samples faster than anything reads. */
  private dirty = false;

  sample(name: MetricName, value: number): void {
    if (!Number.isFinite(value)) return;
    let s = this.series.get(name);
    if (!s) {
      s = new Series();
      this.series.set(name, s);
    }
    s.push(value);
    this.notify();
  }

  /** Time a synchronous block and record it. Returns whatever the block returns. */
  time<R>(name: MetricName, fn: () => R): R {
    const t0 = now();
    try {
      return fn();
    } finally {
      this.sample(name, now() - t0);
    }
  }

  async timeAsync<R>(name: MetricName, fn: () => Promise<R>): Promise<R> {
    const t0 = now();
    try {
      return await fn();
    } finally {
      this.sample(name, now() - t0);
    }
  }

  summary(name: MetricName): Summary | null {
    const s = this.series.get(name);
    if (!s || s.count === 0) return null;
    const sorted = s.sorted();
    const spec = METRICS[name];
    return {
      name,
      unit: spec.unit,
      count: s.count,
      min: sorted[0],
      p50: quantile(sorted, 0.5),
      p95: quantile(sorted, 0.95),
      p99: quantile(sorted, 0.99),
      max: sorted[sorted.length - 1],
      mean: s.sum / s.count,
      budget: "budget" in spec ? spec.budget : undefined,
    };
  }

  all(): Summary[] {
    const out: Summary[] = [];
    for (const name of Object.keys(METRICS) as MetricName[]) {
      const s = this.summary(name);
      if (s) out.push(s);
    }
    return out;
  }

  reset(): void {
    for (const s of this.series.values()) s.reset();
    this.series.clear();
    this.notify();
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private notify(): void {
    if (this.dirty || this.listeners.size === 0) return;
    this.dirty = true;
    queueMicrotask(() => {
      this.dirty = false;
      for (const fn of this.listeners) fn();
    });
  }
}

export function now(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

/** One recorder for the app. Tests build their own rather than sharing this. */
export const metrics = new Metrics();

/* A scan is the unit a user cares about, so its totals are accumulated
   separately and flushed once at the end rather than sampled per frame. */
export class ScanTimer {
  private readonly startedAt = now();
  private frames = 0;
  private bytes = 0;
  private firstAnswerAt: number | null = null;
  private lockedAt: number | null = null;

  constructor(private readonly sink: Metrics = metrics) {}

  frameSent(bytes: number): void {
    this.frames += 1;
    this.bytes += bytes;
    this.sink.sample("frame.bytes", bytes);
  }

  answered(): void {
    if (this.firstAnswerAt == null) this.firstAnswerAt = now();
  }

  locked(): void {
    if (this.lockedAt == null) this.lockedAt = now();
  }

  /** Called once when the scan ends, however it ends. */
  finish(): void {
    const elapsed = now() - this.startedAt;
    this.sink.sample("scan.frames", this.frames);
    this.sink.sample("scan.bytes", this.bytes);
    if (elapsed > 0 && this.frames > 0) this.sink.sample("scan.fps", (this.frames * 1000) / elapsed);
    if (this.firstAnswerAt != null) this.sink.sample("scan.ttfa", this.firstAnswerAt - this.startedAt);
    if (this.lockedAt != null) this.sink.sample("scan.ttl", this.lockedAt - this.startedAt);
  }
}

/** Human-readable, for the dev overlay and the exported report. */
export function formatValue(value: number, unit: Unit): string {
  if (unit === "bytes") {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)} MB`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)} kB`;
    return `${Math.round(value)} B`;
  }
  if (unit === "ms") return value >= 100 ? `${Math.round(value)} ms` : `${value.toFixed(1)} ms`;
  if (unit === "fps") return `${value.toFixed(2)} fps`;
  // CLS is a unitless score whose whole interesting range is below 0.25, so it
  // is the one series where rounding to an integer would erase the measurement.
  if (unit === "score") return value.toFixed(3);
  return String(Math.round(value));
}
