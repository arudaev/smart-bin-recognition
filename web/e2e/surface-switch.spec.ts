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

/* Half a toggle is worse than none. The first version navigated and did not
   remember, so the next cold launch put the machine back on the camera and the
   choice had to be made again every time - which is the complaint, not the fix.
   The preference is stored beside mode and locale, and this is the assertion
   that it survives the reload that used to undo it. */
test("the choice survives a cold launch at the root", async ({ page, context }) => {
  await seedPreferences(page);
  await page.setViewportSize(VIEWPORTS.tablet);

  await page.goto("/settings");
  await page.getByText("Open the desk view").click();
  await expect(page).toHaveURL(/\/viewer$/);

  /* A SECOND PAGE, not a reload, and the distinction is the whole test.
     `seedPreferences` installs an init script that rewrites `sbr.prefs` on every
     navigation, so reloading this page would overwrite the choice with the seed
     and then assert that the seed was honoured. A new page in the same context
     shares the origin's localStorage and carries no init script, which is what a
     cold launch from a home-screen icon actually looks like.
     "/" is the manifest's start_url, and it is the navigation that used to undo
     the choice: /viewer would have held either way, because routes.ts honours an
     explicit viewer request no matter what the probe said. */
  const cold = await context.newPage();
  await cold.setViewportSize(VIEWPORTS.tablet);
  await cold.goto("/");
  await expect(cold).toHaveURL(/\/viewer$/);

  // Not a one-way door: choosing the scanner puts the preference back on auto.
  await cold.goto("/viewer/settings");
  await cold.getByText("Open the scanner").click();
  await expect(cold).toHaveURL(/\/scan$/);

  const again = await context.newPage();
  await again.setViewportSize(VIEWPORTS.tablet);
  await again.goto("/");
  await expect(again).toHaveURL(/\/scan$/);
});
