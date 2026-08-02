import type { CSSProperties, ElementType, HTMLAttributes, ReactNode } from "react";

const cardTones = {
  plain: { background: "var(--surface-card)", borderColor: "var(--line-hair)", color: "var(--text-body)" },
  strong: { background: "var(--surface-card)", borderColor: "var(--ink-0)", color: "var(--text-body)" },
  sunk: { background: "var(--surface-sunk)", borderColor: "transparent", color: "var(--text-body)" },
  inverse: { background: "var(--surface-inverse)", borderColor: "var(--ink-0)", color: "var(--text-inverse)" },
  unknown: {
    background: "var(--surface-card)",
    borderColor: "var(--line-hair)",
    color: "var(--text-body)",
    backgroundImage: "var(--hatch-unknown)",
  },
} as const;

export interface CardProps extends HTMLAttributes<HTMLElement> {
  children?: ReactNode;
  tone?: keyof typeof cardTones;
  pad?: string;
  as?: ElementType;
  style?: CSSProperties;
}

export function Card({ children, tone = "plain", pad = "var(--space-5)", style, as: As = "div", ...rest }: CardProps) {
  const t = cardTones[tone] ?? cardTones.plain;
  return (
    <As
      style={{
        borderRadius: "var(--radius-2)",
        borderStyle: "solid",
        borderWidth: tone === "strong" ? "var(--border-rule)" : "var(--border-hair)",
        padding: pad,
        ...t,
        ...style,
      }}
      {...rest}
    >
      {children}
    </As>
  );
}
