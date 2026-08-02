import { ItemRule, RuleGroup } from "@/components";
import { rulesFor } from "@/data/taxonomy";
import type { T } from "@/i18n";

/* Rules, grouped: the verdict is said in words once, and the marks confirm it.
   A flat list of eight mixed rows makes every row carry its own verdict; the
   heading takes that job instead, so no row depends on its glyph alone. */

export function RulesList({ stream, t }: { stream: string; t: T }) {
  const r = rulesFor(stream);
  if (!r.yes.length && !r.no.length && !r.watch.length) return null;

  return (
    <div style={{ display: "grid", gap: "var(--space-5)" }}>
      {r.yes.length ? (
        <RuleGroup verdict="yes" heading={t("answer.whatGoes")}>
          {r.yes.map((i) => (
            <ItemRule key={i} verdict="yes" verdictLabel={t("answer.yes")}>
              {t(`item.${i}`)}
            </ItemRule>
          ))}
        </RuleGroup>
      ) : null}

      {r.no.length ? (
        <RuleGroup verdict="no" heading={t("answer.whatNot")}>
          {r.no.map((i) => (
            <ItemRule key={i} verdict="no" verdictLabel={t("answer.no")}>
              {t(`item.${i}`)}
            </ItemRule>
          ))}
        </RuleGroup>
      ) : null}

      {r.watch.length ? (
        <RuleGroup verdict="watch" heading={t("answer.watch")}>
          {r.watch.map((i) => (
            <ItemRule key={i} verdict="watch" verdictLabel={t("answer.careful")} note={noteFor(i, t)}>
              {t(`item.${i}`)}
            </ItemRule>
          ))}
        </RuleGroup>
      ) : null}
    </div>
  );
}

/* Per-item warnings exist only for the mistakes worth explaining, so a missing
   one is normal rather than a gap. Asked with `has` instead of by translating
   and comparing, which would log every intentional absence as a fault. */
function noteFor(item: string, t: T): string | undefined {
  const key = `note.${item}`;
  return t.has(key) ? t(key) : undefined;
}
