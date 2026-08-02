import type { CSSProperties, HTMLAttributes } from "react";

import { Icon, STREAM_GLYPH } from "../core/Icon";

const glyphBoxes = { sm: 32, md: 44, lg: 60, xl: 76 } as const;

const tones = {
  plain: { background: "var(--surface-card)", borderColor: "var(--ink-0)", color: "var(--ink-0)" },
  filled: { background: "var(--ink-0)", borderColor: "var(--ink-0)", color: "var(--ink-inverse)" },
  quiet: { background: "var(--surface-sunk)", borderColor: "var(--line-hair)", color: "var(--text-body)" },
  unknown: {
    background: "var(--surface-card)",
    borderColor: "var(--ink-0)",
    color: "var(--ink-0)",
    backgroundImage: "var(--hatch-unknown)",
  },
} as const;

export interface StreamGlyphProps extends HTMLAttributes<HTMLSpanElement> {
  stream: string;
  size?: keyof typeof glyphBoxes;
  tone?: keyof typeof tones;
  label?: string;
  style?: CSSProperties;
}

export function StreamGlyph({ stream, size = "md", tone = "plain", label, style, ...rest }: StreamGlyphProps) {
  const box = glyphBoxes[size] ?? glyphBoxes.md;
  const t = tones[tone] ?? tones.plain;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        inlineSize: box,
        blockSize: box,
        flex: "none",
        borderRadius: "var(--radius-2)",
        borderStyle: "solid",
        borderWidth: "var(--border-rule)",
        ...t,
        ...style,
      }}
      {...rest}
    >
      <Icon name={STREAM_GLYPH[stream] ?? "circle-question-mark"} size={Math.round(box * 0.52)} stroke={1.9} label={label} />
    </span>
  );
}
