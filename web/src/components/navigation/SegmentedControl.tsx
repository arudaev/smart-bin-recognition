import type { CSSProperties, HTMLAttributes } from "react";

import { Icon } from "../core/Icon";

export interface SegmentedItem<T extends string = string> {
  value: T;
  label: string;
  icon?: string;
}

export interface SegmentedControlProps<T extends string = string>
  extends Omit<HTMLAttributes<HTMLDivElement>, "onChange"> {
  items?: SegmentedItem<T>[];
  value?: T;
  onChange?: (value: T) => void;
  size?: "outdoor" | "default" | "dense";
  style?: CSSProperties;
}

export function SegmentedControl<T extends string = string>({
  items = [],
  value,
  onChange,
  size = "default",
  style,
  ...rest
}: SegmentedControlProps<T>) {
  const h = size === "outdoor" ? "var(--tap-outdoor)" : size === "dense" ? "var(--tap-dense)" : "var(--tap-min)";
  return (
    <div
      role="tablist"
      style={{
        display: "inline-grid",
        gridAutoFlow: "column",
        /* `minmax(0, 1fr)`, not `1fr`. A bare `1fr` track has an automatic
           MINIMUM of its content, and these cells are `nowrap`, so three
           labels sized the control past a 320px viewport rather than
           sharing it. The minmax lets the tracks actually shrink. */
        gridAutoColumns: "minmax(0, 1fr)",
        maxInlineSize: "100%",
        border: "var(--border-rule) solid var(--ink-0)",
        borderRadius: "var(--radius-2)",
        background: "var(--surface-card)",
        overflow: "hidden",
        ...style,
      }}
      {...rest}
    >
      {items.map((it, i) => {
        const on = it.value === value;
        return (
          <button
            key={it.value}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange?.(it.value)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "var(--space-2)",
              blockSize: h,
              paddingInline: "var(--space-4)",
              border: 0,
              borderInlineStart: i === 0 ? "none" : "var(--border-hair) solid var(--ink-0)",
              background: on ? "var(--ink-0)" : "transparent",
              color: on ? "var(--ink-inverse)" : "var(--text-body)",
              font: "var(--type-body)",
              fontWeight: (on ? "var(--weight-semibold)" : "var(--weight-medium)") as unknown as number,
              fontSize: size === "dense" ? "var(--text-sm)" : "var(--text-base)",
              cursor: "pointer",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              minInlineSize: 0,
              transition: "var(--transition-ui)",
            }}
          >
            {it.icon ? <Icon name={it.icon} size={17} stroke={2.1} /> : null}
            {it.label}
          </button>
        );
      })}
    </div>
  );
}
