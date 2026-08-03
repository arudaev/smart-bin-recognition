import { describe, expect, it } from "vitest";

import { budgetReport, exportReport, judgedOn, summarise } from "./budget";
import { METRICS, Metrics, ScanTimer, formatValue } from "./metrics";
import type { MetricName } from "./metrics";

/* "A target nobody measures is a wish." The recorder has to be cheap enough to
   leave on during a scan and honest enough that the number it reports is the
   one the budget is about, which is p95 and not the mean. */

describe("Metrics", () => {
  it("summarises a series at the quantiles the budget is judged on", () => {
    const m = new Metrics();
    for (let i = 1; i <= 100; i += 1) m.sample("net.rtt", i);

    const s = m.summary("net.rtt")!;
    expect(s.count).toBe(100);
    expect(s.min).toBe(1);
    expect(s.max).toBe(100);
    expect(s.p50).toBe(50);
    expect(s.p95).toBe(95);
    expect(s.p99).toBe(99);
    expect(s.mean).toBeCloseTo(50.5);
  });

  it("returns nothing for a series that has never been sampled", () => {
    expect(new Metrics().summary("net.rtt")).toBeNull();
  });

  it("ignores a value that is not a number, rather than poisoning the mean", () => {
    const m = new Metrics();
    m.sample("net.rtt", Number.NaN);
    m.sample("net.rtt", Number.POSITIVE_INFINITY);
    expect(m.summary("net.rtt")).toBeNull();
  });

  it("does not grow without bound during a long scan", () => {
    // A scan that ran for twenty minutes must not leak out of its own
    // instrumentation. The ring keeps a window; the count keeps the truth.
    const m = new Metrics();
    for (let i = 0; i < 5000; i += 1) m.sample("net.rtt", i);
    const s = m.summary("net.rtt")!;
    expect(s.count).toBe(5000);
    expect(s.max).toBeLessThan(5000);
    expect(s.max).toBeGreaterThan(4000);
  });

  it("times a block and records what it cost", () => {
    const m = new Metrics();
    const out = m.time("capture.encode", () => 42);
    expect(out).toBe(42);
    expect(m.summary("capture.encode")?.count).toBe(1);
  });

  it("records a block that threw, because a slow failure is still slow", () => {
    const m = new Metrics();
    expect(() => m.time("capture.encode", () => {
      throw new Error("boom");
    })).toThrow("boom");
    expect(m.summary("capture.encode")?.count).toBe(1);
  });

  it("coalesces notifications, since the loop samples faster than anything reads", async () => {
    const m = new Metrics();
    let calls = 0;
    m.subscribe(() => {
      calls += 1;
    });
    for (let i = 0; i < 50; i += 1) m.sample("net.rtt", i);
    await Promise.resolve();
    await Promise.resolve();
    expect(calls).toBe(1);
  });
});

describe("ScanTimer", () => {
  it("reports one row per scan rather than one per frame", () => {
    const m = new Metrics();
    const timer = new ScanTimer(m);
    timer.frameSent(30_000);
    timer.frameSent(28_000);
    timer.answered();
    timer.locked();
    timer.finish();

    expect(m.summary("scan.frames")?.max).toBe(2);
    expect(m.summary("scan.bytes")?.max).toBe(58_000);
    expect(m.summary("frame.bytes")?.count).toBe(2);
    expect(m.summary("scan.ttfa")).not.toBeNull();
    expect(m.summary("scan.ttl")).not.toBeNull();
  });

  it("records nothing about an answer that never arrived", () => {
    const m = new Metrics();
    const timer = new ScanTimer(m);
    timer.frameSent(30_000);
    timer.finish();
    expect(m.summary("scan.ttfa")).toBeNull();
    expect(m.summary("scan.ttl")).toBeNull();
  });
});

describe("the metric vocabulary", () => {
  it("is closed, so a typo cannot quietly create a new series", () => {
    const names = Object.keys(METRICS) as MetricName[];
    expect(new Set(names).size).toBe(names.length);
    for (const name of names) {
      expect(METRICS[name].description.length).toBeGreaterThan(0);
    }
  });

  it("keeps the round-trip budget the architecture states", () => {
    // docs/01-architecture.md § 4: ~165 ms round trip, ~4 fps.
    expect(METRICS["net.rtt"].budget).toBe(165);
    expect(METRICS["scan.fps"].budget).toBe(4);
  });
});

describe("budgetReport", () => {
  it("passes a series inside its budget and fails one outside", () => {
    const m = new Metrics();
    for (let i = 0; i < 20; i += 1) m.sample("net.rtt", 100);
    expect(budgetReport(m).ok).toBe(true);

    for (let i = 0; i < 20; i += 1) m.sample("capture.encode", 400);
    const report = budgetReport(m);
    expect(report.ok).toBe(false);
    expect(report.over.map((l) => l.name)).toContain("capture.encode");
  });

  it("judges on p95, not the mean", () => {
    // A mean round trip inside budget with a long tail is a product that feels
    // broken for one scan in twenty, and one in twenty is every user, weekly.
    const m = new Metrics();
    for (let i = 0; i < 94; i += 1) m.sample("net.rtt", 50);
    for (let i = 0; i < 6; i += 1) m.sample("net.rtt", 1000);

    const summary = m.summary("net.rtt")!;
    expect(summary.mean).toBeLessThan(165); // a mean that looks fine
    expect(summary.p95).toBeGreaterThan(165); // a tail that is not
    expect(budgetReport(m).ok).toBe(false);
  });

  it("judges the already-extreme vitals on their maximum", () => {
    // CLS is a session maximum and INP the worst interaction, both by
    // construction. A percentile of them would read lower than the thing itself.
    expect(judgedOn("vitals.cls")).toBe("max");
    expect(judgedOn("vitals.inp")).toBe("max");
    expect(judgedOn("net.rtt")).toBe("p95");
  });

  it("does not fail a budget nothing has measured yet", () => {
    const report = budgetReport(new Metrics());
    expect(report.ok).toBe(true);
    expect(report.unmeasured.length).toBeGreaterThan(0);
  });

  it("says what went over, in one line", () => {
    const m = new Metrics();
    m.sample("capture.encode", 900);
    expect(summarise(budgetReport(m))).toMatch(/capture\.encode/);
    expect(summarise(budgetReport(new Metrics()))).toMatch(/within budget/i);
  });
});

describe("exportReport", () => {
  it("emits only series that were measured, with their verdicts", () => {
    const m = new Metrics();
    m.sample("net.rtt", 120);
    const report = exportReport(m);
    expect(report.version).toBe(1);
    expect(report.metrics.map((row) => row.name)).toEqual(["net.rtt"]);
    expect(report.metrics[0]).toMatchObject({ verdict: "pass", budget: 165, judgedOn: "p95" });
  });

  it("carries no identity, because there is none to carry", () => {
    const report = exportReport(new Metrics());
    expect(Object.keys(report.context).sort()).toEqual([
      "connection",
      "deviceMemoryGb",
      "devicePixelRatio",
      "hardwareConcurrency",
      "standalone",
      "userAgent",
      "viewport",
    ]);
  });
});

describe("formatValue", () => {
  it("reads as the unit a person thinks in", () => {
    expect(formatValue(30_000, "bytes")).toBe("30.0 kB");
    expect(formatValue(1_500_000, "bytes")).toBe("1.50 MB");
    expect(formatValue(400, "bytes")).toBe("400 B");
    expect(formatValue(12.34, "ms")).toBe("12.3 ms");
    expect(formatValue(412.7, "ms")).toBe("413 ms");
    expect(formatValue(3.9, "fps")).toBe("3.90 fps");
    expect(formatValue(12, "count")).toBe("12");
  });

  it("keeps CLS readable, since its whole range is below a quarter", () => {
    expect(formatValue(0.083, "score")).toBe("0.083");
  });
});
