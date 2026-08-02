#!/usr/bin/env node
/* Report how far each locale bundle has got against English.
 *
 * This does not fail the build. The Python side already fails CI when a locale
 * that claims to be complete is missing a taxonomy key
 * (ml/scripts/validate_taxonomy.py); this is the human-facing progress report
 * for the locales still being written.
 */

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const i18n = join(here, "..", "src", "i18n");

const read = (name) => JSON.parse(readFileSync(join(i18n, name), "utf8"));

const en = read("en.json");
const enKeys = Object.keys(en);

const bundles = readdirSync(i18n)
  .filter((f) => f.endsWith(".json") && f !== "en.json")
  .sort();

console.log(`en.json  ${String(enKeys.length).padStart(4)} keys  (reference)\n`);

let worst = 0;
for (const file of bundles) {
  const bundle = read(file);
  const missing = enKeys.filter((k) => !(k in bundle));
  const extra = Object.keys(bundle).filter((k) => !(k in en));
  const pct = Math.round((100 * (enKeys.length - missing.length)) / enKeys.length);
  worst = Math.max(worst, missing.length);

  console.log(`${file.padEnd(8)} ${String(Object.keys(bundle).length).padStart(4)} keys  ${String(pct).padStart(3)}%`);
  if (missing.length) {
    const head = missing.slice(0, 6).join(", ");
    const more = missing.length > 6 ? ` (+${missing.length - 6} more)` : "";
    console.log(`         missing ${missing.length}: ${head}${more}`);
  }
  if (extra.length) {
    console.log(`         NOT IN en (${extra.length}): ${extra.slice(0, 6).join(", ")}`);
  }
}

if (worst > 0) {
  console.log(`\nUntranslated keys fall back to English at runtime. See src/i18n/index.ts.`);
}
