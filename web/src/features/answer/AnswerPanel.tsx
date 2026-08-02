import { Button, ColorQuote, Notice, ResultCard, StreamGlyph, Tag } from "@/components";
import type { BinAnswer } from "@/app/answers";
import { cardLevel } from "@/app/answers";
import type { FrameBin } from "@/data/frames";
import type { Region } from "@/data/regions";
import { REGION_PLACE } from "@/data/regions";
import { streamById } from "@/data/taxonomy";
import type { T } from "@/i18n";
import { Provenance, Quoted } from "@/features/shared/Provenance";
import { RulesList } from "@/features/shared/Rules";

/* The answer panel. One bin, opened. This is the only place a physical colour
   appears – quoting is for confirmation, not for browsing. */

interface Props {
  bin: FrameBin;
  answer: BinAnswer;
  region: Region;
  t: T;
  onContribute: () => void;
  onConfirm: (n: number) => void;
  onAnswer: (stream: string | null) => void;
}

export function AnswerPanel({ bin, answer, region, t, onContribute, onConfirm, onAnswer }: Props) {
  if (answer.kind === "pending") return <PendingPanel bin={bin} answer={answer} t={t} />;
  if (answer.stream === "unknown")
    return <UnknownPanel bin={bin} region={region} t={t} onContribute={onContribute} />;

  const colors = bin.quoted.map((c) => ({
    color: c.color,
    label: t(`color.${c.color}`),
    part: t(`part.${c.part}`),
  }));

  const eyebrow =
    answer.kind === "hedge"
      ? t("hedge.mostLikely")
      : answer.kind === "ask"
        ? t("ask.title")
        : answer.kind === "answered"
          ? t("ask.answered")
          : null;

  return (
    <div style={{ display: "grid", gap: "var(--space-5)", alignContent: "start" }}>
      <ResultCard
        stream={answer.stream}
        index={bin.n}
        translated={t(`stream.${answer.stream}`)}
        local={answer.localName}
        localLang="de"
        onBinLabel={t("answer.onBin")}
        level={cardLevel(answer.kind)}
        register={eyebrow}
        colors={colors}
        freshness={answer.freshness}
        freshnessNote={freshnessNote(answer, t)}
        footer={
          answer.kind === "answered" ? (
            <Button variant="quiet" size="dense" icon="arrow-left" onClick={() => onAnswer(null)}>
              {t("ask.change")}
            </Button>
          ) : (
            <Button variant="quiet" size="dense" icon="flag" onClick={onContribute}>
              {t("answer.wrong")}
            </Button>
          )
        }
      >
        {answer.kind === "ask" ? (
          <AskChoices answer={answer} t={t} onAnswer={onAnswer} />
        ) : (
          <RulesList stream={answer.stream} t={t} />
        )}
      </ResultCard>

      {answer.kind === "hedge" ? (
        <Notice tone="attention" icon="circle-question-mark" title={t("hedge.title")}>
          {t("hedge.body")}
        </Notice>
      ) : null}

      {answer.stale ? (
        <Notice
          tone="attention"
          icon="clock"
          title={t("stale.title")}
          action={
            <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
              <Button size="dense" variant="secondary" icon="check" onClick={() => onConfirm(bin.n)}>
                {t("stale.stillHere")}
              </Button>
              <Button size="dense" variant="quiet" icon="x" onClick={() => onConfirm(bin.n)}>
                {t("stale.gone")}
              </Button>
            </div>
          }
        >
          {t("stale.body")}
        </Notice>
      ) : null}

      <Provenance region={region} t={t} />
    </div>
  );
}

function freshnessNote(answer: BinAnswer, t: T): string | undefined {
  if (answer.freshness === 4 && answer.stale === false) return undefined;
  return answer.stale ? t("stale.title") : undefined;
}

/* Disambiguation is its own interaction, not a weaker assertion. The system
   does not guess between three slots – it asks, and the answer rewrites the
   card in place and re-stamps it "you told us". */
function AskChoices({ answer, t, onAnswer }: { answer: BinAnswer; t: T; onAnswer: (stream: string) => void }) {
  const options = answer.disambiguation?.options ?? [];
  const noteKey = answer.disambiguation?.note_key;

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      {noteKey ? <p style={{ font: "var(--type-body)", color: "var(--text-body)" }}>{t(noteKey)}</p> : null}
      <div style={{ display: "grid", gap: "var(--space-2)" }}>
        {options.map((stream) => {
          // The swatch is the stream's own typical colour, from the taxonomy.
          const swatch = streamById(stream)?.typical_colors?.[0] ?? "grey";
          return (
            <button
              key={stream}
              type="button"
              onClick={() => onAnswer(stream)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
                minBlockSize: "var(--tap-outdoor)",
                paddingInline: "var(--space-4)",
                background: "var(--surface-card)",
                border: "var(--border-rule) solid var(--ink-0)",
                borderRadius: "var(--radius-2)",
                cursor: "pointer",
                textAlign: "start",
              }}
            >
              <ColorQuote color={swatch} label={t(`color.${swatch}`)} size="md" showLabel={false} />
              <span style={{ font: "var(--type-body-strong)", color: "var(--text-strong)", minInlineSize: 0 }}>
                {t(`stream.${stream}`)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* Not knowing is a real answer. It opens with what we DO know – the measured
   colours are quoted here even though we cannot name the bin, because the
   measurement is real and it is what the user can check against the object. */
function UnknownPanel({
  bin,
  region,
  t,
  onContribute,
}: {
  bin: FrameBin;
  region: Region;
  t: T;
  onContribute: () => void;
}) {
  const place = REGION_PLACE[region.key];
  return (
    <div style={{ display: "grid", gap: "var(--space-5)", alignContent: "start" }}>
      <article
        style={{
          background: "var(--surface-card)",
          backgroundImage: "var(--hatch-unknown)",
          border: "var(--border-rule) solid var(--ink-0)",
          borderRadius: "var(--radius-2)",
          padding: "var(--space-5)",
          display: "grid",
          gap: "var(--space-5)",
        }}
      >
        <header style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-4)" }}>
          <StreamGlyph stream="unknown" size="lg" tone="unknown" />
          <div style={{ display: "grid", gap: "var(--space-2)", minInlineSize: 0 }}>
            <span className="sbr-register" style={{ fontStyle: "italic" }}>
              {bin.n} / {t("unknown.register")}
            </span>
            <h2
              style={{
                font: "var(--type-answer)",
                fontSize: "var(--text-2xl)",
                letterSpacing: "var(--track-display)",
                color: "var(--text-strong)",
              }}
            >
              {t("unknown.title")}
            </h2>
          </div>
        </header>

        <div
          style={{
            display: "grid",
            gap: "var(--space-3)",
            padding: "var(--space-4)",
            background: "var(--surface-card)",
            border: "var(--border-hair) solid var(--line-hair)",
            borderRadius: "var(--radius-2)",
          }}
        >
          <span className="sbr-register">{t("unknown.seeTitle")}</span>
          <Quoted colors={bin.quoted} t={t} />
          <span
            style={{
              font: "var(--type-register)",
              letterSpacing: "var(--track-register)",
              textTransform: "uppercase",
              color: "var(--text-body)",
            }}
          >
            {t(`form.${bin.observation.form_factor}`)}
          </span>
          <p style={{ font: "var(--type-small)", color: "var(--text-muted)" }}>{t("unknown.seeBody", { place })}</p>
        </div>

        <p style={{ font: "var(--type-body)", color: "var(--text-body)" }}>
          {region.key === "none" ? t("unknown.regionBody") : t("unknown.normal")}
        </p>
      </article>

      <div style={{ display: "grid", gap: "var(--space-2)" }}>
        <span className="sbr-register">{t("unknown.meantime")}</span>
        <Button variant="secondary" block icon="search">
          {t("unknown.search")}
        </Button>
        <Button variant="secondary" block icon="map-pin">
          {t("unknown.street")}
        </Button>
      </div>

      <Button variant="signal" size="outdoor" block icon="flag" onClick={onContribute}>
        {t("unknown.tell")}
      </Button>
    </div>
  );
}

/* Submitted but not published. Visible to the person who sent it and to nobody
   else, and it claims nothing – it shows what you reported, shape and colour,
   not a stream. */
function PendingPanel({ bin, answer, t }: { bin: FrameBin; answer: BinAnswer; t: T }) {
  const r = answer.report ?? {};
  return (
    <div style={{ display: "grid", gap: "var(--space-5)", alignContent: "start" }}>
      <article
        style={{
          background: "var(--surface-card)",
          backgroundImage: "var(--hatch-unknown)",
          border: "var(--border-rule) solid var(--ink-0)",
          borderRadius: "var(--radius-2)",
          padding: "var(--space-5)",
          display: "grid",
          gap: "var(--space-5)",
        }}
      >
        <header style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-4)" }}>
          <StreamGlyph stream="unknown" size="lg" tone="unknown" />
          <div style={{ display: "grid", gap: "var(--space-2)", minInlineSize: 0 }}>
            <span className="sbr-register" style={{ fontStyle: "italic" }}>
              {bin.n} / {t("pending.register")}
            </span>
            <h2 style={{ font: "var(--type-title)", color: "var(--text-strong)" }}>{t("pending.title")}</h2>
          </div>
        </header>

        <div
          style={{
            display: "grid",
            gap: "var(--space-3)",
            padding: "var(--space-4)",
            background: "var(--surface-card)",
            border: "var(--border-hair) solid var(--line-hair)",
            borderRadius: "var(--radius-2)",
          }}
        >
          <span className="sbr-register">{t("pending.reported")}</span>
          {r.color ? (
            <ColorQuote color={r.color} part={t("part.body")} label={t(`color.${r.color}`)} size="sm" />
          ) : (
            <Quoted colors={bin.quoted} t={t} />
          )}
          <span
            style={{
              font: "var(--type-register)",
              letterSpacing: "var(--track-register)",
              textTransform: "uppercase",
              color: "var(--text-body)",
            }}
          >
            {t(`form.${r.form ?? bin.observation.form_factor}`)}
            {r.count && r.count > 1 ? ` · ${r.count}x` : ""}
          </span>
        </div>

        <p style={{ font: "var(--type-body)", color: "var(--text-body)" }}>{t("pending.body")}</p>
        <div>
          <Tag variant="signal" icon="clock">
            {t("sent.tag")}
          </Tag>
        </div>
      </article>

      <Notice tone="quiet" icon="info" title={t("sent.whyTitle")}>
        {t("sent.whyBody")}
      </Notice>
    </div>
  );
}
