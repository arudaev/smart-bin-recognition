import { test } from "@playwright/test";

import { seedPreferences, VIEWPORTS } from "./support";

/* Not an assertion - a deliverable. Run with `npm run test:e2e:shots` to
   regenerate the images the tablet-composition change is reported with. Kept out
   of the default run by its own grep tag so CI does not spend time drawing
   pictures nobody reads. */
const CASES = [
  { name: "phone-paper", vp: VIEWPORTS.phone, mode: "paper" as const, locale: "en" },
  { name: "tablet-paper", vp: VIEWPORTS.tablet, mode: "paper" as const, locale: "en" },
  { name: "tablet-night", vp: VIEWPORTS.tablet, mode: "night" as const, locale: "en" },
  { name: "tablet-rtl", vp: VIEWPORTS.tablet, mode: "paper" as const, locale: "ar" },
  { name: "desktop-paper", vp: VIEWPORTS.desktop, mode: "paper" as const, locale: "en" },
];

for (const c of CASES) {
  test(`@shot ${c.name}`, async ({ page }) => {
    await seedPreferences(page, { mode: c.mode, locale: c.locale });
    await page.setViewportSize(c.vp);
    await page.goto("/scan");
    await page.locator("[data-testid='scan-shell']").waitFor({ state: "visible" });
    await page.waitForTimeout(600); // the sheet's block-size transition
    await page.screenshot({ path: `e2e/__screenshots__/scanner-${c.name}.png` });
  });
}
