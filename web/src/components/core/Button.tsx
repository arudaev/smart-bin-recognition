import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";

import { Icon } from "./Icon";

const btnSizes = {
  outdoor: {
    minHeight: "var(--tap-outdoor)",
    padding: "0 var(--space-6)",
    fontSize: "var(--text-md)",
    gap: "var(--space-3)",
  },
  default: {
    minHeight: "var(--tap-min)",
    padding: "0 var(--space-5)",
    fontSize: "var(--text-base)",
    gap: "var(--space-2)",
  },
  dense: {
    minHeight: "var(--tap-dense)",
    padding: "0 var(--space-3)",
    fontSize: "var(--text-sm)",
    gap: "var(--space-2)",
  },
} as const;

const btnVariants = {
  primary: { background: "var(--ink-0)", color: "var(--ink-inverse)", borderColor: "var(--ink-0)" },
  secondary: { background: "var(--surface-card)", color: "var(--text-strong)", borderColor: "var(--ink-0)" },
  quiet: { background: "transparent", color: "var(--text-strong)", borderColor: "transparent" },
  signal: { background: "var(--signal)", color: "var(--signal-on)", borderColor: "var(--signal)" },
} as const;

export type ButtonVariant = keyof typeof btnVariants;
export type ButtonSize = keyof typeof btnSizes;

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  children?: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: string;
  iconEnd?: string;
  block?: boolean;
  style?: CSSProperties;
}

export function Button({
  children,
  variant = "primary",
  size = "default",
  icon,
  iconEnd,
  block = false,
  disabled = false,
  style,
  ...rest
}: ButtonProps) {
  const s = btnSizes[size] ?? btnSizes.default;
  const v = btnVariants[variant] ?? btnVariants.primary;
  const glyph = size === "outdoor" ? 22 : size === "dense" ? 16 : 18;
  return (
    <button
      type="button"
      disabled={disabled}
      style={{
        display: block ? "flex" : "inline-flex",
        inlineSize: block ? "100%" : "auto",
        /* An inline button must still not be wider than what holds it.
           Without this, "Search the rules instead" plus an icon plus padding
           measured 331px inside a 320px viewport - but only on Linux, where
           the font is wider than on Windows. A layout that depends on font
           metrics is one that breaks on somebody else's phone. */
        maxInlineSize: "100%",
        minInlineSize: 0,
        alignItems: "center",
        justifyContent: "center",
        gap: s.gap,
        minHeight: s.minHeight,
        padding: s.padding,
        fontSize: s.fontSize,
        fontFamily: "var(--font-sans)",
        fontWeight: "var(--weight-semibold)" as unknown as number,
        letterSpacing: "-0.01em",
        lineHeight: 1.15,
        textAlign: "center",
        borderRadius: "var(--radius-2)",
        borderStyle: "solid",
        borderWidth: "var(--border-rule)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.38 : 1,
        transition: "var(--transition-ui)",
        ...v,
        ...style,
      }}
      {...rest}
    >
      {icon ? <Icon name={icon} size={glyph} stroke={2.25} /> : null}
      <span>{children}</span>
      {iconEnd ? <Icon name={iconEnd} size={glyph} stroke={2.25} /> : null}
    </button>
  );
}
