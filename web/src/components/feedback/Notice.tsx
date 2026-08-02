import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { Icon } from "../core/Icon";

const noticeTones = {
  info: { borderColor: "var(--ink-0)", background: "var(--surface-card)", icon: "info" },
  attention: { borderColor: "var(--signal)", background: "var(--signal-tint)", icon: "circle-alert" },
  quiet: { borderColor: "var(--line-hair)", background: "var(--surface-sunk)", icon: "info" },
} as const;

export interface NoticeProps extends HTMLAttributes<HTMLDivElement> {
  tone?: keyof typeof noticeTones;
  icon?: string;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  style?: CSSProperties;
}

export function Notice({ tone = "info", icon, title, children, action, style, ...rest }: NoticeProps) {
  const t = noticeTones[tone] ?? noticeTones.info;
  return (
    <div
      role="note"
      style={{
        display: "flex",
        gap: "var(--space-3)",
        alignItems: "flex-start",
        padding: "var(--space-4)",
        background: t.background,
        border: "var(--border-hair) solid " + t.borderColor,
        borderInlineStartWidth: "var(--border-heavy)",
        borderRadius: "var(--radius-2)",
        ...style,
      }}
      {...rest}
    >
      <Icon
        name={icon ?? t.icon}
        size={20}
        stroke={2}
        style={{ color: tone === "attention" ? "var(--signal)" : "var(--text-strong)", marginBlockStart: 1 }}
      />
      <div style={{ display: "grid", gap: "var(--space-2)", flex: 1, minInlineSize: 0 }}>
        {title ? <span style={{ font: "var(--type-body-strong)", color: "var(--text-strong)" }}>{title}</span> : null}
        {children ? <div style={{ font: "var(--type-small)", color: "var(--text-body)" }}>{children}</div> : null}
        {action}
      </div>
    </div>
  );
}
