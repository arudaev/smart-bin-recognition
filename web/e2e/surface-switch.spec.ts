import { expect, test } from "@playwright/test";

import { seedPreferences, VIEWPORTS } from "./support";

/* A SURFACE YOU CANNOT LEAVE.

   `routes.ts` has always honoured an explicit request for the other surface -
   "a scanner-tier device asking for the viewer gets the viewer" - but nothing
   outside features/desk/ ever mentioned /viewer, so the only way across was to
   type a URL. On a Surface Pro, which has two cameras and is therefore a
   scanner by the capability probe, that meant being locked onto a camera the
   device cannot usefully be pointed with.

   The pair of rows in settings is the affordance. It changes nothing about
   where a device LANDS - `surfaceFor` still decides that from the probe alone.

   Both directions are asserted in one test on purpose: a one-way door is worse
   than no door, and the way that regresses is somebody removing one row. */

test("settings offers the other surface, and offers the way back", async ({ page }) => {
  await seedPreferences(page);
  await page.setViewportSize(VIEWPORTS.tablet);

  await page.goto("/settings");
  await page.getByText("Open the desk view").click();
  await expect(page).toHaveURL(/\/viewer$/);

  await page.goto("/viewer/settings");
  await page.getByText("Open the scanner").click();
  await expect(page).toHaveURL(/\/scan$/);
});
