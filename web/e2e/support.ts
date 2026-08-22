import type { Page } from "@playwright/test";

/* Shared setup. Kept small on purpose: a helper that hides what a spec is doing
   makes a layout failure harder to read, not easier. */

/** The two boundaries the token layer actually defines. */
export const BREAKPOINTS = { narrow: 880, wide: 1100 } as const;

export const VIEWPORTS = {
  phone: { width: 390, height: 844 },
  tablet: { width: 1440, height: 960 },
  desktop: { width: 1920, height: 1080 },
} as const;

/** Seed preferences before the app boots.

   `app/preferences.ts` reads `sbr.prefs` at the top of main.tsx, before
   `createRoot().render()`, so this has to land as an init script rather than as
   a `localStorage.setItem` after navigation - otherwise the first paint is in
   the wrong locale and the theme flips under the assertion. */
export async function seedPreferences(
  page: Page,
  prefs: { mode?: "paper" | "sun" | "night"; locale?: string; onboarded?: boolean; surface?: "auto" | "scanner" | "viewer" } = {},
): Promise<void> {
  const value = JSON.stringify({ mode: "paper", locale: "en", onboarded: true, surface: "auto", ...prefs });
  await page.addInitScript(
    ([key, json]) => window.localStorage.setItem(key as string, json as string),
    ["sbr.prefs", value],
  );
}

/** What `app/theme.ts` wrote onto <html>. The theme lives there and nowhere
    else, so this is the whole of the assertion surface for theming. */
export async function documentState(page: Page): Promise<{ theme: string | null; dir: string | null; lang: string | null }> {
  return page.evaluate(() => ({
    theme: document.documentElement.getAttribute("data-theme"),
    dir: document.documentElement.getAttribute("dir"),
    lang: document.documentElement.getAttribute("lang"),
  }));
}

/** Whether the page scrolls sideways. A horizontal scrollbar on a viewport the
    design claims to support is the single cheapest signal that a layout has been
    given no idea what a large screen is. */
export async function scrollsHorizontally(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
}
