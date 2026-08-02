import type { CSSProperties, HTMLAttributes } from "react";

import { Icon } from "../core/Icon";

/* Endonyms only. No flags – a language is not a country, and the person who
   most needs this control cannot read the label above it. Each row is set in
   its own script and direction, so it is recognisable before it is readable. */

export interface LanguageItem {
  code: string;
  endonym: string;
  dir?: "ltr" | "rtl";
}

export interface LanguageListProps extends Omit<HTMLAttributes<HTMLUListElement>, "onChange"> {
  items?: LanguageItem[];
  value?: string;
  onChange?: (code: string) => void;
  style?: CSSProperties;
}

export function LanguageList({ items = [], value, onChange, style, ...rest }: LanguageListProps) {
  return (
    <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", ...style }} {...rest}>
      {items.map((it) => {
        const on = it.code === value;
        return (
          <li key={it.code}>
            <button
              type="button"
              onClick={() => onChange?.(it.code)}
              aria-pressed={on}
              lang={it.code}
              dir={it.dir ?? "ltr"}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
                inlineSize: "100%",
                minBlockSize: "var(--tap-outdoor)",
                paddingInline: "var(--space-4)",
                textAlign: "start",
                background: on ? "var(--surface-sunk)" : "transparent",
                color: "var(--text-strong)",
                border: 0,
                borderBlockEnd: "var(--border-hair) solid var(--line-quiet)",
                cursor: "pointer",
                font: "var(--type-body)",
                fontSize: "var(--text-md)",
                fontWeight: (on ? "var(--weight-semibold)" : "var(--weight-text)") as unknown as number,
              }}
            >
              <span style={{ flex: 1, minInlineSize: 0 }}>{it.endonym}</span>
              <span
                dir="ltr"
                style={{
                  font: "var(--type-register-sm)",
                  letterSpacing: "var(--track-register)",
                  textTransform: "uppercase",
                  color: "var(--text-faint)",
                }}
              >
                {it.code}
              </span>
              {on ? <Icon name="check" size={20} stroke={2.5} /> : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
