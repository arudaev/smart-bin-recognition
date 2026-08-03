import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { budgetReport, exportReport, judgedOn, summarise } from "@/perf/budget";
import type { BudgetLine } from "@/perf/budget";
import { METRICS, formatValue, metrics } from "@/perf/metrics";

/* THE METRICS OVERLAY.
 *
 * docs/01-architecture.md § 4 states a latency budget as a target, and a target
 * nobody looks at is a wish. This is where it is looked at: every series the
 * scan loop records, judged against its budget at p95, with the ones that are
 * over pulled to the top.
 *
 * Two things it is deliberately not. It is not a dashboard – nothing is sent
 * anywhere, because there is no analytics endpoint in this architecture and
 * adding one would be the first thing in the product to transmit anything about
 * a user. And it is not part of the design system: like the director panel it
 * is scaffolding standing next to the building, styled so it can never be
 * mistaken for the thing being built.
 *
 * The export button is the point of the whole module. Optimisation later is
 * arithmetic if there is a before, and opinion if there is not.
 */

const CSS = `
.mp{position:fixed;inset-inline-start:16px;inset-block-end:16px;z-index:2147483645;inline-size:320px;
  max-block-size:calc(100vh - 32px);display:flex;flex-direction:column;
  background:rgba(20,23,27,.9);color:#e8e6e1;
  -webkit-backdrop-filter:blur(24px);backdrop-filter:blur(24px);
  border:.5px solid rgba(255,255,255,.16);border-radius:14px;
  box-shadow:0 12px 40px rgba(0,0,0,.4);
  font:11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:hidden}
.mp-hd{display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding:9px 8px 9px 13px;border-block-end:.5px solid rgba(255,255,255,.12)}
.mp-hd b{font:600 11.5px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.04em;text-transform:uppercase}
.mp-x{appearance:none;border:0;background:transparent;color:rgba(232,230,225,.6);
  inline-size:22px;block-size:22px;border-radius:6px;cursor:pointer;font-size:13px;line-height:1}
.mp-x:hover{background:rgba(255,255,255,.1);color:#fff}
.mp-verdict{padding:7px 13px;font-size:10.5px;border-block-end:.5px solid rgba(255,255,255,.1)}
.mp-ok{color:#9fd6a8}
.mp-bad{color:#f0a8a0}
.mp-body{overflow-y:auto;min-block-size:0;scrollbar-width:thin}
.mp-row{display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:baseline;
  padding:5px 13px;border-block-end:.5px solid rgba(255,255,255,.06)}
.mp-row[data-over=true]{background:rgba(240,168,160,.12)}
.mp-name{color:rgba(232,230,225,.9);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mp-val{font-weight:600;font-variant-numeric:tabular-nums}
.mp-bud{color:rgba(232,230,225,.42);font-variant-numeric:tabular-nums}
.mp-row[data-over=true] .mp-val{color:#f0a8a0}
.mp-none{padding:14px 13px;color:rgba(232,230,225,.5);font-size:10.5px;line-height:1.5}
.mp-ft{display:flex;gap:6px;padding:9px 13px;border-block-start:.5px solid rgba(255,255,255,.12)}
.mp-btn{appearance:none;flex:1;min-block-size:24px;border:.5px solid rgba(255,255,255,.18);
  border-radius:7px;background:rgba(255,255,255,.08);color:inherit;
  font:500 10.5px/1 ui-sans-serif,system-ui,sans-serif;cursor:pointer}
.mp-btn:hover{background:rgba(255,255,255,.16)}
.mp-open{position:fixed;inset-inline-start:16px;inset-block-end:16px;z-index:2147483645;
  appearance:none;border:.5px solid rgba(255,255,255,.16);border-radius:999px;cursor:pointer;
  background:rgba(20,23,27,.9);-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px);
  box-shadow:0 8px 24px rgba(0,0,0,.35);padding:8px 14px;color:#e8e6e1;
  font:600 11px/1 ui-sans-serif,system-ui,sans-serif}
.mp-open[data-over=true]{color:#f0a8a0}
`;

/** Live view of the recorder. `metrics` coalesces its notifications already. */
function useMetricsTick(): number {
  return useSyncExternalStore(
    (fn) => metrics.subscribe(fn),
    () => tick,
    () => 0,
  );
}

let tick = 0;
metrics.subscribe(() => {
  tick += 1;
});

export function MetricsPanel() {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  useMetricsTick();

  useEffect(() => {
    const id = "sbr-metrics-css";
    if (document.getElementById(id)) return;
    const el = document.createElement("style");
    el.id = id;
    el.textContent = CSS;
    document.head.appendChild(el);
  }, []);

  const download = useCallback(() => {
    const blob = new Blob([JSON.stringify(exportReport(), null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sbr-metrics-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const copy = useCallback(() => {
    void navigator.clipboard?.writeText(JSON.stringify(exportReport(), null, 2)).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    });
  }, []);

  if (!import.meta.env.DEV) return null;

  const report = budgetReport();
  const measured = report.lines.filter((line) => line.summary !== null);

  if (!open) {
    return (
      <button type="button" className="mp-open" data-over={!report.ok} onClick={() => setOpen(true)}>
        {report.ok ? `metrics · ${measured.length}` : `metrics · ${report.over.length} over`}
      </button>
    );
  }

  // Over budget first, then everything else in the vocabulary's own order.
  const rows = [...measured].sort((a, b) => Number(b.verdict === "over") - Number(a.verdict === "over"));

  return (
    <aside className="mp" aria-label="Performance metrics">
      <div className="mp-hd">
        <b>Metrics</b>
        <button type="button" className="mp-x" onClick={() => setOpen(false)} aria-label="Close metrics">
          ✕
        </button>
      </div>

      <div className={`mp-verdict ${report.ok ? "mp-ok" : "mp-bad"}`}>{summarise(report)}</div>

      <div className="mp-body">
        {rows.length === 0 ? (
          <p className="mp-none">
            Nothing measured yet. Start a scan, or reload to capture loading vitals.
          </p>
        ) : (
          rows.map((line) => <Row key={line.name} line={line} />)
        )}
      </div>

      <div className="mp-ft">
        <button type="button" className="mp-btn" onClick={() => metrics.reset()}>
          Reset
        </button>
        <button type="button" className="mp-btn" onClick={copy}>
          {copied ? "Copied" : "Copy JSON"}
        </button>
        <button type="button" className="mp-btn" onClick={download}>
          Download
        </button>
      </div>
    </aside>
  );
}

function Row({ line }: { line: BudgetLine }) {
  const unit = METRICS[line.name].unit;
  return (
    <div className="mp-row" data-over={line.verdict === "over"} title={`${line.description} · judged on ${judgedOn(line.name)} of ${line.summary?.count ?? 0}`}>
      <span className="mp-name">{line.name}</span>
      <span className="mp-val">{line.formatted}</span>
      <span className="mp-bud">{line.budget == null ? "–" : `≤ ${formatValue(line.budget, unit)}`}</span>
    </div>
  );
}
