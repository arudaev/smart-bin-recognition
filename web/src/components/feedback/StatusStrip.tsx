import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

import { Icon } from "../core/Icon";

/* Connection states are ordinary, not alarming. One thin strip, mono, calm.
   The only animation in the product lives here: a 1.6s opacity pulse on the
   marker while the server is being reached, stopped by reduced-motion.
   The keyframes live in tokens/base.css. */

/* `demo` is a connection state and not a decoration: it is what "there is no
   detector at the other end" looks like. It carries a warning glyph rather than
   `live`'s shield-check on purpose - a shield-check over a camera means the
   boxes on the frame came from that camera, and in this state they did not. */
const stripStates = {
  live: { icon: "shield-check", dim: false },
  demo: { icon: "triangle-alert", dim: false },
  connecting: { icon: "loader-circle", dim: true },
  waking: { icon: "clock", dim: true },
  busy: { icon: "clock", dim: true },
  offline: { icon: "wifi-off", dim: false },
} as const;

export type ConnectionState = keyof typeof stripStates;

export interface StatusStripProps extends HTMLAttributes<HTMLDivElement> {
  state?: ConnectionState;
  message: string;
  onCamera?: boolean;
  action?: ReactNode;
  style?: CSSProperties;
}

export function StatusStrip({ state = "live", message, onCamera = false, action, style, ...rest }: StatusStripProps) {
  const s = stripStates[state] ?? stripStates.live;
  const pulsing = state === "connecting" || state === "waking";
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-2)",
        minBlockSize: 32,
        paddingInline: "var(--space-4)",
        background: onCamera ? "rgba(22,24,28,0.78)" : "var(--surface-sunk)",
        color: onCamera ? "rgba(255,255,255,0.92)" : "var(--text-muted)",
        borderBlockEnd: onCamera ? "none" : "var(--border-hair) solid var(--line-hair)",
        borderRadius: onCamera ? "var(--radius-2)" : 0,
        font: "var(--type-register-sm)",
        letterSpacing: "var(--track-register)",
        textTransform: "uppercase",
        ...style,
      }}
      {...rest}
    >
      <Icon
        name={s.icon}
        size={13}
        stroke={2.4}
        style={pulsing ? { animation: "sbrPulse 1.6s var(--ease-in-out) infinite" } : undefined}
      />
      <span style={{ flex: 1, minInlineSize: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {message}
      </span>
      {action}
    </div>
  );
}
