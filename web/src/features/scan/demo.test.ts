import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { clientKind } from "@/transport";
import en from "@/i18n/en.json";

import { connMessage } from "./Scanner";

/* THE BUG THIS FILE EXISTS FOR.
 *
 * A Vercel preview went out with neither VITE_DETECT_URL nor VITE_DETECT_WS
 * set. `createClient` fell back to MockClient, which answers out of
 * data/frames.ts - boxes measured off archive photographs of Deggendorf - and
 * the scanner drew three markers over a living room, resolved them through the
 * real region pack, and captioned the frame "CONNECTED · DEGGENDORF". A tester
 * pointing a phone at their own floor was told bin 1 was Biomüll.
 *
 * Every individual part was behaving as designed. The mock is meant to answer;
 * the resolver is meant to resolve; `conn.live` is meant to say Connected once
 * the transport has answered a frame. What was missing was the one fact that
 * makes the composition honest: nothing on screen came from the camera.
 *
 * AGENTS.md's first guardrail is "never assert a disposal rule without a
 * region-pack entry, because being confidently wrong about what goes in which
 * bin is this product's worst failure". A rule asserted over a fabricated
 * detection is the same failure reached from the other end, so it is pinned the
 * same way: with tests that fail if the label goes quiet again.
 */

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = (rel: string) => readFileSync(join(SRC, rel), "utf8");

describe("naming the transport", () => {
  it("says mock when nothing is configured, which is the whole failure case", () => {
    expect(clientKind("scanner", {})).toBe("mock");
    expect(clientKind("viewer", {})).toBe("mock");
  });

  it("prefers the socket on a scanner and REST everywhere else", () => {
    const both = { socket: "wss://x/stream", rest: "https://x/detect" };
    expect(clientKind("scanner", both)).toBe("socket");
    expect(clientKind("capture", both)).toBe("rest");
    expect(clientKind("capture", { socket: both.socket })).toBe("socket");
  });

  it("agrees with the client that actually gets built", async () => {
    // Two functions deciding the same thing is how they drift apart. The kind
    // reported to the user has to be the kind that answers the frames.
    const { createClient } = await import("@/transport");
    for (const override of [{}, { rest: "https://x/detect" }, { socket: "wss://x/stream" }]) {
      expect(createClient("scanner", override).kind).toBe(clientKind("scanner", override));
    }
  });
});

describe("what the strip over the camera says", () => {
  const t = ((key: string) => (en as Record<string, string>)[key] ?? key) as never;
  const region = { key: "deggendorf" } as never;

  it("does not say Connected when no detector is connected", () => {
    const message = connMessage("demo", t, region);
    expect(message).not.toContain("Connected");
    expect(message.toLowerCase()).toContain("demo");
  });

  it("still says Connected when one is", () => {
    expect(connMessage("live", t, region)).toContain("Connected");
  });

  it("carries the demo strings in every bundle, so no locale falls back to silence", () => {
    for (const locale of ["en", "de", "ar"]) {
      const bundle = JSON.parse(read(`i18n/${locale}.json`)) as Record<string, string>;
      for (const key of ["conn.demo", "demo.title", "demo.body"]) {
        expect(bundle[key], `${locale} is missing ${key}`).toBeTruthy();
      }
    }
  });
});

/* The wiring, pinned at the source. There is no DOM in this suite - by design,
   see CONVENTIONS - so what a renderer would assert is asserted here instead:
   the two lines that carry the fact from the transport to the screen. Both are
   one careless edit from vanishing, and neither would fail anything else. */
describe("the wiring that carries it to the screen", () => {
  const app = read("App.tsx");
  const scanner = read("features/scan/Scanner.tsx");

  it("tells the scanner when the transport is the mock", () => {
    expect(app).toContain('demo={transport === "mock"}');
  });

  it("rewrites the live state rather than trusting it", () => {
    expect(scanner).toContain('demo && live.state.connection === "live"');
  });

  it("puts the caveat in the sheet, where the disposal rule is asserted", () => {
    expect(scanner).toContain('t("demo.title")');
    expect(scanner).toContain('t("demo.body")');
  });
});
