import { useState } from "react";

import { Button, Card, EmptyState, Freshness, Icon, ListRow, LocalName, Notice, StreamGlyph, Tag, TextField } from "@/components";
import { STREAM_GLYPH } from "@/components";
import { freshnessFrom } from "@/domain";
import { REGISTRY } from "@/data/registry";
import type { Region } from "@/data/regions";
import { REGION_PLACE } from "@/data/regions";
import type { T } from "@/i18n";
import { CoverageTag } from "@/features/shared/Provenance";

/* Where the bins are, and how recently each was confirmed. Pins are coarse on
   purpose: a bin outside a single house is a fact about that house. */

export function DeskMap({ t, region }: { t: T; region: Region }) {
  const rows = REGISTRY[region.key] ?? [];
  const [sel, setSel] = useState(0);
  const entry = rows[sel];
  const place = REGION_PLACE[region.key];

  return (
    <div style={{ display: "grid", gridTemplate: "var(--desk-split)", blockSize: "100%", minBlockSize: 0 }}>
      <div
        style={{
          position: "relative",
          background: "var(--paper-2)",
          borderInlineEnd: "var(--desk-pane-rule-inline)",
          borderBlockEnd: "var(--desk-pane-rule-block)",
        }}
      >
        {rows.length ? (
          <>
            <div
              aria-hidden="true"
              style={{
                position: "absolute",
                inset: 0,
                background: "var(--paper-2)",
                backgroundImage:
                  "linear-gradient(var(--line-hair) 1px, transparent 1px), linear-gradient(90deg, var(--line-hair) 1px, transparent 1px)",
                backgroundSize: "48px 48px",
                opacity: 0.6,
              }}
            />
            <div style={{ position: "absolute", inset: 0 }}>
              {rows.map((r, i) => {
                const fresh = freshnessFrom(r.lastConfirmed);
                return (
                  <button
                    key={r.where + i}
                    type="button"
                    onClick={() => setSel(i)}
                    style={{
                      position: "absolute",
                      cursor: "pointer",
                      insetInlineStart: `${r.at[0]}%`,
                      insetBlockStart: `${r.at[1]}%`,
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                      minBlockSize: "var(--tap-min)",
                      padding: "var(--space-1) var(--space-3)",
                      background: sel === i ? "var(--ink-0)" : "var(--surface-card)",
                      color: sel === i ? "var(--ink-inverse)" : "var(--text-strong)",
                      border: "var(--border-rule) solid var(--ink-0)",
                      borderRadius: "var(--radius-2)",
                      boxShadow: "var(--shadow-marker)",
                    }}
                  >
                    <Icon name={STREAM_GLYPH[r.stream] ?? "circle-question-mark"} size={16} stroke={2} />
                    <span
                      style={{
                        font: "var(--type-register-sm)",
                        letterSpacing: "var(--track-register)",
                        textTransform: "uppercase",
                      }}
                    >
                      {r.count}x
                    </span>
                    <span aria-hidden="true" style={{ display: "inline-flex", gap: 2 }}>
                      {[0, 1, 2, 3].map((k) => (
                        <span
                          key={k}
                          style={{
                            inlineSize: 5,
                            blockSize: 3,
                            background: k < fresh ? "currentColor" : "transparent",
                            boxShadow: k < fresh ? "none" : "inset 0 0 0 1px currentColor",
                            opacity: k < fresh ? 1 : 0.4,
                          }}
                        />
                      ))}
                    </span>
                  </button>
                );
              })}
            </div>
            <div
              style={{
                position: "absolute",
                insetBlockEnd: "var(--space-5)",
                insetInlineStart: "var(--space-5)",
                display: "flex",
                gap: "var(--space-2)",
                flexWrap: "wrap",
              }}
            >
              <Tag variant="solid" icon="map-pin">
                {rows.length} · {place}
              </Tag>
              <Tag icon="clock">{t("desk.pinsShow")}</Tag>
            </div>
          </>
        ) : (
          <div style={{ display: "grid", placeItems: "center", blockSize: "100%", padding: "var(--gutter-desk)" }}>
            <div style={{ maxInlineSize: 460 }}>
              <EmptyState
                icon="map"
                title={t("desk.emptyTitle", { place })}
                action={<Button icon="plus">{t("desk.startPack", { place })}</Button>}
              >
                {t("desk.emptyBody")}
              </EmptyState>
            </div>
          </div>
        )}
      </div>

      <aside style={{ display: "grid", gridTemplateRows: "auto 1fr", minBlockSize: 0, background: "var(--surface-card)" }}>
        <div
          style={{
            padding: "var(--space-5)",
            borderBlockEnd: "var(--border-hair) solid var(--line-hair)",
            display: "grid",
            gap: "var(--space-3)",
            justifyItems: "start",
          }}
        >
          <TextField id="near" icon="search" label={t("desk.near")} placeholder={place} style={{ inlineSize: "100%" }} />
          <CoverageTag region={region} t={t} />
        </div>

        <div style={{ overflowY: "auto" }}>
          {rows.map((r, i) => {
            const fresh = freshnessFrom(r.lastConfirmed);
            return (
              <ListRow
                key={r.where + i}
                selected={sel === i}
                onClick={() => setSel(i)}
                dense
                leading={<StreamGlyph stream={r.stream} size="sm" tone={r.stream === "unknown" ? "unknown" : "plain"} />}
                title={t(`stream.${r.stream}`)}
                subtitle={`${r.where} · ${r.count}`}
                trailing={<Freshness level={fresh} size="sm" />}
              />
            );
          })}

          <div style={{ padding: "var(--space-5)", display: "grid", gap: "var(--space-4)" }}>
            {entry ? (
              <Card tone="strong" style={{ display: "grid", gap: "var(--space-3)" }}>
                <span className="sbr-register">{t("desk.selected")}</span>
                <LocalName
                  translated={t(`stream.${entry.stream}`)}
                  local={entry.where}
                  localLang="de"
                  onBinLabel={t("desk.queueWhere")}
                  size="md"
                />
                <Freshness level={freshnessFrom(entry.lastConfirmed)} />
                <div style={{ display: "flex", gap: "var(--space-2)" }}>
                  <Button size="dense" variant="secondary" icon="check">
                    {t("stale.stillHere")}
                  </Button>
                  <Button size="dense" variant="quiet" icon="x">
                    {t("stale.gone")}
                  </Button>
                </div>
              </Card>
            ) : null}
            <Notice tone="quiet" icon="shield-check" title={t("desk.coarseTitle")}>
              {t("desk.coarseBody")}
            </Notice>
          </div>
        </div>
      </aside>
    </div>
  );
}
