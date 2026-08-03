/* Turning measurements into a verdict.
 *
 * docs/01-architecture.md § 4 states a latency budget and AGENTS.md makes
 * missing it a build failure rather than a warning – "Never ship a model that
 * misses its latency budget… The build fails; it does not warn." That rule is
 * about the service, but the client half of the round trip is measured on the
 * device and nowhere else, so this is where the client's side of the same
 * budget is checked.
 *
 * The verdict is taken at p95, not at the mean. A mean round trip of 160 ms
 * with a long tail is a product that feels broken for one scan in twenty, and
 * one scan in twenty is every user, weekly. The mean is reported because it is
 * useful for reasoning about cost; it is not what passes or fails.
 */

import { METRICS, formatValue, metrics as defaultMetrics } from "./metrics";
import type { MetricName, Metrics, Summary } from "./metrics";

export type Verdict = "pass" | "over" | "unmeasured";

export interface BudgetLine {
  name: MetricName;
  description: string;
  verdict: Verdict;
  /** The value the verdict was taken on: p95 for everything with a budget. */
  observed: number | null;
  budget: number | null;
  /** observed / budget. Above 1 is over. Null when either side is missing. */
  ratio: number | null;
  summary: Summary | null;
  formatted: string;
}

export interface BudgetReport {
  lines: BudgetLine[];
  over: BudgetLine[];
  /** False when anything with a budget was measured and exceeded it. */
  ok: boolean;
  /** Budgeted metrics with no samples. Not a failure – nothing ran yet. */
  unmeasured: MetricName[];
  takenAt: string;
}

/**
 * Which statistic a budget is judged on.
 *
 * Nearly everything is p95. Two exceptions, both because the metric is already
 * an extreme: CLS is a session maximum by construction, and INP is the worst
 * interaction by construction, so taking a p95 of them would be a percentile of
 * a percentile and would read lower than the thing it is measuring.
 */
export function judgedOn(name: MetricName): keyof Pick<Summary, "p95" | "max"> {
  return name === "vitals.cls" || name === "vitals.inp" ? "max" : "p95";
}

export function budgetReport(sink: Metrics = defaultMetrics): BudgetReport {
  const lines: BudgetLine[] = [];
  const unmeasured: MetricName[] = [];

  for (const name of Object.keys(METRICS) as MetricName[]) {
    const spec = METRICS[name];
    // Widened on purpose: METRICS is `as const`, so without this the type is
    // the union of the literal budgets and every comparison to another number
    // reads to the compiler as unreachable.
    const budget: number | null = "budget" in spec ? (spec.budget ?? null) : null;
    const summary = sink.summary(name);

    if (!summary) {
      if (budget != null) unmeasured.push(name);
      lines.push({
        name,
        description: spec.description,
        verdict: "unmeasured",
        observed: null,
        budget,
        ratio: null,
        summary: null,
        formatted: "–",
      });
      continue;
    }

    const observed = summary[judgedOn(name)];
    const verdict: Verdict = budget == null ? "pass" : observed > budget ? "over" : "pass";

    lines.push({
      name,
      description: spec.description,
      verdict,
      observed,
      budget,
      ratio: budget == null || budget === 0 ? null : observed / budget,
      summary,
      formatted: formatValue(observed, spec.unit),
    });
  }

  const over = lines.filter((line) => line.verdict === "over");
  return {
    lines,
    over,
    ok: over.length === 0,
    unmeasured,
    takenAt: new Date().toISOString(),
  };
}

export interface ReportEnvelope {
  version: 1;
  takenAt: string;
  ok: boolean;
  /* Recorded so a number is interpretable six months later: a 400 ms round trip
     means one thing on a laptop over fibre and another on the phone this
     product exists for. None of it identifies anybody – there is no user
     identity to attach it to, and none is invented here. */
  context: {
    userAgent: string | null;
    hardwareConcurrency: number | null;
    deviceMemoryGb: number | null;
    connection: string | null;
    devicePixelRatio: number | null;
    viewport: { width: number; height: number } | null;
    standalone: boolean | null;
  };
  metrics: {
    name: MetricName;
    unit: string;
    description: string;
    budget: number | null;
    judgedOn: string;
    observed: number | null;
    verdict: Verdict;
    count: number;
    min: number;
    p50: number;
    p95: number;
    p99: number;
    max: number;
    mean: number;
  }[];
}

/**
 * The whole recorder as one JSON document, for later optimisation.
 *
 * Deliberately a file a person exports rather than a beacon a page sends. There
 * is no analytics endpoint in this architecture and adding one would be the
 * first thing in the product to send anything about a user anywhere.
 */
export function exportReport(sink: Metrics = defaultMetrics): ReportEnvelope {
  const report = budgetReport(sink);
  return {
    version: 1,
    takenAt: report.takenAt,
    ok: report.ok,
    context: deviceContext(),
    metrics: report.lines
      .filter((line) => line.summary !== null)
      .map((line) => ({
        name: line.name,
        unit: METRICS[line.name].unit,
        description: line.description,
        budget: line.budget,
        judgedOn: judgedOn(line.name),
        observed: line.observed,
        verdict: line.verdict,
        count: line.summary!.count,
        min: round(line.summary!.min),
        p50: round(line.summary!.p50),
        p95: round(line.summary!.p95),
        p99: round(line.summary!.p99),
        max: round(line.summary!.max),
        mean: round(line.summary!.mean),
      })),
  };
}

function round(value: number): number {
  return Math.round(value * 1000) / 1000;
}

interface NetworkInformation {
  effectiveType?: string;
}

function deviceContext(): ReportEnvelope["context"] {
  if (typeof navigator === "undefined") {
    return {
      userAgent: null,
      hardwareConcurrency: null,
      deviceMemoryGb: null,
      connection: null,
      devicePixelRatio: null,
      viewport: null,
      standalone: null,
    };
  }
  const nav = navigator as Navigator & {
    deviceMemory?: number;
    connection?: NetworkInformation;
  };
  return {
    userAgent: nav.userAgent ?? null,
    hardwareConcurrency: nav.hardwareConcurrency ?? null,
    deviceMemoryGb: nav.deviceMemory ?? null,
    connection: nav.connection?.effectiveType ?? null,
    devicePixelRatio: typeof window === "undefined" ? null : window.devicePixelRatio,
    viewport: typeof window === "undefined" ? null : { width: window.innerWidth, height: window.innerHeight },
    standalone: typeof window === "undefined" ? null : window.matchMedia?.("(display-mode: standalone)").matches,
  };
}

/** A one-line summary for a log or a commit message. */
export function summarise(report: BudgetReport): string {
  if (report.over.length === 0) {
    const measured = report.lines.filter((l) => l.summary).length;
    return `${measured} metrics within budget`;
  }
  return report.over.map((l) => `${l.name} ${l.formatted} > ${formatValue(l.budget!, METRICS[l.name].unit)}`).join("; ");
}
