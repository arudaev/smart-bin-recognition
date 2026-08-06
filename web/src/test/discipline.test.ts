import { readFileSync, readdirSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");

/* The rules in web/CONVENTIONS.md that a reviewer would otherwise have to hold
   in their head, held here instead.

   These are not style preferences. "Logical properties only" is what makes the
   Arabic build work at all, and "colour is quoted, never worn" is the mechanism
   that stops the interface being mistaken for the object it is pointed at. Both
   fail silently and both are one careless line away, which is exactly the shape
   of rule worth spending a test on. */

interface File {
  path: string;
  rel: string;
  text: string;
}

function walk(dir: string): File[] {
  const out: File[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walk(full));
    } else if ([".ts", ".tsx"].includes(extname(entry.name))) {
      out.push({ path: full, rel: relative(SRC, full).replace(/\\/g, "/"), text: readFileSync(full, "utf8") });
    }
  }
  return out;
}

const ALL = walk(SRC);

/** The design system is the whole product surface. dev/ and test/ are not. */
const PRODUCT = ALL.filter(
  (f) => !f.rel.startsWith("dev/") && !f.rel.startsWith("test/") && !f.rel.endsWith(".test.ts") && !f.rel.endsWith(".test.tsx"),
);

/* A hex literal is the shape a *worn* colour takes – a bin colour or a theme
   colour written into a component instead of read from a token. Two files hold
   one, both deliberately, and both say why in the file itself. */
const HEX_EXCEPTIONS = new Set([
  // The marker overlays a photograph. Its ink casing is a drop-shadow filter,
  // and filters cannot read a custom property.
  "components/domain/DetectionMarker.tsx",
  // Controls floating over the live camera. The design system's §3 specifies
  // this one translucency literally, because it sits on the camera surface,
  // which is the one surface the design does not control.
  "components/core/IconButton.tsx",
]);

/* `rgba()` is a different thing from a worn colour: in this system it is only
   ever ink or paper at an alpha, for a scrim over the camera or an edge on a
   swatch. Neither can be a token, because both have to be independent of the
   theme – one sits on a photograph, the other on a measured colour. */
const ALPHA_EXCEPTIONS = new Set([
  ...HEX_EXCEPTIONS,
  // The strip pinned over the live frame. Same argument as IconButton.
  "components/feedback/StatusStrip.tsx",
  // A one-pixel inner highlight, so a black swatch still has an edge against a
  // dark card. It is a property of the quote, not of the colour being quoted.
  "components/domain/ColorQuote.tsx",
]);

/* The marker positions its box with physical left/top because it overlays a
   photograph, and a photograph does not mirror under RTL. */
const DIRECTION_EXCEPTIONS = new Set(["components/domain/DetectionMarker.tsx"]);

function offenders(files: File[], pattern: RegExp): string[] {
  const found: string[] = [];
  for (const file of files) {
    for (const [index, line] of file.text.split("\n").entries()) {
      if (pattern.test(line)) found.push(`${file.rel}:${index + 1}  ${line.trim()}`);
    }
  }
  return found;
}

describe("colour is quoted, never worn", () => {
  it("writes no colour as a hex literal", () => {
    const files = PRODUCT.filter((f) => !HEX_EXCEPTIONS.has(f.rel));
    expect(offenders(files, /#[0-9a-fA-F]{3,8}\b/)).toEqual([]);
  });

  it("uses no alpha colour outside the surfaces that cannot be themed", () => {
    const files = PRODUCT.filter((f) => !ALPHA_EXCEPTIONS.has(f.rel));
    expect(offenders(files, /\brgba?\(/)).toEqual([]);
  });

  it("never writes one of the eleven measured bin colours into a component", () => {
    // The whole rule in one check: a bin colour may exist on screen only inside
    // a ColorQuote, which reads it from tokens/bin-color.css by name.
    const files = PRODUCT.filter((f) => !f.rel.startsWith("styles/"));
    expect(offenders(files, /#(1f4fa8|1e7a3c|6b4423|1a1a1a|8a8a8a|f2c200|e8720c|c1272d|f2f2f2|9ba3a8)\b/i)).toEqual([]);
  });

  it("keeps every exception documenting itself", () => {
    for (const rel of [...HEX_EXCEPTIONS, ...DIRECTION_EXCEPTIONS]) {
      const file = ALL.find((f) => f.rel === rel);
      expect(file, `${rel} is listed as an exception but does not exist`).toBeDefined();
      // If the reason ever stops being written down, the exception stops being
      // an exception and becomes a precedent.
      expect(file!.text).toMatch(/photograph|camera surface/i);
    }
  });
});

describe("logical properties only", () => {
  it("uses no physical margin, padding or border side", () => {
    expect(offenders(PRODUCT, /\b(margin|padding|border)(Left|Right)\b/)).toEqual([]);
  });

  it("uses no physical left or right offset outside the marker", () => {
    const files = PRODUCT.filter((f) => !DIRECTION_EXCEPTIONS.has(f.rel));
    // `inset:` is symmetric and therefore safe; `left:`/`right:` are not.
    expect(offenders(files, /(^|[^-\w])(left|right):\s/)).toEqual([]);
  });

  it("uses no textAlign of left or right", () => {
    expect(offenders(PRODUCT, /textAlign:\s*"(left|right)"/)).toEqual([]);
  });

  it("sizes with inlineSize and blockSize, not width and height", () => {
    // `width`/`height` as DOM attributes on <svg> and <canvas> are fine; as CSS
    // in a style object they are the physical axis under a vertical writing
    // mode. Only style objects are checked.
    expect(offenders(PRODUCT, /\bstyle=\{\{[^}]*\b(width|height):/)).toEqual([]);
  });
});

describe("prose", () => {
  it("uses en dashes, never em dashes", () => {
    // PRODUCT rather than ALL: this file and i18n.test.ts both have to contain
    // the character in order to check for it.
    expect(offenders(PRODUCT, /—/)).toEqual([]);
  });
});

describe("layering", () => {
  it("keeps domain/ free of any framework", () => {
    // The resolver is the piece most likely to be quietly wrong and the piece
    // that has to run identically in a browser and in a test. A React import
    // here would make it untestable without a DOM, so it is forbidden outright.
    const domain = PRODUCT.filter((f) => f.rel.startsWith("domain/"));
    expect(domain.length).toBeGreaterThan(0);
    expect(offenders(domain, /from "react|from "@\/components|document\.|window\./)).toEqual([]);
  });

  it("keeps components/ free of translation calls", () => {
    // Strings arrive as props. A component that calls t() cannot be reused for
    // a string the design did not anticipate, and cannot be rendered in a test
    // without a locale.
    const components = PRODUCT.filter((f) => f.rel.startsWith("components/"));
    expect(offenders(components, /\bt\(\s*"/)).toEqual([]);
  });

  it("keeps domain/ and data/ from importing features/", () => {
    const lower = PRODUCT.filter((f) => f.rel.startsWith("domain/") || f.rel.startsWith("data/"));
    expect(offenders(lower, /from "@\/features/)).toEqual([]);
  });
});

describe("the shell fills the viewport", () => {
  /* App.tsx was a prototype viewer for one phase: a 390x812 bordered box with a
     drop shadow, centred on a page. Removing it once is not the same as it
     staying removed – a fixed-width card is what a prototype shell looks like
     on the way in, and it arrives one plausible commit at a time. */
  const shell = () => ALL.find((f) => f.rel === "App.tsx")!;

  it("sizes nothing in the shell with a bare number", () => {
    expect(offenders([shell()], /\b(inline|block)Size:\s*\d/)).toEqual([]);
  });

  it("uses no vh in the shell", () => {
    // 100vh is measured against the viewport with the mobile URL bar retracted,
    // so a 100vh scanner is a screen and a bit tall and the bottom of the sheet
    // sits under the browser's own chrome. The shell is 100dvh, declared in
    // tokens/base.css because a style object cannot carry the vh fallback.
    expect(offenders([shell()], /\dvh\b/)).toEqual([]);
  });

  it("draws no frame around the surface", () => {
    // The border and the drop shadow were the device mockup. Neither belongs to
    // a shell whose whole job is to get out of the way of a screen.
    expect(offenders([shell()], /\b(border|boxShadow):/)).toEqual([]);
  });
});

describe("the guardrails", () => {
  it("ships no inference runtime", () => {
    // AGENTS.md: "There is no model. If anything here imports an inference
    // runtime it is in the wrong repository."
    expect(offenders(PRODUCT, /onnxruntime|@tensorflow|@xenova|transformers\.js/)).toEqual([]);
  });

  it("has no leftover debugging in the product surface", () => {
    expect(offenders(PRODUCT, /console\.(log|debug)\(|\bdebugger\b|\.only\(/)).toEqual([]);
  });
});
