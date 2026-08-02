import type { ButtonHTMLAttributes, CSSProperties } from "react";

import { Icon } from "../core/Icon";

/* A large, one-handed choice. Contribution is entirely structured – no free
   text anywhere – so these tiles are how a user describes a bin we do not know. */

export interface ChoiceTileProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type" | "title"> {
  icon?: string;
  title: string;
  meta?: string;
  selected?: boolean;
  onSelect?: () => void;
  style?: CSSProperties;
}

export function ChoiceTile({ icon, title, meta, selected = false, onSelect, style, ...rest }: ChoiceTileProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-4)",
        inlineSize: "100%",
        minBlockSize: "var(--tap-outdoor)",
        padding: "var(--space-3) var(--space-4)",
        textAlign: "start",
        background: selected ? "var(--ink-0)" : "var(--surface-card)",
        color: selected ? "var(--ink-inverse)" : "var(--text-strong)",
        border: "var(--border-rule) solid var(--ink-0)",
        borderRadius: "var(--radius-2)",
        cursor: "pointer",
        transition: "var(--transition-ui)",
        ...style,
      }}
      {...rest}
    >
      {icon ? <Icon name={icon} size={26} stroke={1.9} /> : null}
      <span style={{ display: "grid", gap: 2, flex: 1, minInlineSize: 0 }}>
        <span style={{ font: "var(--type-body-strong)" }}>{title}</span>
        {meta ? (
          <span
            style={{
              font: "var(--type-register-sm)",
              letterSpacing: "var(--track-register)",
              textTransform: "uppercase",
              opacity: 0.72,
            }}
          >
            {meta}
          </span>
        ) : null}
      </span>
      {selected ? <Icon name="check" size={22} stroke={2.5} /> : null}
    </button>
  );
}
