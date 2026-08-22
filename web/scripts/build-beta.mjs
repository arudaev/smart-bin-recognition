#!/usr/bin/env node
/* A production-shaped build that KEEPS the beta instrumentation.
 *
 *     npm run build:beta
 *
 * On Vercel nobody runs this: `vite.config.ts` reads `VERCEL_ENV`, which Vercel
 * sets to "preview" on every branch and pull-request build, so a preview is a
 * beta build automatically and production cannot be one. This exists for looking
 * at the overlay locally in a real build rather than in `vite dev`, which is the
 * only way to see what a tester actually sees.
 *
 * Why a script rather than `VITE_SBR_BETA=1 npm run build` in package.json: that
 * form is POSIX-only and this repository is developed on Windows. The obvious
 * fix - shelling back into npm from `node -e` - fails on Windows too (EINVAL
 * spawning npm.cmd through execFileSync). Spawning the local vite binary
 * directly avoids both.
 */

import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const WEB = dirname(dirname(fileURLToPath(import.meta.url)));
const env = { ...process.env, VITE_SBR_BETA: "1" };

/** Run one of the locally installed bins, the way npm would. */
function run(bin, args) {
  const cmd = process.platform === "win32" ? `${bin}.cmd` : bin;
  const result = spawnSync(join(WEB, "node_modules", ".bin", cmd), args, {
    cwd: WEB,
    env,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

// Same two steps as `npm run build`, so the beta build is not a different build.
run("tsc", ["-b"]);
run("vite", ["build"]);

console.log("\nbeta build: src/dev/ and the Vercel telemetry are INCLUDED.");
console.log("Check it with:  VITE_SBR_BETA=1 node scripts/check-bundle.mjs");
