import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { IconButton } from "../core/IconButton";

export interface TopBarProps extends HTMLAttributes<HTMLElement> {
  title?: string;
  register?: string;
  backLabel?: string;
  onBack?: () => void;
  actions?: ReactNode;
  style?: CSSProperties;
}

export function TopBar({ title, register, backLabel, onBack, actions, style, ...rest }: TopBarProps) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-3)",
        minBlockSize: 60,
        paddingInline: "var(--space-4)",
        background: "var(--surface-card)",
        borderBlockEnd: "var(--border-rule) solid var(--ink-0)",
        ...style,
      }}
      {...rest}
    >
      {onBack ? (
        <IconButton
          name="arrow-left"
          label={backLabel ?? "Back"}
          variant="quiet"
          onClick={onBack}
          style={{ marginInlineStart: "calc(var(--space-3) * -1)" }}
        />
      ) : null}
      <div style={{ display: "grid", gap: 1, flex: 1, minInlineSize: 0 }}>
        {register ? (
          <span
            style={{
              font: "var(--type-register-sm)",
              letterSpacing: "var(--track-register)",
              textTransform: "uppercase",
              color: "var(--text-faint)",
            }}
          >
            {register}
          </span>
        ) : null}
        {title ? (
          <h1
            style={{
              font: "var(--type-heading)",
              color: "var(--text-strong)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {title}
          </h1>
        ) : null}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-1)" }}>{actions}</div>
    </header>
  );
}
