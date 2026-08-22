import { expect, test } from "@playwright/test";

import { documentState, scrollsHorizontally, seedPreferences, VIEWPORTS } from "./support";

/* The theme goes on <html> and nowhere else - `app/theme.ts` is the only thing
   that writes it - so <html> is the whole assertion surface. Arabic is a launch
   locale, which makes `dir` a correctness property rather than a nicety. */

test("night mode reaches the document element, not a wrapper", async ({ page }) => {
  await seedPreferences(page, { mode: "night" });
  await page.setViewportSize(VIEWPORTS.tablet);
  await page.goto("/scan");
  await expect(page.locator("[data-testid='scan-shell']")).toBeVisible();

  const state = await documentState(page);
  expect(state.theme).toBe("night");

  // The mode has to actually change what is painted. A token layer wired to the
  // wrong element leaves data-theme correct and the colours untouched, which is
  // the failure worth catching.
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).not.toBe("rgba(0, 0, 0, 0)");
});

test("paper and night paint different backgrounds", async ({ page, context }) => {
  const read = async (mode: "paper" | "night") => {
    const p = await context.newPage();
    await p.addInitScript(
      ([k, v]) => window.localStorage.setItem(k as string, v as string),
      ["sbr.prefs", JSON.stringify({ mode, locale: "en", onboarded: true })],
    );
    await p.goto("/scan");
    await p.locator("[data-testid='scan-shell']").waitFor({ state: "visible" });
    const bg = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await p.close();
    return bg;
  };
  expect(await read("paper")).not.toBe(await read("night"));
  await page.close();
});

test("Arabic mirrors the document and still does not scroll sideways", async ({ page }) => {
  await seedPreferences(page, { locale: "ar" });
  await page.setViewportSize(VIEWPORTS.tablet);
  await page.goto("/scan");
  await expect(page.locator("[data-testid='scan-shell']")).toBeVisible();

  const state = await documentState(page);
  expect(state.dir).toBe("rtl");
  expect(state.lang).toBe("ar");
  expect(await scrollsHorizontally(page)).toBe(false);
});

test("the sheet sits on the opposite side under RTL", async ({ page }) => {
  /* The reason logical properties are not negotiable in this repository. Under
     `dir=rtl` the second grid column is drawn at the inline end, which is the
     LEFT of the viewport - so a sheet written with `left`/`right` would stay put
     and overlap the camera. */
  await seedPreferences(page, { locale: "ar" });
  await page.setViewportSize(VIEWPORTS.tablet);
  await page.goto("/scan");
  const rtl = await page.locator("[data-testid='scan-sheet']").boundingBox();

  await seedPreferences(page, { locale: "en" });
  await page.goto("/scan");
  await page.locator("[data-testid='scan-shell']").waitFor({ state: "visible" });
  const ltr = await page.locator("[data-testid='scan-sheet']").boundingBox();

  expect(rtl).not.toBeNull();
  expect(ltr).not.toBeNull();
  expect(rtl!.x).toBeLessThan(ltr!.x);
  expect(rtl!.x).toBeLessThan(100);
});
