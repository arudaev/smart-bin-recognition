import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ContributionReport, SessionState } from "@/app/answers";
import { EMPTY_SESSION } from "@/app/answers";
import type { DirectorState } from "@/app/director";
import { PRODUCTION_DIRECTOR } from "@/app/director";
import { readPreferences, writePreferences } from "@/app/preferences";
import { PATH, normalisePath, resolveRoute } from "@/app/routes";
import type { Mode } from "@/app/theme";
import { applyThemeToDocument } from "@/app/theme";
import { Telemetry } from "@/app/Telemetry";
import { useRouter } from "@/app/useRoute";
import type { Tier } from "@/capture/capability";
import { useScan } from "@/capture/useScan";
import { FRAMES } from "@/data/frames";
import { REGIONS } from "@/data/regions";
import { Contribute, Sent } from "@/features/contribute/Contribute";
import { DeskShell } from "@/features/desk/DeskShell";
import { FirstRun } from "@/features/firstrun/FirstRun";
import { PhoneRules } from "@/features/rules/PhoneRules";
import { Scanner } from "@/features/scan/Scanner";
import { Settings } from "@/features/settings/Settings";
import type { Locale } from "@/i18n";
import { translator } from "@/i18n";
import { MockClient, createClient } from "@/transport";

/* THE SHELL.
 *
 * It used to be a prototype viewer: a 390x812 bordered box with a drop shadow
 * and a scanner/viewer switch in a header. Installed to a home screen, the app
 * drew a picture of a phone inside itself.
 *
 * What it does now is the four things a shell owes the screens under it.
 *
 *   1. A URL for every state. app/routes.ts holds the whole map and the whole
 *      redirect policy; app/useRoute.ts is the forty lines of History API that
 *      make it real. Hand-rolled on purpose: a router library is ~10 kB gzip
 *      against a 115 kB budget, for nested routes and loaders nothing here
 *      wants.
 *
 *   2. The theme on <html>, not on a div. See app/theme.ts for why the browser
 *      chrome, the scrollbar and the overscroll gutter depend on it.
 *
 *   3. The viewport, filled. Exactly 100dvh via .sbr-app-root, and no padding
 *      on the scanner: the camera is a full-bleed surface, and the controls
 *      floating over it hold themselves out of the safe-area bands instead.
 *
 *   4. The surface, from the capability probe and from nothing else – never a
 *      viewport query, never a user-agent. routes.ts:surfaceFor says which of
 *      the three tiers gets which of the two surfaces, and why.
 *
 * What it deliberately does not do is draw anything. There is no chrome here:
 * no header, no wordmark, no switch. Every pixel belongs to a screen.
 */

/* This branch is the only place the module is named, so a build that fails the
   condition folds it away and the import becomes unreachable. What must not come
   back is a static import: the panels return null in production, but their
   props – every state label in the product – were built either way, and ~3 kB of
   director copy shipped to every user. scripts/check-bundle.mjs greps dist for
   the sentinel in that file.

   `__BETA__` widens the branch from "development" to "development or a Vercel
   PREVIEW build", because a beta tester needs the metrics overlay for exactly
   the reason a developer does: a latency budget nobody looks at is a wish, and
   the maintainer cannot stand behind the tester's shoulder.

   It does NOT widen to production. `__BETA__` is derived in vite.config.ts from
   `VERCEL_ENV`, which Vercel sets itself - there is no flag to forget - and
   check-bundle.mjs asserts the sentinel is PRESENT in a beta build and ABSENT in
   a production one, so both directions fail loudly rather than one silently. */
const DevTools = import.meta.env.DEV || __BETA__ ? lazy(() => import("@/dev/DevTools")) : null;

export default function App() {
  const { path, navigate } = useRouter();

  /* Read once, synchronously, before the first render. main.tsx has already
     applied the same values to <html>; this is the copy React renders from. */
  const stored = useRef(readPreferences()).current;
  const [mode, setMode] = useState<Mode>(stored.mode);
  const [locale, setLocale] = useState<Locale>(stored.locale);
  const [onboarded, setOnboarded] = useState(stored.onboarded);

  const [director, setDirector] = useState<DirectorState>(PRODUCTION_DIRECTOR);
  const patch = useCallback((next: Partial<DirectorState>) => setDirector((d) => ({ ...d, ...next })), []);

  /* The one override of the probe, and it exists only in development.
     Every state in this product is reachable by ordinary use except one: the
     surface a device does not have. A laptop with the camera blocked can never
     see the scanner, and a reviewer who cannot reach a surface cannot judge it.
     `import.meta.env.DEV` folds to false in a build, so what ships reads the
     probe and nothing else – see routes.ts:surfaceFor. */
  const [devTier, setDevTier] = useState<Tier | null>(null);

  const [session, setSession] = useState<SessionState>(EMPTY_SESSION);
  const [contribBin, setContribBin] = useState<number | null>(null);
  const [sent, setSent] = useState(false);

  /* The camera runs on one path and nowhere else, and it is keyed off the path
     rather than off the resolved route to keep this out of a cycle: the route
     needs the tier, the tier comes from the probe, and the probe lives here.
     Anywhere but /scan the camera is closed and the indicator light is out. */
  /* The ladder's rungs are things a loaded SERVICE does, so reaching them means
     standing one in. `live` is the only value production ever holds, so this is
     undefined in every build and the configured transport is used - MockClient
     is already in the bundle as createClient's fallback, so naming it here
     costs nothing beyond this line. */
  const ladder = useMemo(
    () => (director.ladder === "live" ? undefined : new MockClient({ mode: director.ladder })),
    [director.ladder],
  );

  const live = useScan({
    enabled: director.source === "live" && normalisePath(path) === PATH.scan,
    locale,
    debug: import.meta.env.DEV,
    client: ladder,
  });

  const transport = useMemo(() => createClient(live.tier).kind, [live.tier]);

  /* Nothing is placed until the probe has answered. It is one enumerateDevices
     call and resolves in a microtask, and holding one frame is much better than
     the alternative: `capability` starts at VIEWER, so guessing would put every
     phone on the viewer surface and then snatch it away. */
  const tier = import.meta.env.DEV && devTier ? devTier : live.tier;
  const placement = live.probed ? resolveRoute(path, { tier, onboarded }) : null;
  const redirect = placement?.redirect ?? null;

  useEffect(() => {
    // replaceState, never push. A redirect in the history stack is a URL the
    // back button lands on and is immediately bounced off again.
    if (redirect) navigate(redirect, { replace: true });
  }, [redirect, navigate]);

  useEffect(() => {
    applyThemeToDocument(mode, locale);
  }, [mode, locale]);

  useEffect(() => {
    writePreferences({ mode, locale, onboarded });
  }, [mode, locale, onboarded]);

  /* Session state is keyed by the bin's number in the current frame, and that
     number means nothing across a different frame or a different city – bin 1
     in Deggendorf is not bin 1 in Plattling. Carrying "you told us" across
     either would attribute an answer to a bin the user has never seen. */
  useEffect(() => {
    setSession(EMPTY_SESSION);
    setContribBin(null);
  }, [director.coverage, director.frameCount, director.source]);

  const t = translator(locale);
  const region = REGIONS[director.coverage];
  const frame = FRAMES[director.frameCount] ?? FRAMES[3];

  const settingsPanel = (onClose?: () => void) => (
    <Settings
      t={t}
      locale={locale}
      setLocale={setLocale}
      mode={mode}
      setMode={setMode}
      region={region}
      capability={live.capability}
      transport={transport}
      onClose={onClose}
    />
  );

  const devTools =
    DevTools && placement ? (
      <Suspense fallback={null}>
        <DevTools
          path={normalisePath(path)}
          navigate={navigate}
          surface={placement.route.surface}
          setTier={setDevTier}
          probedTier={live.tier}
          mode={mode}
          setMode={setMode}
          locale={locale}
          setLocale={setLocale}
          director={director}
          patch={patch}
          onResetSession={() => setSession(EMPTY_SESSION)}
        />
      </Suspense>
    ) : null;

  /* One themed frame while the probe answers. The background is already on
     <html>, so this is a held breath rather than a white flash. */
  if (!placement) return <div className="sbr-app-root" />;

  const { route } = placement;

  if (route.surface === "viewer") {
    return (
      <div
        className="sbr-app-root"
        style={{
          background: "var(--surface-page)",
          paddingBlockStart: "var(--safe-block-start)",
          paddingBlockEnd: "var(--safe-block-end)",
          paddingInlineStart: "var(--safe-inline-start)",
          paddingInlineEnd: "var(--safe-inline-end)",
        }}
      >
        <DeskShell
          t={t}
          region={region}
          view={route.view}
          setView={(view) => navigate(view === "map" ? PATH.viewer : `${PATH.viewer}/${view}`)}
          settings={settingsPanel()}
        />
        {devTools}
        <Telemetry />
      </div>
    );
  }

  /* The scanner gets no padding. It is a full-bleed surface and the camera runs
     under the notch; the controls pinned over it carry the safe-area insets
     themselves, which is the only way to have both. */
  const screens: Record<typeof route.screen, JSX.Element> = {
    "first-run": (
      <FirstRun
        t={t}
        locale={locale}
        setLocale={setLocale}
        region={region}
        onAllow={() => {
          setOnboarded(true);
          patch({ camera: "granted" });
          if (director.source === "live") live.requestCamera();
          navigate(PATH.scan);
        }}
        onBrowse={() => {
          setOnboarded(true);
          navigate(PATH.rules);
        }}
      />
    ),
    scan: (
      <Scanner
        t={t}
        region={region}
        frame={frame}
        conn={director.conn}
        camera={director.camera}
        session={session}
        answerOptions={{ level: director.level, forceStale: director.forceStale }}
        live={director.source === "live" ? live : null}
        onBrowse={() => navigate(PATH.rules)}
        onSettings={() => navigate(PATH.settings)}
        onContribute={(n) => {
          setContribBin(n);
          setSent(false);
          navigate(PATH.contribute);
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
        onAllowCamera={() => patch({ camera: "granted" })}
        onSunlight={() => setMode(mode === "sun" ? "paper" : "sun")}
      />
    ),
    rules: <PhoneRules t={t} region={region} onClose={() => navigate(PATH.scan)} />,
    /* `sent` is a state of this screen and not a route of its own. A URL
       somebody can arrive at cold must not tell them they just sent something,
       and back from here leads wherever /contribute was reached from. */
    contribute: sent ? (
      <Sent
        t={t}
        region={region}
        onClose={() => {
          setSent(false);
          navigate(PATH.scan);
        }}
      />
    ) : (
      <Contribute
        t={t}
        region={region}
        onClose={() => navigate(PATH.scan)}
        onSent={(report: ContributionReport) => {
          if (contribBin != null) {
            setSession((s) => ({ ...s, pending: { ...s.pending, [contribBin]: report } }));
          }
          setSent(true);
        }}
      />
    ),
    settings: settingsPanel(() => navigate(PATH.scan)),
  };

  return (
    <div className="sbr-app-root" style={{ background: "var(--surface-page)" }}>
      {screens[route.screen]}
      {devTools}
      <Telemetry />
    </div>
  );
}
