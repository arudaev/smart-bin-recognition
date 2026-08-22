import { expect, test } from "@playwright/test";

import { BREAKPOINTS, scrollsHorizontally, seedPreferences, VIEWPORTS } from "./support";

/* The tablet bug, and the boundary it turns on.

   Before 2026-08-22 the scanner was full-bleed absolute with no max-width in the
   shell, so a 1440x960 viewport got a phone layout stretched over it: a result
   sheet 1440px wide and a camera cropped hard. There was no breakpoint to cross
   because there was no second layout to cross into.

   These assert the composition rather than a picture of it. A screenshot would
   fail on a font update and say nothing about why; `grid-template-columns`
   resolving to one track or two is the actual claim. */

/** Wait for the shell, then count the tracks of its grid.

   The wait is not politeness. Reading `gridTemplateColumns` straight after
   `goto` or a `setViewportSize` measures whatever was on screen before React
   mounted - which showed up here as a track count of -1 and as a sheet still
   at its pre-layout width. Every measurement in this file goes through here. */
async function columnCount(page: import("@playwright/test").Page): Promise<number> {
  await page.locator("[data-testid='scan-shell']").waitFor({ state: "visible" });
  return page.evaluate(() => {
    const el = document.querySelector("[data-testid='scan-shell']") as HTMLElement | null;
    if (!el) return -1;
    return getComputedStyle(el).gridTemplateColumns.split(/\s+/).filter(Boolean).length;
  });
}

/** The sheet's box, once the shell has laid out. */
async function sheetBox(page: import("@playwright/test").Page) {
  await page.locator("[data-testid='scan-shell']").waitFor({ state: "visible" });
  const sheet = await page.locator("[data-testid='scan-sheet']").boundingBox();
  const shell = await page.locator("[data-testid='scan-shell']").boundingBox();
  if (!sheet || !shell) throw new Error("the scanner shell did not lay out");
  return { sheet, shell };
}

test.beforeEach(async ({ page }) => {
  await seedPreferences(page);
});

test("stacks into one column on a phone", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.phone);
  await page.goto("/scan");
  await expect(page.locator("[data-testid='scan-shell']")).toBeVisible();

  expect(await columnCount(page)).toBe(1);
  expect(await scrollsHorizontally(page)).toBe(false);
});

test("splits into two columns on a tablet", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.tablet);
  await page.goto("/scan");
  await expect(page.locator("[data-testid='scan-shell']")).toBeVisible();

  expect(await columnCount(page)).toBe(2);
  expect(await scrollsHorizontally(page)).toBe(false);
});

test("the sheet stops spanning the whole viewport once there is room beside it", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.tablet);
  await page.goto("/scan");

  const { sheet, shell } = await sheetBox(page);

  // The regression this file exists for: 1440px of result sheet.
  expect(sheet.width).toBeLessThan(shell.width * 0.62);
  // And it is a full-height column, not a peeking drawer.
  expect(sheet.height).toBeGreaterThan(shell.height * 0.9);
});

test("desktop keeps the split rather than growing the sheet without limit", async ({ page }) => {
  await page.setViewportSize(VIEWPORTS.desktop);
  await page.goto("/scan");

  expect(await columnCount(page)).toBe(2);
  const { sheet } = await sheetBox(page);
  // --desk-panel is 400px; minmax(360px, 400px) must not run away on a wide screen.
  expect(sheet.width).toBeLessThanOrEqual(420);
});

/* The token layer defines exactly two boundaries - 880 and 1100 - and the
   scanner turns on 1100. Both sides of both, because an off-by-one in a media
   query is invisible until somebody has that exact window width. */
for (const [name, edge] of Object.entries(BREAKPOINTS)) {
  test(`the ${name} boundary at ${edge} behaves the same on both sides`, async ({ page }) => {
    await page.setViewportSize({ width: edge - 1, height: 900 });
    await page.goto("/scan");
    const below = await columnCount(page);
    const belowScrolls = await scrollsHorizontally(page);

    await page.setViewportSize({ width: edge, height: 900 });
    const at = await columnCount(page);

    if (edge === BREAKPOINTS.wide) {
      // 1100 is the scanner's own breakpoint: `max-width: 1100px` still matches
      // AT 1100, so the split appears at 1101 and not before.
      expect(below).toBe(1);
      expect(at).toBe(1);
      await page.setViewportSize({ width: edge + 1, height: 900 });
      expect(await columnCount(page)).toBe(2);
    } else {
      // 880 is the viewer's rail breakpoint; the scanner must not move on it.
      expect(below).toBe(at);
    }
    expect(belowScrolls).toBe(false);
    expect(await scrollsHorizontally(page)).toBe(false);
  });
}
