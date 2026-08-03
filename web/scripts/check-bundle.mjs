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

if (failed > 0) {
  console.error(`\n${failed} budget${failed === 1 ? "" : "s"} exceeded.`);
  console.error("Either the growth is worth it and the budget moves in the same commit, or it is not.");
  process.exit(1);
}
console.log("\nWithin budget.");
