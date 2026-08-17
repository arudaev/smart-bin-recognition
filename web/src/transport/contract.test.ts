import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { DetectResponse, LoadAdvice, ServerMessage, WireError } from "./protocol";
import { isError, usableDetections } from "./protocol";

/* THE OTHER HALF OF THE CONTRACT.

   protocol.test.ts checks this file against itself, which is worth doing and is
   not enough: it would have passed happily for the whole period during which
   the service was sending `advice` and this client was throwing it away.

   These fixtures were written by service/tests/test_wire_contract.py from real
   `wire.py` dataclasses. They are bytes the service actually emits, not a
   TypeScript author's idea of them. If Python's shape changes, that test
   rewrites these files, this test fails, and the two are made to agree in one
   commit - which is the entire mechanism.

   Read as JSON rather than through a decoder because that is what the transport
   does: `rest.ts` calls response.json() and `socket.ts` calls JSON.parse. There
   is no validation layer to test, so the thing worth pinning is that the TYPES
   describe what actually arrives. */

const HERE = dirname(fileURLToPath(import.meta.url));
const RESPONSES = join(HERE, "__fixtures__", "responses");
const REQUESTS = join(HERE, "__fixtures__", "requests");

interface Fixture {
  why: string;
  payload: unknown;
}

function load(name: string): Fixture {
  return JSON.parse(readFileSync(join(RESPONSES, `${name}.json`), "utf8")) as Fixture;
}

const response = (name: string) => load(name).payload as DetectResponse;
const wireError = (name: string) => load(name).payload as WireError;

describe("the fixtures themselves", () => {
  it("exist, so this file cannot pass by doing nothing", () => {
    const files = readdirSync(RESPONSES).filter((f) => f.endsWith(".json"));
    expect(files.length).toBeGreaterThanOrEqual(9);
    expect(readdirSync(REQUESTS).filter((f) => f.endsWith(".bin")).length).toBeGreaterThanOrEqual(6);
  });

  it("each says what it is protecting", () => {
    // A fixture whose purpose is not written down becomes a fixture nobody
    // dares change and nobody understands.
    for (const file of readdirSync(RESPONSES).filter((f) => f.endsWith(".json"))) {
      const fixture = JSON.parse(readFileSync(join(RESPONSES, file), "utf8")) as Fixture;
      expect(fixture.why.length, `${file} has no explanation`).toBeGreaterThan(20);
    }
  });
});

describe("a response the service really sends", () => {
  it("reads every field the client depends on", () => {
    const body = response("plain");
    expect(body.seq).toBe(1);
    expect(body.ms).toBe(71);
    expect(body.region_id).toBe("de-by-deggendorf");
    expect(body.pack_status).toBe("draft");
    expect(body.detections).toHaveLength(1);
    expect(body.detections[0].box).toEqual({ x: 12.5, y: 30.0, w: 25.25, h: 44.5 });
    expect(body.detections[0].validator_conf).toBeCloseTo(0.9312);
  });

  it("carries a null form_factor, which is today's real answer", () => {
    /* The identifier is blocked on the 403-crop human pass, so the service says
       where a bin is and declines to say which. The client must render that as
       `unknown` rather than treat a null as a decoding failure. */
    const body = response("plain");
    expect(body.detections[0].form_factor).toBeNull();
    expect(body.detections[0].stream).toBeNull();
  });

  it("distinguishes an absent field from a null one", () => {
    /* wire.py omits `advice` and `debug` when unset and emits `pack_status:
       null` explicitly. The TypeScript types mirror exactly that split, and
       this is the assertion that keeps them mirroring it. */
    const body = response("plain");
    expect("advice" in body).toBe(false);
    expect("debug" in body).toBe(false);
    expect("pack_status" in body).toBe(true);

    const bare = response("no-pack");
    expect(bare.pack_status).toBeNull();
    expect(bare.region_id).toBeNull();
  });

  it("passes an empty frame through as an empty list", () => {
    const body = response("empty");
    expect(body.detections).toEqual([]);
    expect(usableDetections(body)).toEqual([]);
  });

  it("hands the debug block over in the shape the overlay reads", () => {
    const body = response("debug");
    expect(body.debug?.validator_ms).toBe(31);
    expect(body.debug?.identifier_ms).toBe(21);
    expect(body.debug?.validator_boxes[0].conf).toBeCloseTo(0.9312);
  });
});

describe("the degradation ladder, as it arrives on the wire", () => {
  it("rung 1 rides along with a perfectly good answer", () => {
    // Nothing is refused until rung 3. A client that treated advice as an error
    // would throw away the frame it just paid for.
    const body = response("advice-slow");
    expect(body.advice).toEqual({ max_fps: 2 });
    expect(body.detections).toHaveLength(1);
    expect(isError(body as ServerMessage)).toBe(false);
  });

  it("rung 2 asks for a stop, and still answers the frame", () => {
    const body = response("advice-tap");
    expect(body.advice?.max_fps).toBe(0);
    expect(body.detections).toHaveLength(1);
  });

  it("rung 3 is an error carrying a stated wait", () => {
    const body = wireError("error-busy");
    expect(isError(body as ServerMessage)).toBe(true);
    expect(body.retry_after_ms).toBe(1040);
    expect(body.advice?.queue_wait_ms).toBe(1040);
    expect(body.advice?.max_fps).toBe(0);
  });

  it("omits queue_wait_ms on the rungs that have no wait to state", () => {
    const advice = response("advice-slow").advice as LoadAdvice;
    expect("queue_wait_ms" in advice).toBe(false);
  });

  it("has an error shape that needs neither a seq nor advice", () => {
    // A framing error is not a load problem, and the header could not be read
    // far enough to have a seq.
    const body = wireError("error-bare");
    expect(body.seq).toBeNull();
    expect(body.advice).toBeUndefined();
    expect(body.retry_after_ms).toBeUndefined();
  });

  it("delivers a cadence the client is required to refuse", () => {
    /* The fixture carries max_fps 30 against a 4 fps cap. Nothing here clamps
       it - that is Cadence.setMaxFps's job and gates.test.ts asserts it. What
       this pins is that such a value ARRIVES intact, so the clamp is exercised
       by something real rather than only by a value a test invented. */
    expect(response("advice-raise").advice?.max_fps).toBe(30);
  });
});
