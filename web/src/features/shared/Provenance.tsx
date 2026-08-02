import { ColorQuote, Notice, Tag } from "@/components";
import type { Region } from "@/data/regions";
import { REGION_PLACE } from "@/data/regions";
import type { T } from "@/i18n";

/* Coverage has three states, not two, and draft is the one every new city
   passes through. It is expressed cheaply: an outlined tag in the register
   voice, plus one plain sentence naming the operator whose guidance has NOT
   yet been checked. Published carries the same sentence with a retrieval date
   instead. No pack says plainly that the mapping to local containers is the
   part nobody has written down. */

export function Provenance({ region, t }: { region: Region; t: T }) {
  const place = REGION_PLACE[region.key];

  if (region.key === "none") {
    return (
      <Notice tone="attention" icon="circle-question-mark" title={t("rules.noPackTitle", { place })}>
        {t("rules.noPackBody", { place })}
      </Notice>
    );
  }

  if (region.key === "draft") {
    return (
      <Notice tone="attention" icon="info" title={t("coverage.draftTitle", { place })}>
        {t("coverage.draftBody", { source: region.operator ?? "" })}
      </Notice>
    );
  }

  return (
    <Notice tone="quiet" icon="shield-check" title={region.operator ?? ""}>
      {t("coverage.publishedBody", {
        source: region.operator ?? "",
        checked: region.checkedKey ? t(region.checkedKey) : "",
      })}
    </Notice>
  );
}

export function CoverageTag({ region, t }: { region: Region; t: T }) {
  if (region.key === "none") return <Tag icon="circle-question-mark">{REGION_PLACE[region.key]}</Tag>;
  if (region.key === "draft")
    return (
      <Tag variant="outline" icon="triangle-alert">
        {t("ui.draft")}
      </Tag>
    );
  return (
    <Tag variant="solid" icon="check">
      {t("ui.published")}
    </Tag>
  );
}

/* Quoted colour. Only ever quoted, and only when a single bin is open – never
   across a list. Quoting is for confirmation, not for browsing. */
export function Quoted({
  colors,
  t,
  size = "sm",
}: {
  colors: { color: string; part?: string }[];
  t: T;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2) var(--space-5)" }}>
      {colors.map((c, i) => (
        <ColorQuote
          key={c.color + i}
          color={c.color}
          label={t(`color.${c.color}`)}
          part={c.part ? t(`part.${c.part}`) : undefined}
          size={size}
        />
      ))}
    </div>
  );
}
