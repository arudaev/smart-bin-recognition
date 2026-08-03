import { readFileSync, readdirSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import ar from "./ar.json";
import de from "./de.json";
import en from "./en.json";
import { AVAILABLE_LOCALES, LOCALE_META, LOCALES, dirFor, hasString, translate, translator } from ".";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");

const BUNDLES: Record<string, Record<string, string>> = { en, de, ar };

/* The copy rules in the design system's §2 are not decoration – they are what
   makes a stressed reader in their second language able to use this. Several of
   them are mechanically checkable, so they are checked here rather than
   remembered. */

describe("the bundles", () => {
  it("has a bundle for every locale it says is available", () => {
    for (const locale of AVAILABLE_LOCALES) {
      expect(BUNDLES[locale], `no bundle for ${locale}`).toBeDefined();
    }
  });

  it("declares every locale in LOCALES exactly once in LOCALE_META", () => {
    expect(LOCALE_META.map((l) => l.code).sort()).toEqual([...LOCALES].sort());
  });

  it("marks Arabic right to left and nothing else", () => {
    expect(dirFor("ar")).toBe("rtl");
    for (const locale of LOCALES.filter((l) => l !== "ar")) {
      expect(dirFor(locale)).toBe("ltr");
    }
  });

  it("has no key in a translation that English does not have", () => {
    // An orphan is a string nobody can ever see: the fallback path only ever
    // consults English, so a de-only key is dead weight and usually a typo.
    for (const locale of ["de", "ar"]) {
      const orphans = Object.keys(BUNDLES[locale]).filter((key) => !(key in en));
      expect(orphans, `${locale} has keys English does not`).toEqual([]);
    }
  });

  it("has no empty string, which would render as a silently missing label", () => {
    for (const [locale, bundle] of Object.entries(BUNDLES)) {
      const blank = Object.entries(bundle)
        .filter(([, value]) => value.trim() === "")
        .map(([key]) => key);
      expect(blank, `${locale} has blank values`).toEqual([]);
    }
  });

  it("keeps every interpolation a translation uses present in the English it came from", () => {
    // t("desk.mapTitle", { place }) fills {place}. A translation that invented
    // {ort} would render the braces to the user.
    const placeholders = (value: string) => (value.match(/\{[a-zA-Z]+\}/g) ?? []).sort();
    for (const locale of ["de", "ar"]) {
      for (const [key, value] of Object.entries(BUNDLES[locale])) {
        expect(placeholders(value), `${locale}:${key}`).toEqual(placeholders(en[key as keyof typeof en]));
      }
    }
  });
});

describe("the voice", () => {
  it("uses no exclamation marks, anywhere, ever", () => {
    for (const [locale, bundle] of Object.entries(BUNDLES)) {
      const shouting = Object.entries(bundle)
        .filter(([, value]) => value.includes("!") || value.includes("！"))
        .map(([key]) => key);
      expect(shouting, `${locale} raises its voice`).toEqual([]);
    }
  });

  it("uses en dashes, never em dashes – except in Arabic, which has its own", () => {
    for (const locale of ["en", "de"]) {
      const emDashes = Object.entries(BUNDLES[locale])
        .filter(([, value]) => value.includes("—"))
        .map(([key]) => key);
      expect(emDashes, `${locale} uses an em dash`).toEqual([]);
    }
  });

  it("never says model, inference, confidence score, class or detection to a user", () => {
    // The design system's banned vocabulary. Nothing on screen explains how the
    // recognition works, because knowing how it works is not the user's job.
    const banned = /\b(model|inference|confidence score|classifier|detection)\b/i;
    const leaks = Object.entries(en)
      .filter(([, value]) => banned.test(value))
      .map(([key]) => key);
    expect(leaks).toEqual([]);
  });
});

describe("translate", () => {
  it("returns the string for a locale that has it", () => {
    expect(translate("de", "ui.back")).toBe(de["ui.back" as keyof typeof de]);
  });

  it("falls back to English rather than showing a raw key", () => {
    // An English label a reader can look up beats a key, and beats a machine
    // translation of advice about what is safe to throw where.
    const onlyEnglish = Object.keys(en).find((key) => !(key in de))!;
    expect(translate("de", onlyEnglish)).toBe(en[onlyEnglish as keyof typeof en]);
  });

  it("returns the key itself when nothing has it, so the gap is visible", () => {
    expect(translate("en", "nope.not.a.key")).toBe("nope.not.a.key");
  });

  it("interpolates by name and leaves other braces alone", () => {
    expect(translate("en", "desk.mapTitle", { place: "Deggendorf" })).toContain("Deggendorf");
    expect(translate("en", "desk.mapTitle", { place: "Deggendorf" })).not.toContain("{place}");
  });

  it("replaces every occurrence of a placeholder", () => {
    // German and Arabic word order both put a placeholder in a different place,
    // and one string repeats it.
    const value = translate("en", "firstRun.coverage", { n: 41, place: "Deggendorf" });
    expect(value).not.toMatch(/\{n\}|\{place\}/);
  });
});

describe("hasString", () => {
  it("distinguishes an intentional absence from a gap", () => {
    // Used for genuinely optional copy, like a per-item warning only some items
    // have. Calling translate() to find out would log a miss that is not one.
    expect(hasString("en", "ui.back")).toBe(true);
    expect(hasString("ar", "ui.back")).toBe(true);
    expect(hasString("en", "item.thing-that-does-not-exist")).toBe(false);
  });
});

describe("translator", () => {
  it("binds a locale once, so screens read t(\"scan.tapOne\")", () => {
    const t = translator("de");
    expect(t("ui.back")).toBe(de["ui.back" as keyof typeof de]);
    expect(t.has("ui.back")).toBe(true);
  });
});

/* ---- keys the screens actually ask for ---------------------------------- */

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "test" || entry.name === "dev") continue;
      out.push(...sources(full));
    } else if ([".ts", ".tsx"].includes(extname(entry.name)) && !entry.name.endsWith(".test.ts")) {
      out.push(full);
    }
  }
  return out;
}

describe("keys used in the source", () => {
  it("all exist in English", () => {
    // Only literal t("…") calls; the dynamic ones – t(`stream.${id}`) – are
    // covered by the taxonomy validator on the Python side, which knows the
    // full set of stream and item ids.
    const missing = new Set<string>();
    for (const file of sources(SRC)) {
      const text = readFileSync(file, "utf8");
      for (const match of text.matchAll(/\bt\(\s*"([a-zA-Z][\w.]*)"/g)) {
        if (!(match[1] in en)) missing.add(`${match[1]} (${file.slice(SRC.length + 1)})`);
      }
    }
    expect([...missing]).toEqual([]);
  });
});
