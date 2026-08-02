import type { CSSProperties, LiHTMLAttributes, ReactNode } from "react";

import { Icon } from "../core/Icon";

/* Three silhouettes, not three fills.
   Yes / no are the two states that must never be confused, so they differ in
   OUTLINE CLASS before they differ in anything else – a fill difference is the
   first thing to disappear on a scratched screen at noon.

     yes      round, solid, heavy      a disc with a knocked-out check
     no       boxed, hollow, struck    a square crossed by one heavy diagonal
     careful  pointed, unboxed, light  a bare triangle, no container at all

   A single 45 degree bar is the lowest-frequency mark available: it survives
   blur, glare, low resolution and peripheral vision better than any glyph
   inside a box. The verdict word is stated once per group by RuleGroup, so no
   row ever depends on the mark alone. */

export type Verdict = "yes" | "no" | "watch";

export interface ItemRuleProps extends LiHTMLAttributes<HTMLLIElement> {
  verdict?: Verdict;
  children?: ReactNode;
  verdictLabel?: string;
  note?: string;
  style?: CSSProperties;
}

export function ItemRule({ verdict = "yes", children, verdictLabel, note, style, ...rest }: ItemRuleProps) {
  let mark: ReactNode;
  if (verdict === "yes") {
    mark = (
      <span
        aria-hidden="true"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          inlineSize: 24,
          blockSize: 24,
          flex: "none",
          marginBlockStart: 1,
          borderRadius: "var(--radius-round)",
          background: "var(--ink-0)",
          color: "var(--ink-inverse)",
        }}
      >
        <Icon name="check" size={15} stroke={3} />
      </span>
    );
  } else if (verdict === "no") {
    mark = (
      <span
        aria-hidden="true"
        style={{
          inlineSize: 24,
          blockSize: 24,
          flex: "none",
          marginBlockStart: 1,
          borderRadius: "var(--radius-1)",
          border: "var(--border-heavy) solid var(--ink-0)",
          backgroundImage: "linear-gradient(45deg, transparent 42%, var(--ink-0) 42% 58%, transparent 58%)",
        }}
      />
    );
  } else {
    mark = (
      <span
        aria-hidden="true"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          inlineSize: 24,
          blockSize: 24,
          flex: "none",
          marginBlockStart: 1,
          color: "var(--signal)",
        }}
      >
        <Icon name="triangle-alert" size={23} stroke={2.4} />
      </span>
    );
  }

  return (
    <li
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--space-3)",
        paddingBlock: "var(--space-3)",
        borderBlockEnd: "var(--border-hair) solid var(--line-quiet)",
        listStyle: "none",
        ...style,
      }}
      {...rest}
    >
      {mark}
      <span style={{ display: "grid", gap: 2, minInlineSize: 0 }}>
        <span
          style={{
            font: "var(--type-body)",
            fontWeight: (verdict === "no" ? "var(--weight-regular)" : "var(--weight-medium)") as unknown as number,
            color: "var(--text-strong)",
          }}
        >
          {verdictLabel ? <span className="sbr-visually-hidden">{verdictLabel}: </span> : null}
          {children}
        </span>
        {note ? <span style={{ font: "var(--type-small)", color: "var(--text-muted)" }}>{note}</span> : null}
      </span>
    </li>
  );
}
