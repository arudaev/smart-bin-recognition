import type { CSSProperties, HTMLAttributes } from "react";

import { IconButton } from "../core/IconButton";

export interface StepperProps extends Omit<HTMLAttributes<HTMLDivElement>, "onChange"> {
  label?: string;
  value?: number;
  min?: number;
  max?: number;
  onChange?: (value: number) => void;
  decreaseLabel?: string;
  increaseLabel?: string;
  style?: CSSProperties;
}

export function Stepper({
  label,
  value = 1,
  min = 1,
  max = 20,
  onChange,
  decreaseLabel = "One fewer",
  increaseLabel = "One more",
  style,
  ...rest
}: StepperProps) {
  const set = (n: number) => onChange?.(Math.max(min, Math.min(max, n)));
  return (
    <div style={{ display: "grid", gap: "var(--space-2)", ...style }} {...rest}>
      {label ? (
        <span
          style={{
            font: "var(--type-register)",
            letterSpacing: "var(--track-register)",
            textTransform: "uppercase",
            color: "var(--text-muted)",
          }}
        >
          {label}
        </span>
      ) : null}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <IconButton
          name="minus"
          label={decreaseLabel}
          variant="secondary"
          size="outdoor"
          disabled={value <= min}
          onClick={() => set(value - 1)}
        />
        <output
          style={{
            minInlineSize: 72,
            blockSize: "var(--tap-outdoor)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-xl)",
            fontWeight: "var(--weight-semibold)" as unknown as number,
            color: "var(--text-strong)",
            border: "var(--border-hair) solid var(--line-hair)",
            borderRadius: "var(--radius-2)",
            background: "var(--surface-card)",
          }}
        >
          {value}
        </output>
        <IconButton
          name="plus"
          label={increaseLabel}
          variant="secondary"
          size="outdoor"
          disabled={value >= max}
          onClick={() => set(value + 1)}
        />
      </div>
    </div>
  );
}
