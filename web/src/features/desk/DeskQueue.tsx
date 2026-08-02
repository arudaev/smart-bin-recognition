import { useState } from "react";

import { Button, Card, Notice, Tag } from "@/components";
import { QUEUE } from "@/data/registry";
import type { T } from "@/i18n";
import { Quoted } from "@/features/shared/Provenance";

/* The contributor review queue. Agreement is enough to publish a rule; it is
   never enough to enter the training set. Different blast radii, and the panel
   says so rather than leaving a moderator to infer it. */

export function DeskQueue({ t }: { t: T }) {
  const [sel, setSel] = useState(0);
  const c = QUEUE[sel];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr var(--desk-panel)", blockSize: "100%", minBlockSize: 0 }}>
      <div
        style={{
          overflowY: "auto",
          background: "var(--surface-card)",
          borderInlineEnd: "var(--border-hair) solid var(--line-hair)",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            borderBlockEnd: "var(--border-rule) solid var(--ink-0)",
            padding: "var(--space-3) var(--space-5)",
          }}
        >
          {["desk.queueEntry", "desk.queueWhere", "desk.queueSeen", "desk.queueState"].map((k) => (
            <span key={k} className="sbr-register">
              {t(k)}
            </span>
          ))}
        </div>

        {QUEUE.map((row, i) => (
          <button
            key={row.id}
            type="button"
            onClick={() => setSel(i)}
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              alignItems: "center",
              inlineSize: "100%",
              minBlockSize: "var(--tap-dense)",
              padding: "var(--space-2) var(--space-5)",
              textAlign: "start",
              cursor: "pointer",
              background: sel === i ? "var(--surface-sunk)" : "transparent",
              border: 0,
              borderBlockEnd: "var(--border-hair) solid var(--line-quiet)",
              borderInlineStart: `var(--border-heavy) solid ${sel === i ? "var(--ink-0)" : "transparent"}`,
            }}
          >
            <span style={{ font: "var(--type-register)", color: "var(--text-strong)" }}>{row.id}</span>
            <span style={{ font: "var(--type-small)", color: "var(--text-body)" }}>{row.where}</span>
            <span
              style={{
                font: "var(--type-register-sm)",
                letterSpacing: "var(--track-register)",
                textTransform: "uppercase",
                color: "var(--text-muted)",
              }}
            >
              {t(row.seenKey)}
            </span>
            <span>
              <Tag variant={row.state === "ready" ? "solid" : row.state === "disputed" ? "signal" : "outline"}>
                {t(`queue.state.${row.state}`)}
              </Tag>
            </span>
          </button>
        ))}

        <div style={{ padding: "var(--space-5)" }}>
          <Notice tone="quiet" icon="info" title={t("desk.keyboardTitle")}>
            {t("desk.keyboardBody")}
          </Notice>
        </div>
      </div>

      <aside
        style={{
          overflowY: "auto",
          padding: "var(--space-5)",
          display: "grid",
          gap: "var(--space-5)",
          alignContent: "start",
          background: "var(--surface-card)",
        }}
      >
        <div style={{ display: "grid", gap: "var(--space-2)" }}>
          <span className="sbr-register">
            {c.id} · {t(`queue.state.${c.state}`)}
          </span>
          <h2 style={{ font: "var(--type-title)", color: "var(--text-strong)" }}>{t(`form.${c.form}`)}</h2>
          <span style={{ font: "var(--type-body)", color: "var(--text-muted)" }}>
            {c.where} · {t(c.seenKey)}
          </span>
        </div>

        <div
          aria-hidden="true"
          style={{
            blockSize: 180,
            border: "var(--border-hair) solid var(--line-hair)",
            borderRadius: "var(--radius-2)",
            background: "var(--paper-2)",
            backgroundImage: "var(--hatch-unknown)",
          }}
        />

        <Quoted colors={c.colors} t={t} size="md" />

        <Card tone="sunk" style={{ display: "grid", gap: "var(--space-2)" }}>
          <span className="sbr-register">{t("desk.agreement")}</span>
          <span style={{ font: "var(--type-body)" }}>{t("desk.agreeBody", { n: c.agree })}</span>
        </Card>

        <div style={{ display: "grid", gap: "var(--space-2)" }}>
          <Button block icon="check" disabled={c.agree < 2}>
            {t("desk.publish")}
          </Button>
          <Button block variant="secondary" icon="layers">
            {t("desk.merge")}
          </Button>
          <Button block variant="quiet" icon="x">
            {t("desk.reject")}
          </Button>
        </div>

        <Notice tone="attention" title={t("desk.publishTitle")}>
          {t("desk.publishBody")}
        </Notice>
      </aside>
    </div>
  );
}
