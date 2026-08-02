import type { CSSProperties, InputHTMLAttributes } from "react";

import { Icon } from "../core/Icon";

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "style"> {
  label?: string;
  hint?: string;
  icon?: string;
  size?: "outdoor" | "default" | "dense";
  style?: CSSProperties;
}

export function TextField({ label, hint, icon, size = "default", id, style, ...rest }: TextFieldProps) {
  const h = size === "outdoor" ? "var(--tap-outdoor)" : size === "dense" ? "var(--tap-dense)" : "var(--tap-min)";
  const fs = size === "outdoor" ? "var(--text-md)" : "var(--text-base)";
  return (
    <div style={{ display: "grid", gap: "var(--space-2)", ...style }}>
      {label ? (
        <label
          htmlFor={id}
          style={{
            font: "var(--type-register)",
            letterSpacing: "var(--track-register)",
            textTransform: "uppercase",
            color: "var(--text-muted)",
          }}
        >
          {label}
        </label>
      ) : null}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          blockSize: h,
          paddingInline: "var(--space-4)",
          background: "var(--surface-card)",
          border: "var(--border-rule) solid var(--ink-0)",
          borderRadius: "var(--radius-2)",
        }}
      >
        {icon ? <Icon name={icon} size={20} style={{ color: "var(--text-muted)" }} /> : null}
        <input
          id={id}
          style={{
            flex: 1,
            minInlineSize: 0,
            border: 0,
            outline: "none",
            background: "transparent",
            font: "var(--type-body)",
            fontSize: fs,
            color: "var(--text-strong)",
          }}
          {...rest}
        />
      </div>
      {hint ? <span style={{ font: "var(--type-small)", color: "var(--text-muted)" }}>{hint}</span> : null}
    </div>
  );
}
