import type { CSSProperties, HTMLAttributes } from "react";

/* Honest about age. Every fact from the shared registry says when it was last
   confirmed. Four segments, filled from the start: 4 = confirmed this week,
   1 = not seen in months. Segments, not colour – a stale pin and a fresh pin
   differ in shape and in words, so the difference survives greyscale, sunlight
   and colour blindness. */

export interface FreshnessProps extends HTMLAttributes<HTMLSpanElement> {
  level?: number;
  note?: string;
  size?: "sm" | "md";
  style?: CSSProperties;
}

export function Freshness({ level = 4, note, size = "md", style, ...rest }: FreshnessProps) {
  const n = Math.max(0, Math.min(4, level));
  const w = size === "sm" ? 8 : 12;
  const h = size === "sm" ? 3 : 4;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)", ...style }} {...rest}>
      <span aria-hidden="true" style={{ display: "inline-flex", gap: 2 }}>
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            style={{
              inlineSize: w,
              blockSize: h,
              background: i < n ? "var(--ink-0)" : "transparent",
              boxShadow: i < n ? "none" : "inset 0 0 0 1px var(--ink-4)",
            }}
          />
        ))}
      </span>
      {note ? (
        <span
          style={{
            font: "var(--type-register-sm)",
            letterSpacing: "var(--track-register)",
            textTransform: "uppercase",
            color: n <= 1 ? "var(--text-body)" : "var(--text-muted)",
            fontStyle: n <= 1 ? "italic" : "normal",
          }}
        >
          {note}
        </span>
      ) : null}
    </span>
  );
}
