import { expect, test } from "@playwright/test";

import { seedPreferences, VIEWPORTS } from "./support";

/* Browser smoke for the camera path, and NO MORE THAN THAT.

   Chromium's `--use-fake-device-for-media-stream` supplies ONE unlabelled
   device. The Surface Pro 11 bug is about a machine with TWO cameras, neither
   reporting `facingMode`, distinguishable only by labels that appear after
   permission is granted - which this flag cannot reproduce. That fallback is
   covered in `src/capture/camera.test.ts` against an injected MediaDevices, and
   the claim this repository makes about it is bounded accordingly: implemented
   and browser-tested, hardware confirmation on a real Surface still pending.

   What these DO establish is that the capability probe and the capture module
   run in a real engine against a real getUserMedia, which vitest cannot show. */

test("the capability probe runs and picks a surface without throwing", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await seedPreferences(page);
  await page.setViewportSize(VIEWPORTS.phone);
  await page.goto("/scan");
  await expect(page.locator("[data-testid='scan-shell']")).toBeVisible();

  expect(errors).toEqual([]);
});

test("getUserMedia is reachable and returns a video track", async ({ page }) => {
  await seedPreferences(page);
  await page.goto("/scan");

  const track = await page.evaluate(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    const t = stream.getVideoTracks()[0];
    const settings = t.getSettings();
    stream.getTracks().forEach((x) => x.stop());
    return { label: t.label, hasFacing: "facingMode" in settings };
  });

  expect(track).not.toBeNull();
});

test("enumerateDevices is available, which is what the rear-camera fallback needs", async ({ page }) => {
  await seedPreferences(page);
  await page.goto("/scan");

  const kinds = await page.evaluate(async () => {
    await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    return (await navigator.mediaDevices.enumerateDevices()).map((d) => d.kind);
  });

  expect(kinds).toContain("videoinput");
});
