import { useState } from "react";

import { Button, Card, LanguageList, ListRow, Notice, SegmentedControl, StatusStrip, Tag, TopBar } from "@/components";
import type { Capability } from "@/capture/capability";
import type { Region } from "@/data/regions";
import { REGION_ID, REGION_PLACE } from "@/data/regions";
import type { Locale, T } from "@/i18n";
import { LOCALE_META } from "@/i18n";
import { applyUpdate, promptInstall } from "@/pwa";
import { usePwa } from "@/pwa/usePwa";
import { Wordmark } from "@/features/desk/DeskShell";

/* SETTINGS.
 *
 * The design system names a settings surface and never drew one, so this is
 * authored from the two things the brief is emphatic about instead of from a
 * mockup: the app must not lie about what works without a connection, and every
 * fact that came from somewhere must say where.
 *
 * That turns settings into something slightly unusual – it is mostly a page of
 * admissions. Which camera this device has and why that decides the tier. Which
 * service is answering, including "none, and these answers are fixtures". What
 * is cached and therefore what would still work in a lift. Which locale is
 * complete and which falls back to English. None of it is chrome; all of it is
 * the honest version of a claim the rest of the interface makes quietly.
 */

export type Mode = "paper" | "sun" | "night";

interface Props {
  t: T;
  locale: Locale;
  setLocale: (locale: Locale) => void;
  mode: Mode;
  setMode: (mode: Mode) => void;
  region: Region;
  capability: Capability;
  /** Which transport answered. "mock" is said plainly rather than hidden. */
  transport: "socket" | "rest" | "mock";
  /** Phone surface only – the desk reaches settings through its own nav. */
  onClose?: () => void;
  /* THE OTHER SURFACE, REACHABLE.
   *
   * `routes.ts` already honours an explicit request for the surface a device is
   * not on – "reviewing it from a phone is legitimate", and a Surface Pro that
   * cannot be pointed at anything is the same case from the other end. What was
   * missing was any way to ask: nothing outside `features/desk/` mentioned
   * /viewer, so the only route across was typing a URL, and a tablet with two
   * cameras was locked onto the scanner.
   *
   * Exactly one of these is supplied, by the surface the panel is drawn on, and
   * they are supplied in pairs so this never becomes a one-way door.
   *
   * This is NOT an override of the capability probe. `surfaceFor` still decides
   * where a device LANDS – deciding that on width would be wrong the first time
   * somebody rotated a phone. This decides only where a person may go next. */
  onDeskView?: () => void;
  onScanner?: () => void;
}

export function Settings(p: Props) {
  const { t, locale, setLocale, mode, setMode, region, capability, transport } = p;
  const pwa = usePwa();
  const [installing, setInstalling] = useState(false);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: p.onClose ? "auto 1fr" : "1fr",
        blockSize: "100%",
        background: "var(--surface-page)",
        overflow: "hidden",
      }}
    >
      {p.onClose ? (
        <TopBar onBack={p.onClose} backLabel={t("ui.back")} title={t("settings.title")} register={REGION_ID[region.key].toUpperCase()} />
      ) : null}

      <div style={{ overflowY: "auto" }}>
        <div
          style={{
            display: "grid",
            gap: "var(--space-7)",
            padding: "var(--gutter-phone)",
            maxInlineSize: "var(--measure-read)",
            alignContent: "start",
          }}
        >
          {pwa.updateReady ? (
            <Notice
              tone="attention"
              icon="upload"
              title={t("settings.updateTitle")}
              action={
                <Button size="dense" icon="check" onClick={applyUpdate}>
                  {t("settings.updateAction")}
                </Button>
              }
            >
              {t("settings.updateBody")}
            </Notice>
          ) : null}

          {/* ---- language ---- */}
          <Group label={t("settings.language")}>
            <LanguageList
              value={locale}
              onChange={(code) => setLocale(code as Locale)}
              items={LOCALE_META.filter((l) => l.available).map((l) => ({
                code: l.code,
                endonym: l.endonym,
                dir: l.dir,
              }))}
            />
            <div style={{ display: "grid", gap: "var(--space-2)", paddingBlockStart: "var(--space-3)" }}>
              <span className="sbr-register">{t("firstRun.soon")}</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
                {LOCALE_META.filter((l) => !l.available).map((l) => (
                  <Tag key={l.code}>{l.endonym}</Tag>
                ))}
              </div>
              {locale !== "en" ? (
                <p style={{ font: "var(--type-small)", color: "var(--text-muted)" }}>{t("settings.localeGap")}</p>
              ) : null}
            </div>
          </Group>

          {/* ---- display ---- */}
          <Group label={t("settings.display")}>
            <SegmentedControl
              value={mode}
              onChange={(v) => setMode(v as Mode)}
              items={[
                { value: "paper", label: t("settings.modePaper"), icon: "layers" },
                { value: "sun", label: t("settings.modeSun"), icon: "sun" },
                { value: "night", label: t("settings.modeNight"), icon: "moon" },
              ]}
            />
            <p style={{ font: "var(--type-small)", color: "var(--text-muted)", paddingBlockStart: "var(--space-3)" }}>
              {t("settings.modeBody")}
            </p>
          </Group>

          {/* ---- this device ---- */}
          <Group label={t("settings.device")}>
            <ListRow
              title={t(`settings.tier.${capability.tier}`)}
              subtitle={capability.reason}
              register={t("settings.tierRegister")}
              trailing={<Tag variant={capability.tier === "scanner" ? "solid" : "outline"}>{capability.tier}</Tag>}
            />
            <ListRow
              title={t(`settings.transport.${transport}`)}
              subtitle={t(`settings.transportBody.${transport}`)}
              register={t("settings.serviceRegister")}
              trailing={<Tag variant={transport === "mock" ? "outline" : "solid"}>{transport}</Tag>}
            />
            {p.onDeskView ? (
              <ListRow
                title={t("settings.deskView")}
                subtitle={t("settings.deskViewBody")}
                register={t("settings.surfaceRegister")}
                onClick={p.onDeskView}
              />
            ) : null}
            {p.onScanner ? (
              <ListRow
                title={t("settings.scannerView")}
                subtitle={t("settings.scannerViewBody")}
                register={t("settings.surfaceRegister")}
                onClick={p.onScanner}
              />
            ) : null}
            {capability.permission === "denied" ? (
              <div style={{ paddingBlockStart: "var(--space-4)" }}>
                <Notice tone="attention" icon="camera-off" title={t("camera.deniedTitle")}>
                  {t("settings.cameraBlocked")}
                </Notice>
              </div>
            ) : null}
          </Group>

          {/* ---- offline ---- */}
          <Group label={t("settings.offline")}>
            <StatusStrip
              state={pwa.online ? "live" : "offline"}
              message={pwa.online ? t("conn.live") : t("conn.offline")}
            />
            <div style={{ display: "grid", paddingBlockStart: "var(--space-3)" }}>
              <Works t={t} label={t("settings.worksRules")} yes />
              <Works t={t} label={t("settings.worksPack", { place: REGION_PLACE[region.key] })} yes={region.pack !== null} />
              <Works t={t} label={t("settings.worksScan")} yes={false} />
              <Works t={t} label={t("settings.worksMap")} yes={false} />
            </div>
            <div style={{ paddingBlockStart: "var(--space-4)" }}>
              <Notice
                tone="quiet"
                icon={pwa.offlineReady ? "shield-check" : "info"}
                title={pwa.offlineReady ? t("settings.cachedTitle") : t("settings.notCachedTitle")}
              >
                {pwa.offlineReady ? t("settings.cachedBody") : t("settings.notCachedBody")}
              </Notice>
            </div>
          </Group>

          {/* ---- install ---- */}
          <Group label={t("settings.install")}>
            {pwa.installed ? (
              <Card tone="sunk" style={{ display: "grid", gap: "var(--space-2)" }}>
                <span className="sbr-register">{t("settings.installedRegister")}</span>
                <p style={{ font: "var(--type-body)", color: "var(--text-body)" }}>{t("settings.installedBody")}</p>
              </Card>
            ) : pwa.installable ? (
              <div style={{ display: "grid", gap: "var(--space-3)" }}>
                <p style={{ font: "var(--type-body)", color: "var(--text-body)" }}>{t("settings.installBody")}</p>
                <Button
                  size="outdoor"
                  block
                  icon="upload"
                  disabled={installing}
                  onClick={() => {
                    setInstalling(true);
                    void promptInstall().finally(() => setInstalling(false));
                  }}
                >
                  {t("settings.installAction")}
                </Button>
              </div>
            ) : (
              <p style={{ font: "var(--type-body)", color: "var(--text-muted)" }}>{t("settings.installManual")}</p>
            )}
          </Group>

          {/* ---- privacy ---- */}
          <Group label={t("settings.privacy")}>
            <Notice tone="quiet" icon="shield-check" title={t("firstRun.privacyTitle")}>
              {t("firstRun.privacyBody")}
            </Notice>
            <div style={{ paddingBlockStart: "var(--space-3)", display: "grid", gap: "var(--space-2)" }}>
              <p style={{ font: "var(--type-small)", color: "var(--text-muted)" }}>{t("settings.privacyFrames")}</p>
              <p style={{ font: "var(--type-small)", color: "var(--text-muted)" }}>{t("settings.privacyPlace")}</p>
            </div>
          </Group>

          {/* ---- about ---- */}
          <Group label={t("settings.about")}>
            <div style={{ display: "grid", gap: "var(--space-3)", justifyItems: "start" }}>
              <Wordmark size={28} />
              <span className="sbr-register">{t("app.tagline")}</span>
              <p style={{ font: "var(--type-small)", color: "var(--text-muted)" }}>{t("settings.aboutBody")}</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
                <Tag icon="info">{__APP_VERSION__}</Tag>
                <Tag>{__BUILD_TIME__}</Tag>
              </div>
            </div>
          </Group>
        </div>
      </div>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section style={{ display: "grid", gap: "var(--space-3)" }}>
      <h2
        style={{
          font: "var(--type-register)",
          letterSpacing: "var(--track-register)",
          textTransform: "uppercase",
          color: "var(--text-muted)",
          paddingBlockEnd: "var(--space-2)",
          borderBlockEnd: "var(--border-rule) solid var(--ink-0)",
        }}
      >
        {label}
      </h2>
      {children}
    </section>
  );
}

/* Yes and no differ in outline class before anything else, the same way rule
   verdicts do – there is no semantic green here either. */
function Works({ t, label, yes }: { t: T; label: string; yes: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-3)",
        paddingBlock: "var(--space-3)",
        borderBlockEnd: "var(--border-hair) solid var(--line-quiet)",
      }}
    >
      <span
        aria-hidden="true"
        style={
          yes
            ? {
                inlineSize: 18,
                blockSize: 18,
                flex: "none",
                borderRadius: "var(--radius-round)",
                background: "var(--ink-0)",
              }
            : {
                inlineSize: 18,
                blockSize: 18,
                flex: "none",
                borderRadius: "var(--radius-1)",
                border: "var(--border-rule) solid var(--ink-0)",
                backgroundImage: "linear-gradient(45deg, transparent 42%, var(--ink-0) 42% 58%, transparent 58%)",
              }
        }
      />
      <span style={{ font: "var(--type-body)", color: "var(--text-body)", flex: 1, minInlineSize: 0 }}>
        <span className="sbr-visually-hidden">{yes ? t("answer.yes") : t("answer.no")}: </span>
        {label}
      </span>
    </div>
  );
}
