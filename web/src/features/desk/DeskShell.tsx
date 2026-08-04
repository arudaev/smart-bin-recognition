import type { ReactNode } from "react";

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

export type DeskView = "map" | "rules" | "queue" | "settings";

export function DeskShell({
  t,
  region,
  view,
  setView,
  settings,
}: {
  t: T;
  region: Region;
  view: DeskView;
  setView: (v: DeskView) => void;
  /* Passed in rather than built here. Settings needs the capability probe, the
     install state and the locale setter, none of which the desk shell has any
     business knowing about – it lays out a rail and a pane. */
  settings?: ReactNode;
}) {
  const place = REGION_PLACE[region.key];
  const rows = REGISTRY[region.key] ?? [];

  const titles: Record<DeskView, string> = {
    map: t("desk.mapTitle", { place }),
    rules: t("desk.rules"),
    queue: t("desk.queue"),
    settings: t("settings.title"),
  };
  const registers: Record<DeskView, string> = {
    map: `${rows.length} · ${REGION_ID[region.key]}`,
    rules: `${REGION_ID[region.key]} · ${t("rules.offline")}`,
    queue: `${QUEUE.length} · ${REGION_ID[region.key]}`,
    settings: `${__APP_VERSION__} · ${__BUILD_TIME__}`,
  };
  const nav: [DeskView, string, string][] = [
    ["map", t("desk.map"), "map"],
    ["rules", t("desk.rules"), "list"],
    ["queue", t("desk.queue"), "layers"],
    ["settings", t("settings.title"), "settings"],
  ];

  return (
    /* One grid token instead of a column template, because the breakpoints are
       in tokens/space.css: at 1100px the rail and the panels narrow, and at
       880px the rail drops to icons. A resize listener here would re-render the
       whole surface to learn something the browser already knows. */
    <div
      style={{
        display: "grid",
        gridTemplate: "var(--desk-shell)",
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
        {/* The masthead is the first thing to go when the rail collapses: a
            wordmark broken across three lines in 76px is worse than no
            wordmark, and the document title already says the same word. */}
        <div
          className="sbr-rail-masthead"
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
              title={label}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "var(--desk-nav-justify, flex-start)",
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
              {/* Hidden, not removed, below 880px: it is the button's
                  accessible name, and a rail of bare icons is a rail nobody
                  can read. See tokens/base.css. */}
              <span className="sbr-rail-label">{label}</span>
            </button>
          ))}
        </div>

        {/* Which pack, which place, how many bins. Clipped rather than dropped
            when the rail collapses – it is the only statement of coverage on
            this surface, and a screen reader should still reach it. The class
            sits on a bare wrapper because an inline padding would survive it. */}
        <div className="sbr-rail-label">
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
        </div>
      </nav>

      <main style={{ display: "grid", gridTemplateRows: "auto 1fr", minBlockSize: 0 }}>
        <TopBar title={titles[view]} register={registers[view]} />
        <div style={{ minBlockSize: 0 }}>
          {view === "map" && <DeskMap t={t} region={region} />}
          {view === "rules" && <DeskRules t={t} region={region} />}
          {view === "queue" && <DeskQueue t={t} />}
          {view === "settings" && <div style={{ blockSize: "100%", overflow: "hidden" }}>{settings}</div>}
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
