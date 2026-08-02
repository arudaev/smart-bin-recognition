import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { ColorQuote } from "./ColorQuote";
import { Freshness } from "./Freshness";
import { LocalName } from "./LocalName";
import { StreamGlyph } from "./StreamGlyph";

/* The answer. Three registers, chosen by how sure the system is – and the
   difference is grammatical, not chromatic:
     assert  a statement
     hedge   a qualified statement, hairline-dashed, with a way to disagree
     ask     a question, with the choices as the body
   `unknown` is not a failure state: it is a fourth, fully designed answer. */

export type ResultLevel = "assert" | "hedge" | "ask" | "unknown";

const levelRegister: Record<ResultLevel, string | null> = {
  assert: null,
  hedge: "most likely",
  ask: "which one?",
  unknown: "not known here",
};

export interface QuotedColor {
  color: string;
  label?: string;
  part?: string;
}

export interface ResultCardProps extends HTMLAttributes<HTMLElement> {
  stream?: string;
  index?: number | null;
  translated: string;
  local?: string | null;
  localLang?: string;
  localDir?: "ltr" | "rtl";
  level?: ResultLevel;
  colors?: QuotedColor[];
  freshness?: number | null;
  freshnessNote?: string;
  register?: string | null;
  children?: ReactNode;
  footer?: ReactNode;
  onBinLabel?: string;
  style?: CSSProperties;
}

export function ResultCard({
  stream = "unknown",
  index,
  translated,
  local,
  localLang = "de",
  localDir = "ltr",
  level = "assert",
  colors = [],
  freshness,
  freshnessNote,
  register,
  children,
  footer,
  onBinLabel = "on the bin",
  style,
  ...rest
}: ResultCardProps) {
  const isUnknown = level === "unknown" || stream === "unknown";
  const eyebrow = register ?? levelRegister[level];
  return (
    <article
      style={{
        background: "var(--surface-card)",
        backgroundImage: isUnknown ? "var(--hatch-unknown)" : "none",
        border: "var(--border-rule) solid var(--ink-0)",
        borderStyle: level === "hedge" ? "dashed" : "solid",
        borderRadius: "var(--radius-2)",
        padding: "var(--space-5)",
        display: "grid",
        gap: "var(--space-4)",
        ...style,
      }}
      {...rest}
    >
      <header style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-4)" }}>
        <StreamGlyph stream={stream} size="lg" tone={isUnknown ? "unknown" : "plain"} />
        <div style={{ display: "grid", gap: "var(--space-2)", minInlineSize: 0, flex: 1 }}>
          {eyebrow || index != null ? (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
                font: "var(--type-register-sm)",
                letterSpacing: "var(--track-register)",
                textTransform: "uppercase",
                color: "var(--text-muted)",
              }}
            >
              {index != null ? (
                <span style={{ color: "var(--text-strong)", fontWeight: "var(--weight-semibold)" as unknown as number }}>
                  {index}
                </span>
              ) : null}
              {index != null && eyebrow ? <span style={{ color: "var(--ink-4)" }}>/</span> : null}
              {eyebrow ? (
                <span style={{ fontStyle: level === "hedge" || isUnknown ? "italic" : "normal" }}>{eyebrow}</span>
              ) : null}
            </div>
          ) : null}
          <LocalName
            translated={translated}
            local={local}
            localLang={localLang}
            localDir={localDir}
            onBinLabel={onBinLabel}
            size="lg"
          />
        </div>
      </header>

      {colors.length ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "var(--space-2) var(--space-5)",
            paddingBlock: "var(--space-3)",
            borderBlock: "var(--border-hair) solid var(--line-quiet)",
          }}
        >
          {colors.map((c) => (
            <ColorQuote key={String(c.part) + c.color} color={c.color} label={c.label} part={c.part} size="sm" />
          ))}
        </div>
      ) : null}

      {children}

      {freshness != null || footer ? (
        <footer
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--space-4)",
            flexWrap: "wrap",
          }}
        >
          {freshness != null ? <Freshness level={freshness} note={freshnessNote} size="sm" /> : <span />}
          {footer}
        </footer>
      ) : null}
    </article>
  );
}
