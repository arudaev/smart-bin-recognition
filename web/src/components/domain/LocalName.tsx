import type { CSSProperties, HTMLAttributes } from "react";

/* Both, always. The translated name is the answer; the word printed on the lid
   is the thing the user has to match with their eyes. Neither may appear alone.
   `localLang`/`localDir` are set from the region pack, not from the UI locale –
   the word on the bin keeps its own script and direction inside an RTL layout. */

export interface LocalNameProps extends HTMLAttributes<HTMLDivElement> {
  translated: string;
  local?: string | null;
  localLang?: string;
  localDir?: "ltr" | "rtl";
  onBinLabel?: string;
  size?: "sm" | "md" | "lg";
  style?: CSSProperties;
}

export function LocalName({
  translated,
  local,
  localLang = "de",
  localDir = "ltr",
  onBinLabel = "on the bin",
  size = "lg",
  style,
  ...rest
}: LocalNameProps) {
  const primary = size === "lg" ? "var(--text-3xl)" : size === "md" ? "var(--text-xl)" : "var(--text-md)";
  const secondary = size === "lg" ? "var(--text-md)" : size === "md" ? "var(--text-base)" : "var(--text-sm)";
  return (
    <div style={{ display: "grid", gap: "var(--space-2)", ...style }} {...rest}>
      <h2
        style={{
          font: "var(--type-answer)",
          fontSize: primary,
          letterSpacing: "var(--track-display)",
          color: "var(--text-strong)",
          margin: 0,
        }}
      >
        {translated}
      </h2>
      {local ? (
        <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <span
            lang={localLang}
            dir={localDir}
            style={{
              font: "var(--type-local)",
              fontSize: secondary,
              color: "var(--text-body)",
              borderInlineStart: "var(--border-rule) solid var(--ink-0)",
              paddingInlineStart: "var(--space-3)",
            }}
          >
            {local}
          </span>
          <span
            style={{
              font: "var(--type-register-sm)",
              letterSpacing: "var(--track-register)",
              textTransform: "uppercase",
              color: "var(--text-faint)",
              whiteSpace: "nowrap",
            }}
          >
            {onBinLabel}
          </span>
        </div>
      ) : null}
    </div>
  );
}
