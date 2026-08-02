import { useState } from "react";

import { Button, Card, ChoiceTile, ColorQuote, EmptyState, Notice, Stepper, Tag, TopBar } from "@/components";
import type { ContributionReport } from "@/app/answers";
import { CONTRIBUTE_FORMS } from "@/data/registry";
import { COLORS } from "@/data/taxonomy";
import type { Region } from "@/data/regions";
import { REGION_ID } from "@/data/regions";
import type { BinColor, FormFactor } from "@/domain";
import type { T } from "@/i18n";

/* Three taps, one per screen, nothing typed. Structured all the way down, so
   nothing submitted needs translating or moderating for language – and a
   contributor who cannot write the local language can still contribute. */

export function Contribute({
  t,
  region,
  onClose,
  onSent,
}: {
  t: T;
  region: Region;
  onClose: () => void;
  onSent: (report: ContributionReport) => void;
}) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormFactor | null>(null);
  const [color, setColor] = useState<BinColor | null>(null);
  const [count, setCount] = useState(1);

  const heads = [t("contribute.shape"), t("contribute.colour"), t("contribute.else")];

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
        onBack={() => (step === 0 ? onClose() : setStep(step - 1))}
        backLabel={t("ui.back")}
        register={`${t("firstRun.step")} ${step + 1} ${t("firstRun.of")} 3 · ${t("contribute.nothingToType")}`}
        title={heads[step]}
      />

      <div
        style={{
          overflowY: "auto",
          padding: "var(--gutter-phone)",
          display: "grid",
          gap: "var(--space-3)",
          alignContent: "start",
        }}
      >
        {step === 0 &&
          CONTRIBUTE_FORMS.map((f) => (
            <ChoiceTile
              key={f.id}
              icon={f.icon}
              title={t(`form.${f.id}`)}
              selected={form === f.id}
              onSelect={() => {
                setForm(f.id);
                setStep(1);
              }}
            />
          ))}

        {step === 1 && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-2)" }}>
            {COLORS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => {
                  setColor(c);
                  setStep(2);
                }}
                aria-pressed={color === c}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-3)",
                  minBlockSize: "var(--tap-outdoor)",
                  paddingInline: "var(--space-3)",
                  background: color === c ? "var(--surface-sunk)" : "var(--surface-card)",
                  border:
                    color === c
                      ? "var(--border-rule) solid var(--ink-0)"
                      : "var(--border-hair) solid var(--line-hair)",
                  borderRadius: "var(--radius-2)",
                  cursor: "pointer",
                  textAlign: "start",
                }}
              >
                <ColorQuote color={c} label={t(`color.${c}`)} size="md" />
              </button>
            ))}
          </div>
        )}

        {step === 2 && (
          <div style={{ display: "grid", gap: "var(--space-5)" }}>
            <Card tone="sunk" style={{ display: "grid", gap: "var(--space-3)" }}>
              <span className="sbr-register">{t("contribute.soFar")}</span>
              <span style={{ font: "var(--type-body-strong)", color: "var(--text-strong)" }}>
                {form ? t(`form.${form}`) : ""}
              </span>
              <ColorQuote color={color ?? "grey"} part={t("part.body")} label={t(`color.${color ?? "grey"}`)} />
              <span className="sbr-register">{REGION_ID[region.key].toUpperCase()}</span>
            </Card>
            <Stepper
              label={t("contribute.howMany")}
              value={count}
              onChange={setCount}
              decreaseLabel={t("contribute.howMany")}
              increaseLabel={t("contribute.howMany")}
            />
            <Button variant="secondary" block icon="image">
              {t("contribute.photo")}
            </Button>
            <Notice tone="quiet" icon="shield-check" title={t("contribute.photoTitle")}>
              {t("contribute.photoBody")}
            </Notice>
          </div>
        )}
      </div>

      <div style={{ padding: "var(--gutter-phone)", borderBlockStart: "var(--border-hair) solid var(--line-hair)" }}>
        {step === 2 ? (
          <Button variant="signal" size="outdoor" block icon="send" onClick={() => onSent({ form, color, count })}>
            {t("contribute.send")}
          </Button>
        ) : (
          <Button
            size="outdoor"
            block
            variant="secondary"
            iconEnd="arrow-right"
            disabled={step === 0 ? !form : !color}
            onClick={() => setStep(step + 1)}
          >
            {t("ui.continue")}
          </Button>
        )}
      </div>
    </div>
  );
}

/* A submitted contribution claims nothing. It is visible to its submitter and
   to nobody else until a second person reports the same bin. */
export function Sent({ t, region, onClose }: { t: T; region: Region; onClose: () => void }) {
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
        onBack={onClose}
        backLabel={t("nav.backToCamera")}
        title={t("sent.title")}
        register={REGION_ID[region.key].toUpperCase()}
      />
      <div
        style={{
          overflowY: "auto",
          padding: "var(--gutter-phone)",
          display: "grid",
          gap: "var(--space-5)",
          alignContent: "start",
        }}
      >
        <EmptyState icon="clock" title={t("sent.title")} action={<Tag variant="signal">{t("sent.tag")}</Tag>}>
          {t("sent.body")}
        </EmptyState>
        <Notice tone="quiet" icon="info" title={t("sent.whyTitle")}>
          {t("sent.whyBody")}
        </Notice>
      </div>
      <div style={{ padding: "var(--gutter-phone)" }}>
        <Button size="outdoor" block icon="camera" onClick={onClose}>
          {t("nav.backToCamera")}
        </Button>
      </div>
    </div>
  );
}
