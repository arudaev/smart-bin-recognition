import { defineConfig, devices } from "@playwright/test";

/* A browser runner, scoped to what actually broke.

   Two bugs reached this repository by somebody looking at a screen - the Surface
   opening its selfie camera, and the scanner drawn as a phone on a 1440-wide
   tablet - and neither was reachable from vitest, which has no layout. This
   config exists to make that class of bug catchable without a person and a
   device.

   It is deliberately NOT a general testing strategy. The unit suite is 281 tests
   and stays the place for logic; these specs assert only things that need a real
   engine: computed layout at the token layer's own breakpoints, direction and
   theme on <html>, and the camera path's browser plumbing.

   Chromium only. The bugs were Chromium bugs (Edge and Chrome on Windows), a
   second engine would double the CI minutes for coverage nobody has asked for,
   and adding WebKit here would imply a claim about Safari that nothing has
   tested.

   `preview`, not `dev`. A production build is what the service worker registers
   against and what check-bundle.mjs measures, so it is the artefact worth
   asserting on. */
export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e/.artifacts",
  snapshotDir: "./e2e/__screenshots__",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],

  use: {
    // `localhost`, NOT `127.0.0.1`. `vite preview` binds the hostname it is
    // given, and on a machine where `localhost` resolves to ::1 first the two
    // are different addresses: curl to 127.0.0.1 gets nothing while localhost
    // gets 200. Pointing the runner at the literal v4 address makes webServer
    // wait out its whole timeout for a server that is already up.
    baseURL: "http://localhost:4173",
    trace: "on-first-retry",
    // Screenshots are for the two specs where layout IS the question. Everywhere
    // else the accessibility tree is asserted instead: it is faster, it does not
    // rot on a font update, and a failure names what changed instead of showing
    // two pictures.
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: [
            // Lets getUserMedia resolve without hardware. NOTE: this gives ONE
            // unlabelled device, so it cannot reproduce the Surface's two named
            // cameras - that fallback is covered in src/capture/camera.test.ts
            // against an injected MediaDevices. Here it only proves the camera
            // path runs in a real browser.
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
          ],
        },
      },
    },
  ],

  webServer: {
    command: "npm run build && npm run preview -- --port 4173 --strictPort",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
