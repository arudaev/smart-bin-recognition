import { useState } from "react";

import { EmptyState, Icon, ListRow, ResultCard, StreamGlyph, Tag, TextField } from "@/components";
import { STREAM_GLYPH } from "@/components";
import { LOOKUP, STREAMS } from "@/data/taxonomy";
import type { Region } from "@/data/regions";
import { REGION_ID, localNameFor } from "@/data/regions";
import type { T } from "@/i18n";
import { Provenance } from "@/features/shared/Provenance";
import { RulesList } from "@/features/shared/Rules";

/* Search by item is the accessibility-critical path: a text-only route to
   every rule in the product, reachable with no camera and no connection.
   Browse-by-bin is its complement for people who already know the container. */

export function DeskRules({ t, region }: { t: T; region: Region }) {
  const [q, setQ] = useState("");
  const browsable = STREAMS.filter((s) => s.id !== "unknown").map((s) => s.id);
  const [sel, setSel] = useState(browsable[0]);

  const needle = q.trim().toLowerCase();
  const hits = LOOKUP.filter((r) => t(`item.${r.item}`).toLowerCase().includes(needle));

  return (
    <div style={{ display: "grid", gridTemplateColumns: "var(--desk-panel) 1fr", blockSize: "100%", minBlockSize: 0 }}>
      <div
        style={{
          display: "grid",
          gridTemplateRows: "auto 1fr",
          minBlockSize: 0,
          borderInlineEnd: "var(--border-hair) solid var(--line-hair)",
          background: "var(--surface-card)",
        }}
      >
        <div style={{ padding: "var(--space-5)", borderBlockEnd: "var(--border-hair) solid var(--line-hair)" }}>
          <TextField
            id="desk-q"
            icon="search"
            label={t("rules.searchLabel")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("rules.placeholder")}
          />
        </div>

        <div style={{ overflowY: "auto" }}>
          {hits.length ? (
            hits.map((r, i) => (
              <ListRow
                key={r.item + i}
                dense
                onClick={() => setSel(r.stream)}
                selected={sel === r.stream && Boolean(q)}
                leading={<StreamGlyph stream={r.stream} size="sm" />}
                title={t(`item.${r.item}`)}
                subtitle={`${t("rules.goesIn")}: ${t(`stream.${r.stream}`)}`}
                register={r.verdict === "watch" ? t("rules.commonlyWrong") : undefined}
              />
            ))
          ) : (
            <div style={{ padding: "var(--space-5)" }}>
              <EmptyState icon="search" title={t("rules.noMatch", { q })}>
                {t("rules.noMatchBody")}
              </EmptyState>
            </div>
          )}
        </div>
      </div>

      <div
        style={{
          overflowY: "auto",
          padding: "var(--gutter-desk)",
          display: "grid",
          gap: "var(--space-6)",
          alignContent: "start",
          justifyItems: "start",
        }}
      >
        <div style={{ display: "grid", gap: "var(--space-2)" }}>
          <span className="sbr-register">{t("rules.browseByBin")}</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
            {browsable.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSel(s)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  minBlockSize: "var(--tap-min)",
                  paddingInline: "var(--space-3)",
                  background: sel === s ? "var(--ink-0)" : "var(--surface-card)",
                  color: sel === s ? "var(--ink-inverse)" : "var(--text-body)",
                  border: `var(--border-hair) solid ${sel === s ? "var(--ink-0)" : "var(--line-hair)"}`,
                  borderRadius: "var(--radius-2)",
                  cursor: "pointer",
                  font: "var(--type-small)",
                  fontWeight: "var(--weight-medium)" as unknown as number,
                  textAlign: "start",
                }}
              >
                <Icon name={STREAM_GLYPH[s] ?? "circle-question-mark"} size={17} />
                {t(`stream.${s}`)}
              </button>
            ))}
          </div>
        </div>

        <div style={{ maxInlineSize: 720, inlineSize: "100%", display: "grid", gap: "var(--space-5)" }}>
          <ResultCard
            stream={sel}
            translated={t(`stream.${sel}`)}
            local={localNameFor(region, sel)}
            localLang="de"
            onBinLabel={t("answer.onBin")}
            level="assert"
            footer={<Tag icon="info">{REGION_ID[region.key]}</Tag>}
          >
            <RulesList stream={sel} t={t} />
          </ResultCard>
          <Provenance region={region} t={t} />
        </div>
      </div>
    </div>
  );
}
