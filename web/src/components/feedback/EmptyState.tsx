import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { Icon } from "../core/Icon";

/* Nothing here is an error. An empty region, an unmatched search and a bin we
   cannot name all use this: hatched plate, plain sentence, one way forward. */

export interface EmptyStateProps extends HTMLAttributes<HTMLDivElement> {
  icon?: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  hatched?: boolean;
  style?: CSSProperties;
}

export function EmptyState({
  icon = "circle-question-mark",
  title,
  children,
  action,
  hatched = true,
  style,
  ...rest
}: EmptyStateProps) {
  return (
    <div
      style={{
        display: "grid",
        /* `minmax(0, 1fr)`, not the implicit `auto`. An auto track takes the
           MAX-CONTENT of its widest child, so a long action label sized this
           card past a 320px viewport instead of wrapping inside it - and only
           on a platform whose font is a little wider, which is the worst kind
           of layout bug to find. With a zero minimum the track can shrink and
           the button wraps. */
        gridTemplateColumns: "minmax(0, 1fr)",
        justifyItems: "center",
        gap: "var(--space-4)",
        padding: "var(--space-8) var(--space-5)",
        textAlign: "center",
        background: "var(--surface-card)",
        backgroundImage: hatched ? "var(--hatch-unknown)" : "none",
        border: "var(--border-hair) solid var(--line-hair)",
        borderRadius: "var(--radius-2)",
        ...style,
      }}
      {...rest}
    >
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          inlineSize: 56,
          blockSize: 56,
          background: "var(--surface-card)",
          border: "var(--border-rule) solid var(--ink-0)",
          borderRadius: "var(--radius-2)",
          color: "var(--ink-0)",
        }}
      >
        <Icon name={icon} size={28} stroke={1.9} />
      </span>
      <h3 style={{ font: "var(--type-title)", color: "var(--text-strong)", maxInlineSize: "24ch" }}>{title}</h3>
      {children ? (
        <p style={{ font: "var(--type-body)", color: "var(--text-muted)", maxInlineSize: "40ch" }}>{children}</p>
      ) : null}
      {action}
    </div>
  );
}
