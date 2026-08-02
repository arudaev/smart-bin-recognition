import type { CSSProperties, HTMLAttributes } from "react";

/* QUOTED COLOUR – the system's central idea.
   The interface owns no colour. A physical bin colour may appear on screen only
   here: inside a hard-bounded swatch, with an ink hairline, always beside the
   colour's translated name. Colour is therefore never a carrier of meaning on
   its own, and the interface can never be confused with the object. */

const quoteSwatch: Record<string, string> = {
  blue: "var(--bin-blue)",
  green: "var(--bin-green)",
  brown: "var(--bin-brown)",
  black: "var(--bin-black)",
  grey: "var(--bin-grey)",
  yellow: "var(--bin-yellow)",
  orange: "var(--bin-orange)",
  red: "var(--bin-red)",
  white: "var(--bin-white)",
  metal: "var(--bin-metal)",
};

const quoteSizes = { sm: 14, md: 20, lg: 28 } as const;

export interface ColorQuoteProps extends Omit<HTMLAttributes<HTMLSpanElement>, "color"> {
  color: string;
  label?: string;
  part?: string;
  size?: keyof typeof quoteSizes;
  showLabel?: boolean;
  style?: CSSProperties;
}

export function ColorQuote({ color, label, part, size = "md", showLabel = true, style, ...rest }: ColorQuoteProps) {
  const box = quoteSizes[size] ?? quoteSizes.md;
  const fill =
    color === "transparent"
      ? { backgroundImage: "var(--bin-transparent)" }
      : { background: quoteSwatch[color] ?? "var(--paper-3)" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)", ...style }} {...rest}>
      <span
        aria-hidden="true"
        style={{
          inlineSize: box,
          blockSize: box,
          flex: "none",
          borderRadius: "var(--radius-1)",
          border: "var(--border-hair) solid var(--ink-0)",
          boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.28)",
          ...fill,
        }}
      />
      {showLabel ? (
        <span
          style={{
            font: "var(--type-register)",
            letterSpacing: "var(--track-register)",
            textTransform: "uppercase",
            color: "var(--text-body)",
            whiteSpace: "nowrap",
          }}
        >
          {part ? <span style={{ color: "var(--text-faint)" }}>{part} </span> : null}
          {label || color}
        </span>
      ) : (
        <span className="sbr-visually-hidden">
          {part ? part + " " : ""}
          {label || color}
        </span>
      )}
    </span>
  );
}
