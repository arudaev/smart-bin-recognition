import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { Icon } from "./Icon";

const tagVariants = {
  outline: { background: "transparent", color: "var(--text-muted)", borderColor: "var(--line-hair)" },
  solid: { background: "var(--ink-0)", color: "var(--ink-inverse)", borderColor: "var(--ink-0)" },
  signal: { background: "var(--signal-tint)", color: "var(--signal)", borderColor: "var(--signal)" },
  quiet: { background: "var(--surface-sunk)", color: "var(--text-muted)", borderColor: "transparent" },
} as const;

export interface TagProps extends HTMLAttributes<HTMLSpanElement> {
  children?: ReactNode;
  icon?: string;
  variant?: keyof typeof tagVariants;
  style?: CSSProperties;
}

export function Tag({ children, icon, variant = "outline", style, ...rest }: TagProps) {
  const v = tagVariants[variant] ?? tagVariants.outline;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-1)",
        blockSize: 22,
        paddingInline: "var(--space-2)",
        font: "var(--type-register-sm)",
        letterSpacing: "var(--track-register)",
        textTransform: "uppercase",
        borderRadius: "var(--radius-1)",
        borderStyle: "solid",
        borderWidth: "var(--border-hair)",
        whiteSpace: "nowrap",
        ...v,
        ...style,
      }}
      {...rest}
    >
      {icon ? <Icon name={icon} size={12} stroke={2.5} /> : null}
      {children}
    </span>
  );
}
