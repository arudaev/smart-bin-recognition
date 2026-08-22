import { expect, test } from "@playwright/test";

import { seedPreferences, VIEWPORTS } from "./support";

/* THE BETA MUST NOT CLAIM A DETECTOR IT DOES NOT HAVE.

   A preview went out with no VITE_DETECT_URL and no VITE_DETECT_WS. The loop
   ran against MockClient, which answers out of data/frames.ts, and the scanner
   drew archive bins over a live camera under the caption "CONNECTED ·
   DEGGENDORF" - then resolved them through the real Deggendorf pack into real
   disposal advice. A tester pointed a phone at their own floor and was told
   bin 1 was Biomüll.

   src/features/scan/demo.test.ts pins the logic and the wiring. This pins the
   thing neither of those can see: what a person reading the screen is actually
   told. It runs against `vite preview` with no endpoint configured, which is
   exactly the build that shipped. */

const SAYS_CONNECTED = /connected/i;
const SAYS_DEMO = /demo/i;

test("the strip over the camera never claims a connection to a mock", async ({ page }) => {
  await seedPreferences(page);
  await page.setViewportSize(VIEWPORTS.phone);
  await page.goto("/scan");
  await expect(page.locator("[data-testid='scan-shell']")).toBeVisible();

  const strip = page.getByRole("status").first();
  await expect(strip).toBeVisible();

  /* Settle on the loop having ANSWERED, not on a timer. The strip is "Offline"
     for the first frame - loop.ts's initial state, before the client has said
     anything - and sampling then would read a sentence that is true and miss
     the one that was not. The register naming bins is the signal that the mock
     has answered and the claim is now being made. */
  await expect(page.getByText(/in view/i).first()).toHaveText(/[1-9]\d* in view/, { timeout: 15_000 });

  const text = (await strip.textContent()) ?? "";
  expect(text, `status strip read: ${text}`).not.toMatch(SAYS_CONNECTED);
  expect(text, `status strip read: ${text}`).toMatch(SAYS_DEMO);
});

test("the sheet carries the caveat where the disposal rule is asserted", async ({ page }) => {
  await seedPreferences(page);
  await page.setViewportSize(VIEWPORTS.phone);
  await page.goto("/scan");

  const caveat = page.getByRole("note").filter({ hasText: /sample bins/i });
  await expect(caveat).toBeVisible({ timeout: 15_000 });
  await expect(caveat).toContainText(/not your camera/i);
});

test("the tablet composition carries it too, since that is the screen it shipped on", async ({ page }) => {
  await seedPreferences(page);
  await page.setViewportSize(VIEWPORTS.tablet);
  await page.goto("/scan");

  await expect(page.getByRole("note").filter({ hasText: /sample bins/i })).toBeVisible({ timeout: 15_000 });
  const text = (await page.getByRole("status").first().textContent()) ?? "";
  expect(text, `status strip read: ${text}`).not.toMatch(SAYS_CONNECTED);
});
