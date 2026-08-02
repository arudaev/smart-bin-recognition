import { useState } from "react";

import { Button, EmptyState, ListRow, StreamGlyph, TextField, TopBar } from "@/components";
import { LOOKUP } from "@/data/taxonomy";
import type { Region } from "@/data/regions";
import { REGION_PLACE } from "@/data/regions";
import type { T } from "@/i18n";

/* The text-only route to every rule. Nothing here needs a camera or a
   connection – which is the half of the product the people who most need it
   can actually reach. */

export function PhoneRules({ t, region, onClose }: { t: T; region: Region; onClose: () => void }) {
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const hits = LOOKUP.filter((r) => t(`item.${r.item}`).toLowerCase().includes(needle));

  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: "auto auto 1fr",
        blockSize: "100%",
        background: "var(--surface-page)",
        overflow: "hidden",
      }}
    >
      <TopBar
        onBack={onClose}
        backLabel={t("ui.back")}
        title={t("rules.title")}
        register={`${REGION_PLACE[region.key]} · ${t("rules.offline")}`}
      />

      <div style={{ padding: "var(--gutter-phone)" }}>
        <TextField
          id="phone-q"
          icon="search"
          size="outdoor"
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
              leading={<StreamGlyph stream={r.stream} size="sm" />}
              title={t(`item.${r.item}`)}
              subtitle={`${t("rules.goesIn")}: ${t(`stream.${r.stream}`)}`}
              register={r.verdict === "watch" ? t("rules.commonlyWrong") : undefined}
            />
          ))
        ) : (
          <div style={{ padding: "var(--gutter-phone)" }}>
            <EmptyState
              icon="search"
              title={t("rules.noMatch", { q })}
              action={
                <Button variant="secondary" size="dense" icon="flag">
                  {t("rules.ask")}
                </Button>
              }
            >
              {t("rules.noMatchBody")}
            </EmptyState>
          </div>
        )}
      </div>
    </div>
  );
}
