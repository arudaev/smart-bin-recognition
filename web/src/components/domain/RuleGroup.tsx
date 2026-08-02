import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import type { Verdict } from "./ItemRule";

/* The verdict said in words, once, above the rows it governs.
   A list of eight mixed rows makes every row carry its own verdict; grouping
   moves that job to a heading, so the marks become confirmation rather than
   the sole encoding – and the reader gets the answer before the detail. */

export interface RuleGroupProps extends HTMLAttributes<HTMLElement> {
  verdict?: Verdict;
  heading: string;
  children?: ReactNode;
  style?: CSSProperties;
}

export function RuleGroup({ verdict = "yes", heading, children, style, ...rest }: RuleGroupProps) {
  const bar = { yes: "var(--ink-0)", no: "var(--ink-0)", watch: "var(--signal)" }[verdict];
  return (
    <section style={{ display: "grid", gap: "var(--space-1)", ...style }} {...rest}>
      <h3
        style={{
          font: "var(--type-register)",
          letterSpacing: "var(--track-register)",
          textTransform: "uppercase",
          color: verdict === "watch" ? "var(--signal)" : "var(--text-strong)",
          paddingBlockEnd: "var(--space-2)",
          borderBlockEnd: "var(--border-rule) solid " + bar,
        }}
      >
        {heading}
      </h3>
      <ul style={{ margin: 0, padding: 0 }}>{children}</ul>
    </section>
  );
}
