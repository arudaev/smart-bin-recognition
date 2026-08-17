/* Write the request half of the wire contract, using the real TypeScript encoder.
 *
 *     npm --prefix web run emit:fixtures
 *
 * WHY THIS EXISTS. src/transport/protocol.ts and service/wire.py both open by
 * citing docs/01-architecture.md § 4, and both were written by reading it. That
 * is not a contract, it is two opinions – and it had already failed: the service
 * emitted `advice` and `pack_status` for weeks while the client declared
 * neither and dropped both on the floor.
 *
 * So the two sides are pinned to bytes instead. This script encodes a set of
 * requests with the encoder the browser actually ships; the bytes are committed;
 * service/tests/test_wire_contract.py decodes them and asserts every field. The
 * reverse direction – responses encoded by Python and read by TypeScript – is
 * written by that same Python test and read back by contract.test.ts.
 *
 * The fixtures are COMMITTED and regenerating them is a deliberate act. A
 * fixture rewritten on every run pins nothing; it just agrees with whatever the
 * code does today, which is the failure mode this whole apparatus exists to
 * prevent. Run this when the wire genuinely changes, and expect the diff to be
 * reviewed as carefully as the change that caused it.
 *
 * HOW IT LOADS TYPESCRIPT. Through Vite's own SSR module loader, which resolves
 * `@/` from vite.config.ts and needs no transpiler dependency of its own. The
 * alternative – reimplementing the encoder in JavaScript – would produce a test
 * that pins the fixture generator against itself.
 */

import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createServer } from "vite";

const WEB = dirname(dirname(fileURLToPath(import.meta.url)));
const OUT = join(WEB, "src", "transport", "__fixtures__", "requests");

/* A JPEG whose bytes are recognisable in a hex dump: the real SOI/APP0 marker,
   then a run that no JSON header could produce. If a length is ever miscounted,
   the failure shows up as these bytes appearing in the wrong place rather than
   as an opaque "frame is shorter than its length prefix". */
const JPEG = Uint8Array.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0xff, 0xd9]);

/** Each case names the thing it would catch if it broke. */
const CASES = [
  {
    name: "ordinary",
    why: "the common path: a scanner mid-scan with a fix on its location",
    request: { seq: 1, geohash6: "u2853k", locale: "de", debug: false },
    jpeg: JPEG,
  },
  {
    name: "no-geohash",
    why: "location refused or not yet fixed. `null`, never an empty string – the service reads it as 'no jurisdiction' and answers stream: null",
    request: { seq: 2, geohash6: null, locale: "en", debug: false },
    jpeg: JPEG,
  },
  {
    name: "multibyte-locale",
    why: "a header length written in CHARACTERS rather than BYTES slices the JPEG in half, and does so first for a non-Latin locale",
    request: { seq: 3, geohash6: "u2853k", locale: "ar-Ω", debug: false },
    jpeg: JPEG,
  },
  {
    name: "debug",
    why: "the debug flag reaches the service as a boolean, not as the string \"false\"",
    request: { seq: 4, geohash6: "u2856p", locale: "uk", debug: true },
    jpeg: JPEG,
  },
  {
    name: "high-seq",
    why: "seq is not truncated. A long session outlives a 16-bit counter",
    request: { seq: 65_600, geohash6: "u2853k", locale: "en", debug: false },
    jpeg: JPEG,
  },
  {
    name: "empty-jpeg",
    why: "a zero-length payload must still decode to a valid header rather than to a framing error",
    request: { seq: 6, geohash6: null, locale: "en", debug: false },
    jpeg: new Uint8Array(0),
  },
];

const server = await createServer({
  configFile: join(WEB, "vite.config.ts"),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "warn",
  // protocol.ts imports nothing but a type, so there are no dependencies to
  // pre-bundle. Left on, the scanner crawls index.html in the background and
  // then loses its race with close(), which prints a stack trace after a run
  // that succeeded - the most misleading kind of output a build script has.
  optimizeDeps: { noDiscovery: true, include: [] },
});

try {
  const { encodeFrameMessage } = await server.ssrLoadModule("/src/transport/protocol.ts");

  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });

  const manifest = [];
  for (const { name, why, request, jpeg } of CASES) {
    const bytes = new Uint8Array(encodeFrameMessage(request, jpeg));
    writeFileSync(join(OUT, `${name}.bin`), bytes);
    manifest.push({
      name,
      why,
      file: `${name}.bin`,
      request,
      // Both, because they differ for multibyte-locale and that difference IS
      // the bug this fixture exists to catch.
      header_bytes: new TextEncoder().encode(JSON.stringify(request)).byteLength,
      header_chars: JSON.stringify(request).length,
      jpeg_bytes: jpeg.byteLength,
      total_bytes: bytes.byteLength,
    });
  }

  const note =
    "Generated by web/scripts/emit-wire-fixtures.mjs with the TypeScript encoder in " +
    "src/transport/protocol.ts. Read by service/tests/test_wire_contract.py. " +
    "Committed on purpose: regenerating these on every run would pin nothing. " +
    "Do not hand-edit - change protocol.ts and re-emit.";

  writeFileSync(join(OUT, "manifest.json"), `${JSON.stringify({ note, cases: manifest }, null, 2)}\n`);

  console.log(`wrote ${manifest.length} request fixtures to src/transport/__fixtures__/requests/`);
  console.log("these are committed – review the diff, then run the service's contract test");
} finally {
  await server.close();
}
