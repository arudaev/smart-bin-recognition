import { describe, expect, it } from "vitest";

import type { Locale } from "@/i18n";
import type { AttributeTarget, Mode } from "./theme";
import { MODES, applyDocumentTheme, documentTheme } from "./theme";

/* The theme belongs to <html>, and these are the things about that which fail
   silently: a mode written to the wrong element, paper written as a value
   instead of an absence, and – the one that cost a review – a theme-colour
   written to the first of two metas while the browser honours the other. */

interface Fake extends AttributeTarget {
  attributes: Record<string, string>;
  removed: string[];
}

function fake(): Fake {
  const node: Fake = {
    attributes: {},
    removed: [],
    setAttribute(name, value) {
      node.attributes[name] = value;
    },
    removeAttribute(name) {
      node.removed.push(name);
      delete node.attributes[name];
    },
  };
  return node;
}

describe("documentTheme", () => {
  it("says paper by removing the attribute, not by naming it", () => {
    // tokens/modes.css defines sun and night as overrides on an unset root.
    // data-theme="paper" would match nothing and quietly do nothing.
    expect(documentTheme("paper", "en").theme).toBeNull();
  });

  it("names the two modes that are overrides", () => {
    expect(documentTheme("sun", "en").theme).toBe("sun");
    expect(documentTheme("night", "en").theme).toBe("night");
  });

  it("takes direction from the locale", () => {
    expect(documentTheme("paper", "ar").dir).toBe("rtl");
    expect(documentTheme("paper", "de").dir).toBe("ltr");
    expect(documentTheme("night", "en").dir).toBe("ltr");
  });

  it("carries the locale as lang, which is what drives the font stack", () => {
    for (const locale of ["en", "de", "ar"] as Locale[]) {
      expect(documentTheme("sun", locale).lang).toBe(locale);
    }
  });
});

describe("applyDocumentTheme", () => {
  it("writes the mode, the direction and the language to the root", () => {
    const root = fake();
    applyDocumentTheme(root, [], "night", "ar");
    expect(root.attributes).toEqual({ "data-theme": "night", dir: "rtl", lang: "ar" });
  });

  it("removes data-theme for paper rather than leaving the last mode behind", () => {
    const root = fake();
    applyDocumentTheme(root, [], "night", "en");
    applyDocumentTheme(root, [], "paper", "en");
    expect(root.attributes["data-theme"]).toBeUndefined();
    expect(root.removed).toContain("data-theme");
    // dir and lang are still there: paper is a mode, not a reset.
    expect(root.attributes.dir).toBe("ltr");
    expect(root.attributes.lang).toBe("en");
  });

  it("touches nothing on the root but those three attributes", () => {
    const root = fake();
    applyDocumentTheme(root, [], "sun", "de", () => "#ffffff");
    expect(Object.keys(root.attributes).sort()).toEqual(["data-theme", "dir", "lang"]);
  });

  it("writes the theme colour to every meta, not just the first", () => {
    /* index.html declares two meta[name=theme-color], scoped to
       prefers-color-scheme light and dark, and the browser honours the first
       whose media matches. Writing one means the mode changes and the browser
       chrome does not, on whichever system preference selects the other. */
    const light = fake();
    const dark = fake();
    applyDocumentTheme(fake(), [light, dark], "night", "en", () => "#14171b");
    expect(light.attributes.content).toBe("#14171b");
    expect(dark.attributes.content).toBe("#14171b");
  });

  it("trims what the cascade returns", () => {
    // getPropertyValue keeps the whitespace from the declaration.
    const meta = fake();
    applyDocumentTheme(fake(), [meta], "paper", "en", () => " #5b2e91 ");
    expect(meta.attributes.content).toBe("#5b2e91");
  });

  it("leaves the metas alone when the cascade has not resolved yet", () => {
    /* The dev server injects styles through JavaScript, so a read on the boot
       path can come back empty. An empty content attribute is worse than the
       static default already in the document. */
    const meta = fake();
    applyDocumentTheme(fake(), [meta], "night", "en", () => "");
    expect(meta.attributes.content).toBeUndefined();
  });

  it("reads the colour only after the mode has landed", () => {
    // Otherwise the cascade answers for the mode being replaced.
    const root = fake();
    let themeWhenRead: string | undefined;
    applyDocumentTheme(root, [fake()], "sun", "en", () => {
      themeWhenRead = root.attributes["data-theme"];
      return "#ffffff";
    });
    expect(themeWhenRead).toBe("sun");
  });

  it("returns what it applied, for every mode", () => {
    for (const mode of MODES as Mode[]) {
      const applied = applyDocumentTheme(fake(), [], mode, "en");
      expect(applied).toEqual(documentTheme(mode, "en"));
    }
  });
});
