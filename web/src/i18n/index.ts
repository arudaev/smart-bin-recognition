import ar from "./ar.json";
import de from "./de.json";
import en from "./en.json";

/* One t() key per string. Never concatenate translated fragments – German
   compounds and Arabic agreement both break under assembly, and a fragment has
   no context for a translator.

   Interpolation is positional by name: t("desk.mapTitle", { place }).

   COVERAGE. en is complete against data/taxonomy/waste-streams.json and is
   verified by ml/scripts/validate_taxonomy.py. de and ar carry the strings the
   design produced – about 58% – and fall through to English for the rest. The
   fallback is deliberate: an English label a reader can look up beats a raw key,
   and beats a machine translation of advice about what is safe to throw where.
   `npm run check:locales` reports the gap; it is translation work, not a bug. */

export const LOCALES = ["en", "de", "ar", "tr", "uk", "ru", "es", "fr", "hi"] as const;
export type Locale = (typeof LOCALES)[number];

/** Locales with a bundle today. The rest are declared but not yet written. */
export const AVAILABLE_LOCALES: Locale[] = ["en", "de", "ar"];

export const RTL_LOCALES: Locale[] = ["ar"];

export interface LocaleMeta {
  code: Locale;
  endonym: string;
  dir: "ltr" | "rtl";
  available: boolean;
}

/* Endonyms only. No flags – a language is not a country. */
export const LOCALE_META: LocaleMeta[] = [
  { code: "en", endonym: "English", dir: "ltr", available: true },
  { code: "de", endonym: "Deutsch", dir: "ltr", available: true },
  { code: "ar", endonym: "العربية", dir: "rtl", available: true },
  { code: "tr", endonym: "Türkçe", dir: "ltr", available: false },
  { code: "uk", endonym: "Українська", dir: "ltr", available: false },
  { code: "ru", endonym: "Русский", dir: "ltr", available: false },
  { code: "es", endonym: "Español", dir: "ltr", available: false },
  { code: "fr", endonym: "Français", dir: "ltr", available: false },
  { code: "hi", endonym: "हिन्दी", dir: "ltr", available: false },
];

type Bundle = Record<string, string>;

const BUNDLES: Partial<Record<Locale, Bundle>> = { en, de, ar };

export function dirFor(locale: Locale): "ltr" | "rtl" {
  return RTL_LOCALES.includes(locale) ? "rtl" : "ltr";
}

const warned = new Set<string>();

export type Vars = Record<string, string | number>;

export function translate(locale: Locale, key: string, vars?: Vars): string {
  const bundle = BUNDLES[locale];
  let value = bundle?.[key];

  if (value === undefined) {
    value = (BUNDLES.en as Bundle)[key];
    if (value === undefined) {
      if (import.meta.env.DEV && !warned.has(key)) {
        warned.add(key);
        console.warn(`[i18n] no string for key ${key}`);
      }
      return key;
    }
    if (import.meta.env.DEV && locale !== "en") {
      const mark = locale + ":" + key;
      if (!warned.has(mark)) {
        warned.add(mark);
        console.warn(`[i18n] ${locale} falls back to en for ${key}`);
      }
    }
  }

  if (!vars) return value;
  return Object.entries(vars).reduce((acc, [k, v]) => acc.split("{" + k + "}").join(String(v)), value);
}

/**
 * Whether a string exists at all, in this locale or in English.
 *
 * For genuinely optional copy – a per-item warning that only some items have.
 * Calling translate() to find out would report a miss that is not a miss and
 * bury the real gaps in noise.
 */
export function hasString(locale: Locale, key: string): boolean {
  return BUNDLES[locale]?.[key] !== undefined || (BUNDLES.en as Bundle)[key] !== undefined;
}

/** Bind a locale once so screens read `t("scan.tapOne")`. */
export function translator(locale: Locale) {
  const t = (key: string, vars?: Vars) => translate(locale, key, vars);
  t.has = (key: string) => hasString(locale, key);
  return t;
}

export type T = ReturnType<typeof translator>;
