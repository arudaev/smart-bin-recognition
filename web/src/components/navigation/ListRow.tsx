import type { CSSProperties, ReactNode } from "react";

import { Icon } from "../core/Icon";

export interface ListRowProps {
  leading?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  register?: ReactNode;
  trailing?: ReactNode;
  onClick?: () => void;
  selected?: boolean;
  dense?: boolean;
  style?: CSSProperties;
}

export function ListRow({
  leading,
  title,
  subtitle,
  register,
  trailing,
  onClick,
  selected = false,
  dense = false,
  style,
}: ListRowProps) {
  const As = onClick ? "button" : "div";
  return (
    <As
      type={onClick ? "button" : undefined}
      onClick={onClick}
      aria-current={selected ? "true" : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-4)",
        inlineSize: "100%",
        minBlockSize: dense ? "var(--tap-min)" : "var(--tap-outdoor)",
        padding: dense ? "var(--space-2) var(--space-4)" : "var(--space-3) var(--space-4)",
        textAlign: "start",
        background: selected ? "var(--surface-sunk)" : "transparent",
        border: 0,
        borderBlockEnd: "var(--border-hair) solid var(--line-quiet)",
        borderInlineStart: selected
          ? "var(--border-heavy) solid var(--ink-0)"
          : "var(--border-heavy) solid transparent",
        cursor: onClick ? "pointer" : "default",
        color: "var(--text-body)",
        ...style,
      }}
    >
      {leading}
      <span style={{ display: "grid", gap: 2, flex: 1, minInlineSize: 0 }}>
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
        <span
          style={{
            font: "var(--type-body-strong)",
            color: "var(--text-strong)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {title}
        </span>
        {subtitle ? <span style={{ font: "var(--type-small)", color: "var(--text-muted)" }}>{subtitle}</span> : null}
      </span>
      {trailing !== undefined ? (
        trailing
      ) : onClick ? (
        <Icon name="chevron-right" size={20} style={{ color: "var(--text-faint)" }} />
      ) : null}
    </As>
  );
}
