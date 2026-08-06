import { useState } from "react";

import { Button, LanguageList, Notice, StreamGlyph, Tag, TopBar } from "@/components";
import type { Region } from "@/data/regions";
import { REGION_PLACE } from "@/data/regions";
import type { Locale, T } from "@/i18n";
import { LOCALE_META } from "@/i18n";

/* Three steps, and the first one is language – because the person who most
   needs this app cannot read the label above the control that changes it. */

export function FirstRun({
  t,
  locale,
  setLocale,
  region,
  onAllow,
  onBrowse,
}: {
  t: T;
  locale: Locale;
  setLocale: (l: Locale) => void;
  region: Region;
  onAllow: () => void;
  onBrowse: () => void;
}) {
  const [step, setStep] = useState(0);
  const heads = [t("firstRun.language"), t("firstRun.what"), t("firstRun.camera")];
  const available = LOCALE_META.filter((l) => l.available);
  const soon = LOCALE_META.filter((l) => !l.available);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: "auto 1fr auto",
        blockSize: "100%",
        background: "var(--surface-page)",
        overflow: "hidden",
      }}
    >
      <TopBar
        register={`${t("firstRun.step")} ${step + 1} ${t("firstRun.of")} 3`}
        title={heads[step]}
        actions={
          <Button variant="quiet" size="dense" onClick={onAllow}>
            {t("ui.skip")}
          </Button>
        }
      />

      {step === 0 && (
        <div style={{ overflowY: "auto" }}>
          <LanguageList value={locale} onChange={(c) => setLocale(c as Locale)} items={available} />
          <div style={{ padding: "var(--gutter-phone)", display: "grid", gap: "var(--space-2)" }}>
            <span className="sbr-register">{t("firstRun.soon")}</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
              {soon.map((l) => (
                <Tag key={l.code}>{l.endonym}</Tag>
              ))}
            </div>
          </div>
        </div>
      )}

      {step === 1 && (
        <div
          style={{
            padding: "var(--space-7) var(--gutter-phone)",
            display: "grid",
            gap: "var(--space-5)",
            alignContent: "start",
          }}
        >
          <h2
            style={{
              font: "var(--type-answer)",
              fontSize: "var(--text-2xl)",
              letterSpacing: "var(--track-display)",
              color: "var(--text-strong)",
            }}
          >
            {t("firstRun.pitch")}
          </h2>
          <p style={{ font: "var(--type-body)", color: "var(--text-muted)" }}>
            {t("firstRun.coverage", { n: region.bins, place: REGION_PLACE[region.key] })}
          </p>
          <Notice tone="quiet" icon="shield-check" title={t("firstRun.privacyTitle")}>
            {t("firstRun.privacyBody")}
          </Notice>
        </div>
      )}

      {step === 2 && (
        <div
          style={{
            padding: "var(--space-7) var(--gutter-phone)",
            display: "grid",
            gap: "var(--space-5)",
            alignContent: "start",
            justifyItems: "start",
          }}
        >
          <StreamGlyph stream="paper" size="xl" tone="filled" />
          <h2 style={{ font: "var(--type-title)", color: "var(--text-strong)" }}>{t("firstRun.camTitle")}</h2>
          <p style={{ font: "var(--type-body)", color: "var(--text-muted)" }}>{t("firstRun.camBody")}</p>
        </div>
      )}

      <div
        style={{
          padding: "var(--gutter-phone)",
          paddingBlockEnd: "calc(var(--gutter-phone) + var(--safe-block-end))",
          borderBlockStart: "var(--border-hair) solid var(--line-hair)",
          display: "grid",
          gap: "var(--space-3)",
        }}
      >
        <Button
          size="outdoor"
          block
          icon={step === 2 ? "camera" : undefined}
          iconEnd={step < 2 ? "arrow-right" : undefined}
          onClick={() => (step < 2 ? setStep(step + 1) : onAllow())}
        >
          {step === 2 ? t("firstRun.allow") : t("ui.continue")}
        </Button>
        {step === 2 ? (
          <Button variant="quiet" block onClick={onBrowse}>
            {t("firstRun.notNow")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
