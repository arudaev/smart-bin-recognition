/* The transfer budget, enforced.
 *
 * The runtime budgets in src/perf/ measure what happens once the app is
 * running. This one measures what has to arrive before it can run at all, which
 * on the device this product is written for is the larger number.
 *
 * Sizes are gzip, because that is what crosses the network. Raw bytes are
 * reported alongside because that is what has to be parsed, and on a 2019
 * Android parse time is the part you feel.
 *
 * The budgets are deliberately close to today's numbers. A budget with slack in
 * it is a budget that gets used up quietly; one that fails the moment something
 * grows is a budget that starts a conversation.
 *
 *   node scripts/check-bundle.mjs        report and enforce
 *   node scripts/check-bundle.mjs --json emit the numbers for a run log
 */

import { gzipSync } from "node:zlib";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = join(HERE, "..", "dist");

/** Gzip kB. `total` is everything the first load needs before an answer. */
const BUDGETS = {
  "js:total": 115,
  "css:total": 8,
  html: 2,
  "icons:total": 20,
  total: 145,
};

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

let files;
try {
  files = walk(DIST);
} catch {
  console.error("No dist/. Run `npm run build` first.");
  process.exit(1);
}

/* Photographs are excluded from the first-load budget on purpose: the fixture
   frames are demonstration content that a real scanner never downloads, and
   counting them would make the number a story about the prototype. */
const IGNORE = new Set([".png", ".jpg", ".jpeg", ".webp", ".map"]);

const rows = [];
for (const file of files) {
  const rel = relative(DIST, file).replace(/\\/g, "/");
  const ext = extname(file);
  if (rel.startsWith("photos/")) continue;

  const bytes = readFileSync(file);
  const gz = IGNORE.has(ext) ? bytes.length : gzipSync(bytes, { level: 9 }).length;

  let group = "other";
  if (ext === ".js") group = "js";
  else if (ext === ".css") group = "css";
  else if (ext === ".html") group = "html";
  else if (rel.startsWith("icons/")) group = "icons";

  rows.push({ rel, group, raw: bytes.length, gz });
}

const totals = { total: 0 };
for (const row of rows) {
  totals.total += row.gz;
  const key = row.group === "html" ? "html" : `${row.group}:total`;
  totals[key] = (totals[key] ?? 0) + row.gz;
}

if (process.argv.includes("--json")) {
  console.log(JSON.stringify({ files: rows, totals, budgets: BUDGETS }, null, 2));
  process.exit(0);
}

/* The other kind of budget: things that must not be in the bundle at all.
 *
 * src/dev/DevTools.tsx used to be a static import in App.tsx. Both panels
 * returned null in production, but their props – every state label in the
 * product, "densest verified frame" and the rest – were constructed either way,
 * so the copy shipped to every user. It is reached through a DEV-only dynamic
 * import now, which is a claim about what the bundler does with a folded
 * constant. This is where the claim is checked. */
const FORBIDDEN = [{ marker: "sbr-dev-only-do-not-ship", what: "the state director (src/dev/)" }];

/* A BETA BUILD INVERTS THIS CHECK RATHER THAN SKIPPING IT.
 *
 * A Vercel preview is meant to carry the metrics overlay - a tester needs it for
 * the reason a developer does. So on a beta build the sentinel must be PRESENT,
 * and its absence is the failure: it would mean the overlay silently did not
 * ship and the tester is looking at a build that cannot report anything.
 *
 * Production is unchanged: the sentinel must be absent, exactly as before. The
 * point of asserting both directions is that neither mode can quietly become
 * the other - a skipped check would let a broken beta pass as a clean build. */
const BETA = process.env.VERCEL_ENV === "preview" || process.env.VITE_SBR_BETA === "1";

const smuggled = [];
const missing = [];
for (const { marker, what } of FORBIDDEN) {
  const present = rows.some((row) => {
    if (row.group !== "js" && row.group !== "css") return false;
    return readFileSync(join(DIST, row.rel), "utf8").includes(marker);
  });
  if (BETA && !present) missing.push(`  ${what} is NOT in the bundle`);
  if (!BETA && present) {
    for (const row of rows) {
      if (row.group !== "js" && row.group !== "css") continue;
      if (readFileSync(join(DIST, row.rel), "utf8").includes(marker)) {
        smuggled.push(`  ${row.rel} contains ${what}`);
      }
    }
  }
}

const kb = (n) => `${(n / 1024).toFixed(1)} kB`;

console.log("first load, gzip\n");
for (const row of [...rows].sort((a, b) => b.gz - a.gz)) {
  if (row.gz < 512 && row.group === "icons") continue; // the favicons are noise
  console.log(`  ${row.rel.padEnd(34)} ${kb(row.gz).padStart(9)}   raw ${kb(row.raw)}`);
}

console.log("");
let failed = 0;
for (const [name, budgetKb] of Object.entries(BUDGETS)) {
  const actual = totals[name] ?? 0;
  const budget = budgetKb * 1024;
  const over = actual > budget;
  if (over) failed += 1;
  const pct = ((actual / budget) * 100).toFixed(0);
  console.log(`  ${over ? "OVER" : "ok  "} ${name.padEnd(14)} ${kb(actual).padStart(9)} / ${kb(budget).padStart(9)}  ${pct}%`);
}

if (missing.length > 0) {
  console.error("\nThis is a BETA build and the metrics overlay did not ship:\n");
  console.error(missing.join("\n"));
  console.error("\nVERCEL_ENV=preview (or VITE_SBR_BETA=1) must reach src/dev/ via __BETA__ in App.tsx.");
  process.exit(1);
}

if (smuggled.length > 0) {
  console.error("\nDevelopment-only code reached the bundle:\n");
  console.error(smuggled.join("\n"));
  console.error("\nIt must be behind a dynamic import on an import.meta.env.DEV branch.");
  process.exit(1);
}

if (failed > 0) {
  console.error(`\n${failed} budget${failed === 1 ? "" : "s"} exceeded.`);
  console.error("Either the growth is worth it and the budget moves in the same commit, or it is not.");
  process.exit(1);
}
console.log("\nWithin budget.");
