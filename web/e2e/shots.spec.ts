import { test } from "@playwright/test";

import { seedPreferences, VIEWPORTS } from "./support";

/* Not an assertion - a deliverable. Run with `npm run test:e2e:shots` to
   regenerate the images the tablet composition is reported with.

   SKIPPED unless SBR_SHOTS is set, which `test:e2e:shots` does. An earlier
   version relied on a `@shot` name tag and nothing filtered on it, so CI
   regenerated five PNGs on every run and would have reported a diff as a
   failure the first time a font shifted by a pixel. A screenshot is evidence for
   a human, not a gate. */
test.skip(!process.env.SBR_SHOTS, "screenshots are a deliverable, not a gate - set SBR_SHOTS to regenerate");
const CASES = [
  { name: "phone-paper", vp: VIEWPORTS.phone, mode: "paper" as const, locale: "en" },
  { name: "tablet-paper", vp: VIEWPORTS.tablet, mode: "paper" as const, locale: "en" },
  { name: "tablet-night", vp: VIEWPORTS.tablet, mode: "night" as const, locale: "en" },
  { name: "tablet-rtl", vp: VIEWPORTS.tablet, mode: "paper" as const, locale: "ar" },
  { name: "desktop-paper", vp: VIEWPORTS.desktop, mode: "paper" as const, locale: "en" },
];

for (const c of CASES) {
  test(`shot: ${c.name}`, async ({ page }) => {
    await seedPreferences(page, { mode: c.mode, locale: c.locale });
    await page.setViewportSize(c.vp);
    await page.goto("/scan");
    await page.locator("[data-testid='scan-shell']").waitFor({ state: "visible" });
    /* Wait for the loop to have ANSWERED, not for a guessed number of
       milliseconds. 600 ms was short of the mock's first frame, so the shots
       were of an empty sheet mid-transition - a picture of the wrong moment.
       The marker is what the register counts, and unlike the register's own
       words it is the same in every locale: `/in view/` matched nothing in the
       Arabic shot and spent the whole 30 s test budget failing to. Soft and
       short-fused, because a shot is a deliverable and must not fail a run. */
    await page
      .locator("[data-testid='scan-shell'] button")
      .first()
      .waitFor({ state: "visible", timeout: 8_000 })
      .catch(() => {});
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `e2e/__screenshots__/scanner-${c.name}.png` });
  });
}
