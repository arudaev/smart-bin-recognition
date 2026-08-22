import type { LevelOverride } from "@/app/answers";
import type { DirectorState } from "@/app/director";
import type { Route, Surface } from "@/app/routes";
import { PATH, pathOf } from "@/app/routes";
import type { Mode } from "@/app/theme";
import type { Tier } from "@/capture/capability";
import type { Coverage } from "@/data/regions";
import type { ConnSetting } from "@/features/scan/Scanner";
import type { Locale } from "@/i18n";
import type { MockMode } from "@/transport";

import { Action, DirectorPanel, Section, Segmented, Select, Toggle } from "./DirectorPanel";
import { MetricsPanel } from "./MetricsPanel";

/* EVERYTHING DEV-ONLY, IN ONE MODULE.
 *
 * It used to live in App.tsx, which meant its labels – "densest verified
 * frame", "No pack – Plattling", every state name in the product – were
 * constructed unconditionally and travelled to every user. The panels returned
 * null in production; their strings shipped anyway.
 *
 * So the boundary is a module boundary now. App.tsx reaches this file through a
 * dynamic import that only exists on the DEV branch, and scripts/check-bundle.mjs
 * fails the build if the sentinel below is ever found in dist. That is the part
 * worth keeping: a rule nobody can quietly break beats a rule everybody means
 * to follow.
 *
 * The panels themselves are unchanged and still deliberately styled outside the
 * design system – scaffolding standing next to the building.
 */

/** Load-bearing: this is the marker scripts/check-bundle.mjs greps dist for. */
const DEV_ONLY = "sbr-dev-only-do-not-ship";

const JUMPS: { route: Route; label: string }[] = [
  { route: { surface: "scanner", screen: "first-run" }, label: "First run" },
  { route: { surface: "scanner", screen: "scan" }, label: "Scanner" },
  { route: { surface: "scanner", screen: "rules" }, label: "Rules" },
  { route: { surface: "scanner", screen: "contribute" }, label: "Contribute" },
  { route: { surface: "scanner", screen: "settings" }, label: "Settings" },
  { route: { surface: "viewer", view: "map" }, label: "Viewer – map" },
  { route: { surface: "viewer", view: "rules" }, label: "Viewer – rules" },
  { route: { surface: "viewer", view: "queue" }, label: "Viewer – queue" },
  { route: { surface: "viewer", view: "settings" }, label: "Viewer – settings" },
];

const LEVEL_LABELS: Record<LevelOverride, string> = {
  auto: "As resolved",
  assert: "Certain",
  hedge: "Most likely",
  ask: "Needs a question",
  unknown: "Unknown",
};

const CONN_LABELS: Record<ConnSetting, string> = {
  auto: "Play it out",
  live: "Connected",
  /* Not selectable in practice: the scanner derives this one from the transport
     rather than from the override, so forcing it here would claim a mock where
     there is a service. Present because ConnSetting is exhaustive. */
  demo: "Demo transport",
  connecting: "Connecting",
  waking: "Waking",
  busy: "Busy",
  offline: "Offline",
};

/* The degradation ladder, docs/05 § 3. These drive the MOCK rather than the
   fixture timeline, because a rung is a thing the transport does: the service
   answers the frame and asks the client to ease off, and the loop reacts. They
   are only reachable with `Frames from: live`. */
const LADDER_LABELS: Record<MockMode, string> = {
  live: "Coping",
  slow: "Rung 1 – 2 fps",
  shed: "Rung 2 – tap only",
  busy: "Rung 3 – stated wait",
  offline: "No connection",
};

export interface DevToolsProps {
  path: string;
  navigate: (to: string) => void;
  surface: Surface;
  /** Override the capability probe. Development only – see App.tsx. */
  setTier: (tier: Tier | null) => void;
  /** What the probe actually found, so the override says what it is hiding. */
  probedTier: Tier;
  mode: Mode;
  setMode: (mode: Mode) => void;
  locale: Locale;
  setLocale: (locale: Locale) => void;
  director: DirectorState;
  patch: (patch: Partial<DirectorState>) => void;
  onResetSession: () => void;
}

export default function DevTools(p: DevToolsProps) {
  const d = p.director;

  return (
    <div id={DEV_ONLY}>
      <DirectorPanel>
        {/* The surface switch survives here and only here. In the product the
            surface is the capability probe's answer and never a control: a
            shell that let somebody choose would teach the wrong model to
            whatever gets built from it. Reviewing both side by side is still
            worth a button, so the button lives in the scaffolding – and it
            navigates, rather than setting a flag, so it exercises the same
            router a user does. */}
        <Section label="Surface" />
        <Segmented
          label={`Capability (probe: ${p.probedTier})`}
          value={p.surface}
          options={["scanner", "viewer"] as const}
          onChange={(s) => {
            // Both halves, and in this order. Overriding the tier without
            // navigating leaves the address bar on the other surface, and
            // navigating without overriding is undone by the redirect.
            p.setTier(s === "viewer" ? "viewer" : "scanner");
            p.navigate(s === "viewer" ? PATH.viewer : PATH.scan);
          }}
        />
        <Segmented label="Mode" value={p.mode} options={["paper", "sun", "night"] as const} onChange={p.setMode} />
        <Segmented
          label="Language"
          value={p.locale as "en" | "de" | "ar"}
          options={["en", "de", "ar"] as const}
          onChange={(l) => p.setLocale(l)}
        />

        <Section label="Camera" />
        <Segmented
          label="Frames from"
          value={d.source}
          options={["fixtures", "live"] as const}
          onChange={(source) => p.patch({ source })}
        />
        <Select
          label="Bins in frame"
          value={String(d.frameCount) as "1" | "3" | "6"}
          options={[
            { value: "1", label: "1 – 92% of the archive" },
            { value: "3", label: "3 – densest verified frame" },
            { value: "6", label: "6 – unverified probe" },
          ]}
          onChange={(v) => p.patch({ frameCount: Number(v) as 1 | 3 | 6 })}
        />
        <Segmented
          label="Permission"
          value={d.camera}
          options={["granted", "denied"] as const}
          onChange={(camera) => p.patch({ camera })}
        />

        <Section label="Situation" />
        <Select
          label="Region coverage"
          value={d.coverage}
          options={[
            { value: "published", label: "Published – München" },
            { value: "draft", label: "Draft – Deggendorf" },
            { value: "none", label: "No pack – Plattling" },
          ]}
          onChange={(coverage) => p.patch({ coverage: coverage as Coverage })}
        />
        <Select
          label="Lead answer"
          value={d.level}
          options={(Object.keys(LEVEL_LABELS) as LevelOverride[]).map((k) => ({ value: k, label: LEVEL_LABELS[k] }))}
          onChange={(level) => p.patch({ level })}
        />
        <Toggle label="Lead bin is stale" value={d.forceStale} onChange={(forceStale) => p.patch({ forceStale })} />
        <Select
          label="Connection"
          value={d.conn}
          options={(Object.keys(CONN_LABELS) as ConnSetting[]).map((k) => ({ value: k, label: CONN_LABELS[k] }))}
          onChange={(conn) => p.patch({ conn })}
        />
        {/* Reachable only with live frames: a rung is something the transport
            does to the loop, and the fixture timeline has no transport. */}
        <Select
          label={d.source === "live" ? "Service load" : "Service load (needs live frames)"}
          value={d.ladder}
          options={(Object.keys(LADDER_LABELS) as MockMode[]).map((k) => ({ value: k, label: LADDER_LABELS[k] }))}
          onChange={(ladder) => p.patch({ ladder })}
        />

        <Section label="Jump to" />
        <Select
          label="Screen"
          value={p.path}
          options={JUMPS.map(({ route, label }) => ({ value: pathOf(route), label }))}
          onChange={(to) => p.navigate(to)}
        />
        <Action label="Reset what I contributed" onClick={p.onResetSession} />
      </DirectorPanel>

      <MetricsPanel />
    </div>
  );
}
