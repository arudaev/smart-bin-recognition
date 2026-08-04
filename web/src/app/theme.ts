import type { Locale } from "@/i18n";
import { dirFor } from "@/i18n";

/* THE THEME LIVES ON <html>.
 *
 * Not on a div inside the app. The browser reads the document element for the
 * things the app does not draw: the scrollbar, the overscroll gutter past the
 * end of a list, the background behind a rubber-band bounce, and the form
 * controls the platform renders itself. A theme set one element lower leaves
 * every one of those in paper mode while the page is in night, which is most
 * visible in exactly the place this product is used – a phone, at night,
 * scrolling a rules list past its end.
 *
 * `dir` and `lang` belong on the same element for the same reason. `lang`
 * drives the font stack and the platform's own hyphenation; `dir` has to be
 * outside everything it mirrors.
 */

export type Mode = "paper" | "sun" | "night";

export const MODES: Mode[] = ["paper", "sun", "night"];

export interface DocumentTheme {
  /** null is paper. Paper removes the attribute rather than naming itself:
   *  tokens/modes.css defines sun and night as overrides on an unset root. */
  theme: Exclude<Mode, "paper"> | null;
  dir: "ltr" | "rtl";
  lang: Locale;
}

export function documentTheme(mode: Mode, locale: Locale): DocumentTheme {
  return { theme: mode === "paper" ? null : mode, dir: dirFor(locale), lang: locale };
}

/** Whatever can carry an attribute. Duck-typed so a test needs no DOM. */
export interface AttributeTarget {
  setAttribute(name: string, value: string): void;
  removeAttribute(name: string): void;
}

/**
 * Write the theme onto a root element and the theme-colour metas.
 *
 * `metas` is a list, and every one of them is written. index.html declares two
 * `meta[name="theme-color"]`, scoped to `prefers-color-scheme: light` and
 * `dark`, and the browser honours the first whose media matches. Setting one
 * would mean the mode changed and the browser chrome did not, on whichever
 * system preference happened to select the other. The pair stays as the
 * pre-mount default and agrees from here on.
 *
 * The colour is read through a callback rather than computed here, because its
 * value is a token – `--theme-color` in tokens/color.css and tokens/modes.css –
 * and reading it means asking the platform what the cascade resolved to.
 */
export function applyDocumentTheme(
  root: AttributeTarget,
  metas: Iterable<AttributeTarget>,
  mode: Mode,
  locale: Locale,
  readThemeColor?: () => string,
): DocumentTheme {
  const applied = documentTheme(mode, locale);

  if (applied.theme === null) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", applied.theme);
  root.setAttribute("dir", applied.dir);
  root.setAttribute("lang", applied.lang);

  // Read after the attributes land, or the cascade answers for the old mode.
  const color = readThemeColor?.().trim();
  if (color) {
    for (const meta of metas) meta.setAttribute("content", color);
  }

  return applied;
}

/** The same thing against a real document. Called before mount and on change. */
export function applyThemeToDocument(mode: Mode, locale: Locale, doc: Document = document): DocumentTheme {
  const root = doc.documentElement;
  return applyDocumentTheme(root, doc.querySelectorAll('meta[name="theme-color"]'), mode, locale, () =>
    getComputedStyle(root).getPropertyValue("--theme-color"),
  );
}
