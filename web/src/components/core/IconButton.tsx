import type { ButtonHTMLAttributes, CSSProperties } from "react";

import { Icon } from "./Icon";

const ibSizes = { outdoor: 56, default: 44, dense: 36 } as const;

const ibVariants = {
  primary: { background: "var(--ink-0)", color: "var(--ink-inverse)", borderColor: "var(--ink-0)" },
  secondary: { background: "var(--surface-card)", color: "var(--text-strong)", borderColor: "var(--ink-0)" },
  quiet: { background: "transparent", color: "var(--text-strong)", borderColor: "transparent" },
  /* The only place the system writes over the photograph, and it stays
     achromatic: a translucent ink plate with a paper hairline. */
  onCamera: { background: "rgba(22,24,28,0.72)", color: "#fff", borderColor: "rgba(255,255,255,0.5)" },
} as const;

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type" | "name"> {
  name: string;
  label: string;
  variant?: keyof typeof ibVariants;
  size?: keyof typeof ibSizes;
  style?: CSSProperties;
}

export function IconButton({
  name,
  label,
  variant = "quiet",
  size = "default",
  disabled = false,
  style,
  ...rest
}: IconButtonProps) {
  const box = ibSizes[size] ?? ibSizes.default;
  const v = ibVariants[variant] ?? ibVariants.quiet;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        inlineSize: box,
        blockSize: box,
        flex: "none",
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
      <Icon name={name} size={box <= 36 ? 18 : box <= 44 ? 20 : 24} stroke={2} />
    </button>
  );
}
