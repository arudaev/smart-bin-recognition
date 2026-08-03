import { useEffect, useMemo, useRef, useState } from "react";

import { IconButton, SegmentedControl } from "@/components";
import type { ContributionReport, LevelOverride, SessionState } from "@/app/answers";
import { EMPTY_SESSION } from "@/app/answers";
import { useScan } from "@/capture/useScan";
import { FRAMES } from "@/data/frames";
import type { Coverage } from "@/data/regions";
import { REGIONS } from "@/data/regions";
import { Action, DirectorPanel, Section, Segmented, Select, Toggle } from "@/dev/DirectorPanel";
import { MetricsPanel } from "@/dev/MetricsPanel";
import { Contribute, Sent } from "@/features/contribute/Contribute";
import type { DeskView } from "@/features/desk/DeskShell";
import { DeskShell, Wordmark } from "@/features/desk/DeskShell";
import { FirstRun } from "@/features/firstrun/FirstRun";
import { PhoneRules } from "@/features/rules/PhoneRules";
import type { ConnSetting } from "@/features/scan/Scanner";
import { Scanner } from "@/features/scan/Scanner";
import { Settings } from "@/features/settings/Settings";
import type { Locale } from "@/i18n";
import { dirFor, translator } from "@/i18n";
import { createClient } from "@/transport";

/* The shell.

   Two jobs, and they used to be one. It decides which surface the device gets –
   and that decision is now the real capability probe from docs/01-architecture
   § 5, not a switch someone flipped – and it holds the session state that spans
   screens. The switch in the header survives because reviewing both surfaces
   side by side is the whole reason this shell exists, but it starts wherever
   the probe puts it.

   The distinction it is careful about: the surfaces are scanner and viewer, a
   statement about what the device can do. They are never phone and desktop, and
   the choice is never a viewport query. A tablet with a rear camera at narrow
   width is a scanner; a phone in landscape is still a scanner. */

type Surface = "scanner" | "viewer";
type Mode = "paper" | "sun" | "night";
type PhoneScreen = "first-run" | "scan" | "rules" | "contribute" | "sent" | "settings";
type CameraSetting = "granted" | "denied";
type Source = "fixtures" | "live";

const SCREEN_LABELS: Record<PhoneScreen, string> = {
  "first-run": "First run",
  scan: "Scanner",
  rules: "Rules",
  contribute: "Contribute",
  sent: "Sent",
  settings: "Settings",
};

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
  connecting: "Connecting",
  waking: "Waking",
  busy: "Busy",
  offline: "Offline",
};

/** The manifest declares a shortcut straight to the rules; honour it. */
function initialScreen(): PhoneScreen {
  if (typeof window === "undefined") return "first-run";
  const requested = new URLSearchParams(window.location.search).get("screen");
  return requested && requested in SCREEN_LABELS ? (requested as PhoneScreen) : "first-run";
}

export default function App() {
  const [surface, setSurface] = useState<Surface>("scanner");
  const [mode, setMode] = useState<Mode>("paper");
  const [locale, setLocale] = useState<Locale>("en");
  const [coverage, setCoverage] = useState<Coverage>("draft");
  const [frameCount, setFrameCount] = useState<1 | 3 | 6>(3);
  const [level, setLevel] = useState<LevelOverride>("auto");
  const [forceStale, setForceStale] = useState(false);
  const [conn, setConn] = useState<ConnSetting>("auto");
  const [camera, setCamera] = useState<CameraSetting>("granted");
  const [screen, setScreen] = useState<PhoneScreen>(initialScreen);
  const [deskView, setDeskView] = useState<DeskView>("map");
  const [source, setSource] = useState<Source>("fixtures");

  const [session, setSession] = useState<SessionState>(EMPTY_SESSION);
  const [contribBin, setContribBin] = useState<number | null>(null);

  /* The camera only runs on the screen that shows it. Anywhere else – reading
     the rules, filling in a contribution, sitting on settings – it is closed,
     and the indicator light goes out with it. */
  const live = useScan({
    enabled: source === "live" && surface === "scanner" && screen === "scan",
    locale,
    debug: import.meta.env.DEV,
  });

  const transport = useMemo(() => createClient(live.tier).kind, [live.tier]);

  /* Follow the probe, once, unless somebody has already chosen. A device with
     no rear camera opens on the viewer instead of on a scanner it cannot use. */
  const chosen = useRef(false);
  useEffect(() => {
    if (chosen.current) return;
    if (live.capability.reason === "No camera API on this origin") return; // still probing
    chosen.current = true;
    setSurface(live.tier === "viewer" ? "viewer" : "scanner");
  }, [live.capability, live.tier]);

  /* Session state is keyed by the bin's number in the current frame, and that
     number means nothing across a different frame or a different city – bin 1
     in Deggendorf is not bin 1 in Plattling. Carrying "you told us" across
     either would attribute an answer to a bin the user has never seen. */
  useEffect(() => {
    setSession(EMPTY_SESSION);
    setContribBin(null);
  }, [coverage, frameCount, source]);

  const t = translator(locale);
  const region = REGIONS[coverage];
  const frame = FRAMES[frameCount] ?? FRAMES[3];
  const dir = dirFor(locale);
  const theme = mode === "paper" ? undefined : mode;

  const settingsPanel = (
    <Settings
      t={t}
      locale={locale}
      setLocale={setLocale}
      mode={mode}
      setMode={setMode}
      region={region}
      capability={live.capability}
      transport={transport}
      onClose={surface === "scanner" ? () => setScreen("scan") : undefined}
    />
  );

  const phone: Record<PhoneScreen, JSX.Element> = {
    "first-run": (
      <FirstRun
        t={t}
        locale={locale}
        setLocale={setLocale}
        region={region}
        onAllow={() => {
          setCamera("granted");
          if (source === "live") live.requestCamera();
          setScreen("scan");
        }}
        onBrowse={() => setScreen("rules")}
      />
    ),
    scan: (
      <Scanner
        t={t}
        region={region}
        frame={frame}
        conn={conn}
        camera={camera}
        session={session}
        answerOptions={{ level, forceStale }}
        live={source === "live" ? live : null}
        onBrowse={() => setScreen("rules")}
        onContribute={(n) => {
          setContribBin(n);
          setScreen("contribute");
        }}
        onConfirm={(n) => setSession((s) => ({ ...s, confirmed: { ...s.confirmed, [n]: true } }))}
        onAnswer={(n, stream) =>
          setSession((s) => {
            const answered = { ...s.answered };
            if (stream) answered[n] = stream;
            else delete answered[n];
            return { ...s, answered };
          })
        }
        onAllowCamera={() => setCamera("granted")}
        onSunlight={() => setMode((m) => (m === "sun" ? "paper" : "sun"))}
      />
    ),
    rules: <PhoneRules t={t} region={region} onClose={() => setScreen("scan")} />,
    contribute: (
      <Contribute
        t={t}
        region={region}
        onClose={() => setScreen("scan")}
        onSent={(report: ContributionReport) => {
          if (contribBin != null) {
            setSession((s) => ({ ...s, pending: { ...s.pending, [contribBin]: report } }));
          }
          setScreen("sent");
        }}
      />
    ),
    sent: <Sent t={t} region={region} onClose={() => setScreen("scan")} />,
    settings: settingsPanel,
  };

  return (
    <div
      style={{
        minBlockSize: "100vh",
        background: "var(--paper-2)",
        display: "grid",
        gridTemplateRows: "auto 1fr",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-5)",
          flexWrap: "wrap",
          padding: "var(--space-5) var(--space-7)",
          borderBlockEnd: "var(--border-hair) solid var(--paper-4)",
          background: "var(--paper-1)",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-4)" }}>
          <Wordmark size={22} />
          <span className="sbr-register">{t("app.tagline")}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <SegmentedControl
            size="dense"
            value={surface}
            onChange={setSurface}
            items={[
              { value: "scanner", label: t("ui.phone"), icon: "camera" },
              { value: "viewer", label: t("ui.desk"), icon: "map" },
            ]}
          />
          <IconButton
            name="settings"
            label={t("settings.title")}
            variant="secondary"
            size="dense"
            onClick={() => {
              if (surface === "scanner") setScreen("settings");
              else setDeskView("settings");
            }}
          />
        </div>
      </header>

      <div
        style={{
          display: "grid",
          placeItems: "start center",
          padding: "var(--space-8) var(--space-6)",
          overflow: "auto",
        }}
      >
        {surface === "scanner" ? (
          <div
            data-theme={theme}
            dir={dir}
            lang={locale}
            style={{
              inlineSize: 390,
              blockSize: 812,
              borderRadius: 22,
              border: "6px solid var(--ink-0)",
              overflow: "hidden",
              background: "var(--surface-page)",
              boxShadow: "0 30px 70px -40px rgba(22,24,28,.55)",
            }}
          >
            {phone[screen]}
          </div>
        ) : (
          <div
            data-theme={theme}
            dir={dir}
            lang={locale}
            style={{
              inlineSize: "min(1280px, 100%)",
              blockSize: 800,
              border: "6px solid var(--ink-0)",
              borderRadius: 10,
              overflow: "hidden",
              background: "var(--surface-page)",
              boxShadow: "0 30px 70px -40px rgba(22,24,28,.55)",
            }}
          >
            <DeskShell t={t} region={region} view={deskView} setView={setDeskView} settings={settingsPanel} />
          </div>
        )}
      </div>

      <DirectorPanel>
        <Section label="Surface" />
        <Segmented label="Capability" value={surface} options={["scanner", "viewer"] as const} onChange={setSurface} />
        <Segmented label="Mode" value={mode} options={["paper", "sun", "night"] as const} onChange={setMode} />
        <Segmented
          label="Language"
          value={locale as "en" | "de" | "ar"}
          options={["en", "de", "ar"] as const}
          onChange={(l) => setLocale(l)}
        />

        <Section label="Camera" />
        <Segmented
          label="Frames from"
          value={source}
          options={["fixtures", "live"] as const}
          onChange={(v) => setSource(v)}
        />
        <Select
          label="Bins in frame"
          value={String(frameCount) as "1" | "3" | "6"}
          options={[
            { value: "1", label: "1 – 92% of the archive" },
            { value: "3", label: "3 – densest verified frame" },
            { value: "6", label: "6 – unverified probe" },
          ]}
          onChange={(v) => setFrameCount(Number(v) as 1 | 3 | 6)}
        />
        <Segmented label="Permission" value={camera} options={["granted", "denied"] as const} onChange={setCamera} />

        <Section label="Situation" />
        <Select
          label="Region coverage"
          value={coverage}
          options={[
            { value: "published", label: "Published – München" },
            { value: "draft", label: "Draft – Deggendorf" },
            { value: "none", label: "No pack – Plattling" },
          ]}
          onChange={setCoverage}
        />
        <Select
          label="Lead answer"
          value={level}
          options={(Object.keys(LEVEL_LABELS) as LevelOverride[]).map((k) => ({ value: k, label: LEVEL_LABELS[k] }))}
          onChange={setLevel}
        />
        <Toggle label="Lead bin is stale" value={forceStale} onChange={setForceStale} />
        <Select
          label="Connection"
          value={conn}
          options={(Object.keys(CONN_LABELS) as ConnSetting[]).map((k) => ({ value: k, label: CONN_LABELS[k] }))}
          onChange={setConn}
        />

        <Section label="Jump to" />
        <Select
          label="Phone screen"
          value={screen}
          options={(Object.keys(SCREEN_LABELS) as PhoneScreen[]).map((k) => ({ value: k, label: SCREEN_LABELS[k] }))}
          onChange={(v) => {
            setSurface("scanner");
            setScreen(v);
          }}
        />
        <Select
          label="Desk view"
          value={deskView}
          options={[
            { value: "map", label: "Map" },
            { value: "rules", label: "Rules browser" },
            { value: "queue", label: "Review queue" },
            { value: "settings", label: "Settings" },
          ]}
          onChange={(v) => {
            setSurface("viewer");
            setDeskView(v);
          }}
        />
        <Action label="Reset what I contributed" onClick={() => setSession(EMPTY_SESSION)} />
      </DirectorPanel>

      <MetricsPanel />
    </div>
  );
}
