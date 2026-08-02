import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { IconButton } from "../core/IconButton";

/* The answer surface on the phone. Sits over the camera, snaps to a peek or a
   full height, and carries an ink top rule so its edge survives any frame
   behind it. */

export interface SheetProps extends HTMLAttributes<HTMLElement> {
  children?: ReactNode;
  title?: string;
  register?: string;
  onClose?: () => void;
  closeLabel?: string;
  peek?: boolean;
  style?: CSSProperties;
}

export function Sheet({ children, title, register, onClose, closeLabel = "Close", peek = false, style, ...rest }: SheetProps) {
  return (
    <section
      style={{
        position: "relative",
        display: "grid",
        gridTemplateRows: "auto 1fr",
        background: "var(--surface-card)",
        borderStartStartRadius: "var(--radius-3)",
        borderStartEndRadius: "var(--radius-3)",
        borderBlockStart: "var(--border-rule) solid var(--ink-0)",
        boxShadow: "var(--shadow-sheet)",
        overflow: "hidden",
        ...style,
      }}
      {...rest}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          padding: "var(--space-3) var(--space-4) var(--space-3) var(--space-5)",
          borderBlockEnd: peek ? "none" : "var(--border-hair) solid var(--line-quiet)",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            inlineSize: 40,
            blockSize: 3,
            background: "var(--paper-4)",
            borderRadius: "var(--radius-round)",
            position: "absolute",
            // Centred without a physical transform, so it stays centred in RTL.
            insetInline: 0,
            marginInline: "auto",
            insetBlockStart: 6,
          }}
        />
        <div style={{ display: "grid", gap: 2, flex: 1, minInlineSize: 0, paddingBlockStart: "var(--space-2)" }}>
          {register ? (
            <span
              style={{
                font: "var(--type-register-sm)",
                letterSpacing: "var(--track-register)",
                textTransform: "uppercase",
                color: "var(--text-faint)",
              }}
            >
              {register}
            </span>
          ) : null}
          {title ? <h2 style={{ font: "var(--type-heading)", color: "var(--text-strong)" }}>{title}</h2> : null}
        </div>
        {onClose ? <IconButton name="x" label={closeLabel} variant="quiet" onClick={onClose} /> : null}
      </header>
      <div style={{ overflowY: "auto", padding: "var(--space-5)", paddingBlockStart: "var(--space-4)" }}>{children}</div>
    </section>
  );
}
