import { Icon, StatusStrip, TopBar } from "@/components";
import { REGISTRY, QUEUE } from "@/data/registry";
import type { Region } from "@/data/regions";
import { REGION_ID, REGION_PLACE } from "@/data/regions";
import type { T } from "@/i18n";
import { CoverageTag } from "@/features/shared/Provenance";

import { DeskMap } from "./DeskMap";
import { DeskQueue } from "./DeskQueue";
import { DeskRules } from "./DeskRules";

/* THERE IS NO CAMERA HERE. Not disabled, not hidden behind a tooltip – absent.
   A laptop has no rear camera and pointing one at a bin is not a thing anyone
   does, so the surface offers what a laptop is actually good for instead:
   where the bins are, how recently each was confirmed, and every rule
   reachable as text.

   Note that this is decided by capability, never by viewport width. A tablet
   with a rear camera at narrow width is a scanner; a phone in landscape is
   still a scanner. See docs/01-architecture.md. */

export type DeskView = "map" | "rules" | "queue";

export function DeskShell({
  t,
  region,
  view,
  setView,
}: {
  t: T;
  region: Region;
  view: DeskView;
  setView: (v: DeskView) => void;
}) {
  const place = REGION_PLACE[region.key];
  const rows = REGISTRY[region.key] ?? [];

  const titles: Record<DeskView, string> = {
    map: t("desk.mapTitle", { place }),
    rules: t("desk.rules"),
    queue: t("desk.queue"),
  };
  const registers: Record<DeskView, string> = {
    map: `${rows.length} · ${REGION_ID[region.key]}`,
    rules: `${REGION_ID[region.key]} · ${t("rules.offline")}`,
    queue: `${QUEUE.length} · ${REGION_ID[region.key]}`,
  };
  const nav: [DeskView, string, string][] = [
    ["map", t("desk.map"), "map"],
    ["rules", t("desk.rules"), "list"],
    ["queue", t("desk.queue"), "layers"],
  ];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "var(--desk-rail) 1fr",
        blockSize: "100%",
        background: "var(--surface-page)",
        minBlockSize: 0,
      }}
    >
      <nav
        style={{
          display: "grid",
          gridTemplateRows: "auto 1fr auto",
          borderInlineEnd: "var(--border-rule) solid var(--ink-0)",
          background: "var(--surface-card)",
          minBlockSize: 0,
        }}
      >
        <div
          style={{
            padding: "var(--space-6) var(--space-5) var(--space-5)",
            borderBlockEnd: "var(--border-hair) solid var(--line-hair)",
          }}
        >
          <Wordmark size={24} />
          <div style={{ marginBlockStart: "var(--space-2)" }}>
            <span className="sbr-register">{t("desk.noCamera")}</span>
          </div>
        </div>

        <div style={{ padding: "var(--space-3)", display: "grid", gap: "var(--space-1)", alignContent: "start" }}>
          {nav.map(([k, label, icon]) => (
            <button
              key={k}
              type="button"
              onClick={() => setView(k)}
              aria-current={view === k ? "page" : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
                minBlockSize: "var(--tap-min)",
                paddingInline: "var(--space-3)",
                textAlign: "start",
                cursor: "pointer",
                borderRadius: "var(--radius-2)",
                border: 0,
                background: view === k ? "var(--ink-0)" : "transparent",
                color: view === k ? "var(--ink-inverse)" : "var(--text-body)",
                font: "var(--type-body)",
                fontWeight: (view === k ? "var(--weight-semibold)" : "var(--weight-medium)") as unknown as number,
              }}
            >
              <Icon name={icon} size={19} />
              {label}
            </button>
          ))}
        </div>

        <div
          style={{
            padding: "var(--space-4)",
            display: "grid",
            gap: "var(--space-3)",
            borderBlockStart: "var(--border-hair) solid var(--line-hair)",
            justifyItems: "start",
          }}
        >
          <CoverageTag region={region} t={t} />
          <StatusStrip state="live" message={`${place} · ${region.bins}`} style={{ inlineSize: "100%" }} />
        </div>
      </nav>

      <main style={{ display: "grid", gridTemplateRows: "auto 1fr", minBlockSize: 0 }}>
        <TopBar title={titles[view]} register={registers[view]} />
        <div style={{ minBlockSize: 0 }}>
          {view === "map" && <DeskMap t={t} region={region} />}
          {view === "rules" && <DeskRules t={t} region={region} />}
          {view === "queue" && <DeskQueue t={t} />}
        </div>
      </main>
    </div>
  );
}

/* Set in type; no drawn mark exists and none was invented. The full stop is the
   only place the owned violet appears in the wordmark. */
export function Wordmark({ size = 22 }: { size?: number }) {
  return (
    <span
      style={{
        font: `var(--weight-semibold) ${size}px/1 var(--font-sans)`,
        letterSpacing: "-0.03em",
        color: "var(--text-strong)",
        whiteSpace: "nowrap",
      }}
    >
      Which&thinsp;Bin
      <span style={{ color: "var(--signal)" }}>.</span>
    </span>
  );
}
