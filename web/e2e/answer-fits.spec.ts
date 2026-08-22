import { expect, test } from "@playwright/test";

import { seedPreferences } from "./support";

/* AN ANSWER THAT DOES NOT FIT ON THE SCREEN IS NOT AN ANSWER.
 *
 * Opening a bin's answer made the sheet as tall as its own content - 1745px
 * inside an 844px window - and two things followed. The sheet is anchored to the
 * block end, so its header went off the top of the screen; and `overflow-y:
 * auto` never engaged, because the scrolling box was bigger than the thing it
 * was meant to scroll. Side by side it was worse: the sheet stretched the grid's
 * implicit `auto` row, and the camera - centred against that row - slid up to
 * 477px down the screen every time somebody tapped a bin.
 *
 * Two causes, both the shape CONVENTIONS already names for the inline axis: an
 * `auto` track plus a content-sized child removes the maximum. The third was a
 * custom property that could never have worked (tokens/space.css, .sbr-scan-sheet).
 *
 * The assertions below are deliberately about GEOMETRY rather than about which
 * fix is in place. Any future layout that keeps the answer on the screen and
 * scrollable passes; any that does not, fails.
 */

const VIEWPORTS = [
  { name: "phone", width: 390, height: 844 },
  { name: "phone-landscape", width: 844, height: 390 },
  { name: "ipad-portrait", width: 768, height: 1024 },
  { name: "surface-ish", width: 1366, height: 768 },
  { name: "tablet-wide", width: 1440, height: 960 },
  { name: "desktop", width: 1920, height: 1080 },
];

/** The sheet, the box inside it that is supposed to scroll, and the camera. */
async function geometry(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const shell = document.querySelector("[data-testid='scan-shell']") as HTMLElement;
    const sheet = document.querySelector("[data-testid='scan-sheet']") as HTMLElement;
    const body = sheet.querySelector("section > div:last-child") as HTMLElement;
    const media = shell.firstElementChild!.firstElementChild as HTMLElement;
    const box = (el: HTMLElement) => {
      const r = el.getBoundingClientRect();
      return { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height) };
    };
    return {
      sheet: box(sheet),
      mediaTop: Math.round(media.getBoundingClientRect().top),
      body: { ...box(body), scrollHeight: body.scrollHeight, clientHeight: body.clientHeight },
      viewportHeight: window.innerHeight,
    };
  });
}

for (const vp of VIEWPORTS) {
  test(`${vp.name} ${vp.width}x${vp.height}: the answer stays on screen and scrolls`, async ({ page }) => {
    await seedPreferences(page);
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto("/scan");
    await page
      .getByText(/[1-9]\d* in view/)
      .first()
      .waitFor({ timeout: 15_000 });

    const before = await geometry(page);

    await page.locator("[data-testid='scan-sheet'] button").filter({ hasText: /Everything else/ }).first().click();
    // The sheet animates its own block-size; settle before measuring.
    await page.waitForTimeout(900);

    const after = await geometry(page);

    // 1. The sheet is inside the window. Its top going negative is how the
    //    register, the title and the close button left the screen.
    expect(after.sheet.top, "the sheet's top is above the viewport").toBeGreaterThanOrEqual(-1);
    expect(after.sheet.height, "the sheet is taller than the window").toBeLessThanOrEqual(after.viewportHeight + 1);

    // 2. Content longer than the box scrolls INSIDE the box. The answer panel
    //    for a Restmüll bin is long at every viewport here, so this is the
    //    honest form of the assertion rather than a conditional one.
    expect(after.body.scrollHeight, "the answer is not longer than its box - is the fixture still long?").toBeGreaterThan(
      after.body.clientHeight,
    );
    expect(after.body.clientHeight, "the scrolling box is taller than the window").toBeLessThanOrEqual(
      after.viewportHeight + 1,
    );

    // 3. Side by side, opening an answer must not move the camera. Stacked, the
    //    sheet rising over the frame is the design, so the camera is allowed to
    //    stay exactly where it is - which it also does.
    expect(after.mediaTop, "opening an answer moved the camera").toBe(before.mediaTop);
  });
}
