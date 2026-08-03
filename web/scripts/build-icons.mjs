/* Rasterise the app icon.
 *
 * The mark is specified, not invented here: the design system's §4 describes it
 * as "the detection frame – the product's own signature shape – around a
 * two-wheel household bin, the form factor in nearly every archive photograph.
 * Paper on violet." The geometry below is that drawing, in the same 100-unit
 * space the design system's thumbnail uses, so the icon and the thumbnail are
 * the same mark rather than two drawings of one idea.
 *
 * It rasterises without a dependency. Every shape in the mark is a stroked line
 * or a stroked rounded rectangle, and the signed distance to both is four lines
 * of arithmetic, so analytic coverage gives cleaner edges than a supersampler
 * and the whole thing is a hundred lines instead of a 30 MB native binary in
 * devDependencies. PNG is deflate plus four chunks; node has zlib.
 *
 *   node scripts/build-icons.mjs
 *
 * Degradation is designed rather than exported: the brackets are dropped below
 * 48 px, where a 4/100 stroke is under a quarter of a pixel and would render as
 * grey mud, and the bin scales up to fill the favicon instead.
 */

import { deflateSync } from "node:zlib";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "public", "icons");

/* Tokens, copied rather than imported: this script runs in node with no CSS. */
const SIGNAL = [0x5b, 0x2e, 0x91];
const PAPER = [0xfc, 0xfb, 0xf8];

const STROKE = 4;

/** The four corner brackets of the detection frame. */
const BRACKETS = [
  [30, 30, 22, 30],
  [22, 30, 22, 38],
  [70, 30, 78, 30],
  [78, 30, 78, 38],
  [30, 70, 22, 70],
  [22, 70, 22, 62],
  [70, 70, 78, 70],
  [78, 70, 78, 62],
];

/** The bin: a body, the lid line it hangs under, and the handle above it. */
const BIN_BODY = { x: 38, y: 38, w: 24, h: 26, r: 2 };
const BIN_LINES = [
  [36, 38, 64, 38],
  [46, 34, 54, 34],
];

/* ---- distance fields --------------------------------------------------- */

function distanceToSegment(px, py, ax, ay, bx, by) {
  const vx = bx - ax;
  const vy = by - ay;
  const wx = px - ax;
  const wy = py - ay;
  const len = vx * vx + vy * vy;
  const t = len === 0 ? 0 : Math.max(0, Math.min(1, (wx * vx + wy * vy) / len));
  const dx = wx - t * vx;
  const dy = wy - t * vy;
  return Math.hypot(dx, dy);
}

/** Signed distance to a rounded rectangle; negative inside. */
function distanceToRoundedBox(px, py, box) {
  const cx = box.x + box.w / 2;
  const cy = box.y + box.h / 2;
  const hx = box.w / 2 - box.r;
  const hy = box.h / 2 - box.r;
  const qx = Math.abs(px - cx) - hx;
  const qy = Math.abs(py - cy) - hy;
  const outside = Math.hypot(Math.max(qx, 0), Math.max(qy, 0));
  const inside = Math.min(Math.max(qx, qy), 0);
  return outside + inside - box.r;
}

/**
 * Coverage of one pixel, 0..1.
 *
 * `d` is the distance to the shape's edge in icon units and `px` is one device
 * pixel in the same units, so the ramp is exactly one pixel wide whatever the
 * output size – which is why a 16 px favicon and a 512 px icon have edges of
 * the same apparent softness rather than the small one looking blurred.
 */
function coverage(d, px) {
  return Math.max(0, Math.min(1, 0.5 - d / px));
}

/* ---- the mark ----------------------------------------------------------- */

/**
 * @param {object} opts
 * @param {number} opts.size            output edge in pixels
 * @param {boolean} opts.brackets       draw the detection frame
 * @param {number} opts.scale           content scale about the centre
 * @param {boolean} opts.transparent    no violet ground; shapes carry the alpha
 */
function render({ size, brackets = true, scale = 1, transparent = false }) {
  const rgba = new Uint8Array(size * size * 4);
  const unit = 100 / size; // icon units per device pixel
  const fg = transparent ? [0, 0, 0] : PAPER;

  // Content is scaled about the centre of the 100-unit space, so a maskable
  // icon shrinks the drawing inside its safe area without moving it.
  const at = (v) => 50 + (v - 50) / scale;

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const px = at((x + 0.5) * unit);
      const py = at((y + 0.5) * unit);

      let ink = 0;
      if (brackets) {
        for (const [ax, ay, bx, by] of BRACKETS) {
          ink = Math.max(ink, coverage(distanceToSegment(px, py, ax, ay, bx, by) - STROKE / 2, unit / scale));
          if (ink >= 1) break;
        }
      }
      if (ink < 1) {
        const body = Math.abs(distanceToRoundedBox(px, py, BIN_BODY)) - STROKE / 2;
        ink = Math.max(ink, coverage(body, unit / scale));
      }
      if (ink < 1) {
        for (const [ax, ay, bx, by] of BIN_LINES) {
          ink = Math.max(ink, coverage(distanceToSegment(px, py, ax, ay, bx, by) - STROKE / 2, unit / scale));
          if (ink >= 1) break;
        }
      }

      const i = (y * size + x) * 4;
      if (transparent) {
        rgba[i] = fg[0];
        rgba[i + 1] = fg[1];
        rgba[i + 2] = fg[2];
        rgba[i + 3] = Math.round(ink * 255);
      } else {
        // Composite paper over violet. Straight alpha, no premultiplication:
        // both are opaque and only the edge pixels blend.
        for (let c = 0; c < 3; c += 1) {
          rgba[i + c] = Math.round(SIGNAL[c] * (1 - ink) + fg[c] * ink);
        }
        rgba[i + 3] = 255;
      }
    }
  }
  return rgba;
}

/* ---- PNG ---------------------------------------------------------------- */

const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i += 1) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const out = Buffer.alloc(data.length + 12);
  out.writeUInt32BE(data.length, 0);
  out.write(type, 4, "ascii");
  data.copy(out, 8);
  const body = out.subarray(4, 8 + data.length);
  out.writeUInt32BE(crc32(body), 8 + data.length);
  return out;
}

function png(rgba, size) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // truecolour with alpha
  // 10..12: deflate, adaptive filtering, no interlace – all zero.

  // One filter byte per scanline. Filter 0: the art is flat colour and large
  // runs, which deflate already handles; a predictor would cost more than it saves.
  const raw = Buffer.alloc(size * (size * 4 + 1));
  for (let y = 0; y < size; y += 1) {
    raw[y * (size * 4 + 1)] = 0;
    Buffer.from(rgba.buffer, y * size * 4, size * 4).copy(raw, y * (size * 4 + 1) + 1);
  }

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

/* ---- SVG ---------------------------------------------------------------- */

function svg({ brackets = true, scale = 1, transparent = false }) {
  const stroke = transparent ? "currentColor" : "#FCFBF8";
  const ground = transparent ? "" : `<rect width="100" height="100" fill="#5B2E91"/>`;
  const bracketPath = brackets
    ? `<path d="M30 30h-8v8M70 30h8v8M30 70h-8v-8M70 70h8v-8"/>`
    : "";
  const transform = scale === 1 ? "" : ` transform="translate(50 50) scale(${scale}) translate(-50 -50)"`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="Which Bin.">${ground}<g${transform} fill="none" stroke="${stroke}" stroke-width="${STROKE}" stroke-linecap="round" stroke-linejoin="round">${bracketPath}<rect x="38" y="38" width="24" height="26" rx="2"/><path d="M36 38h28M46 34h8"/></g></svg>\n`;
}

/* ---- outputs ------------------------------------------------------------ */

const RASTER = [
  // PWA `any`. Full bleed – launchers that do not mask show the whole square.
  { file: "icon-192.png", size: 192, brackets: true, scale: 1 },
  { file: "icon-512.png", size: 512, brackets: true, scale: 1 },

  // PWA `maskable`. Everything inside the 80% safe circle, so an aggressive
  // circular mask on Android never clips a bracket off.
  { file: "icon-maskable-192.png", size: 192, brackets: true, scale: 0.72 },
  { file: "icon-maskable-512.png", size: 512, brackets: true, scale: 0.72 },

  // PWA `monochrome`. Alpha only – the launcher supplies the colour.
  { file: "icon-mono-512.png", size: 512, brackets: true, scale: 0.72, transparent: true },

  // iOS home screen. Never transparent: iOS composites black behind alpha.
  { file: "apple-touch-icon.png", size: 180, brackets: true, scale: 0.86 },

  // Favicons. Below 48 px the brackets are under a quarter of a pixel of
  // stroke, so they are dropped and the bin fills the space instead.
  { file: "favicon-48.png", size: 48, brackets: false, scale: 0.62 },
  { file: "favicon-32.png", size: 32, brackets: false, scale: 0.58 },
  { file: "favicon-16.png", size: 16, brackets: false, scale: 0.54 },
];

const VECTOR = [
  { file: "icon.svg", brackets: true, scale: 1 },
  { file: "icon-maskable.svg", brackets: true, scale: 0.72 },
  { file: "icon-mono.svg", brackets: true, scale: 0.72, transparent: true },
  { file: "favicon.svg", brackets: false, scale: 0.62 },
];

mkdirSync(OUT, { recursive: true });

let bytes = 0;
for (const spec of RASTER) {
  const data = png(render(spec), spec.size);
  writeFileSync(join(OUT, spec.file), data);
  bytes += data.length;
  console.log(`${spec.file.padEnd(28)} ${spec.size}×${spec.size}  ${(data.length / 1024).toFixed(1)} kB`);
}
for (const spec of VECTOR) {
  const data = svg(spec);
  writeFileSync(join(OUT, spec.file), data);
  bytes += Buffer.byteLength(data);
  console.log(`${spec.file.padEnd(28)} vector    ${(Buffer.byteLength(data) / 1024).toFixed(1)} kB`);
}
console.log(`\n${RASTER.length + VECTOR.length} files, ${(bytes / 1024).toFixed(1)} kB total`);
