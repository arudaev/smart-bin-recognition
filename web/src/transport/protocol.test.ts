import { describe, expect, it } from "vitest";

import type { DetectRequest, DetectResponse, WireDetection } from "./protocol";
import {
  VALIDATOR_FLOOR,
  decodeFrameMessage,
  encodeFrameMessage,
  isError,
  resultSignature,
  usableDetections,
} from "./protocol";

/* This file is the contract with service/, which does not exist yet. Testing it
   against itself is not circular so long as what is asserted is the paragraph
   in docs/01-architecture.md § 4 rather than the implementation: a 4-byte
   big-endian header length, a JSON header, then the JPEG bytes, with no base64
   anywhere near the payload that dominates the uplink bill. */

const detection = (over: Partial<WireDetection> = {}): WireDetection => ({
  box: { x: 10, y: 20, w: 30, h: 40 },
  validator_conf: 0.95,
  form_factor: "wheelie_small",
  identifier_conf: 0.9,
  body_color: "black",
  lid_color: "grey",
  stream: null,
  stream_conf: 0,
  novelty: "none",
  ...over,
});

describe("frame framing", () => {
  const request: DetectRequest = { seq: 7, geohash6: "u1q0rz", locale: "de", debug: false };
  const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46]);

  it("round-trips the header and the bytes", () => {
    const { request: back, jpeg: bytes } = decodeFrameMessage(encodeFrameMessage(request, jpeg));
    expect(back).toEqual(request);
    expect(Array.from(bytes)).toEqual(Array.from(jpeg));
  });

  it("carries the JPEG as bytes, not as base64", () => {
    // A third more uplink on the one payload that dominates the bill.
    const buffer = encodeFrameMessage(request, jpeg);
    const header = JSON.stringify(request).length;
    expect(buffer.byteLength).toBe(4 + header + jpeg.byteLength);
  });

  it("writes the header length big-endian", () => {
    const buffer = encodeFrameMessage(request, jpeg);
    expect(new DataView(buffer).getUint32(0, false)).toBe(JSON.stringify(request).length);
  });

  it("survives a header whose JSON is multi-byte", () => {
    // Locales are not all ASCII and a length written in characters rather than
    // bytes would slice the JPEG in half on the first Arabic-speaking user.
    const wide: DetectRequest = { ...request, locale: "ar", geohash6: "u1q0rz" };
    const withEmoji = { ...wide, locale: "ar-Ω" } as DetectRequest;
    const { request: back, jpeg: bytes } = decodeFrameMessage(encodeFrameMessage(withEmoji, jpeg));
    expect(back.locale).toBe("ar-Ω");
    expect(Array.from(bytes)).toEqual(Array.from(jpeg));
  });

  it("handles an empty frame without corrupting the header", () => {
    const { request: back, jpeg: bytes } = decodeFrameMessage(encodeFrameMessage(request, new Uint8Array(0)));
    expect(back).toEqual(request);
    expect(bytes.byteLength).toBe(0);
  });
});

describe("isError", () => {
  it("separates an error from a response", () => {
    expect(isError({ seq: 1, error: "busy" })).toBe(true);
    expect(isError({ seq: 1, ms: 10, detections: [] } as DetectResponse)).toBe(false);
  });
});

describe("usableDetections", () => {
  it("drops anything the validator is not sure about", () => {
    const response: DetectResponse = {
      seq: 1,
      ms: 20,
      detections: [
        detection({ validator_conf: VALIDATOR_FLOOR }),
        detection({ validator_conf: VALIDATOR_FLOOR - 0.01 }),
      ],
    };
    expect(usableDetections(response)).toHaveLength(1);
  });
});

describe("resultSignature", () => {
  it("agrees across the drift of a hand-held phone", () => {
    // The lock needs three identical results. If a signature broke on a
    // half-percent wobble it would never close and the loop would stream for
    // the full twenty seconds, every scan.
    const a = resultSignature([detection({ box: { x: 10, y: 20, w: 30, h: 40 } })]);
    const b = resultSignature([detection({ box: { x: 10.4, y: 19.6, w: 30, h: 40 } })]);
    expect(a).toBe(b);
  });

  it("disagrees when the phone has been turned to a different bin", () => {
    const a = resultSignature([detection({ box: { x: 10, y: 20, w: 30, h: 40 } })]);
    const b = resultSignature([detection({ box: { x: 60, y: 20, w: 30, h: 40 } })]);
    expect(a).not.toBe(b);
  });

  it("disagrees when the same box became a different kind of bin", () => {
    const a = resultSignature([detection({ form_factor: "wheelie_small" })]);
    const b = resultSignature([detection({ form_factor: "igloo" })]);
    expect(a).not.toBe(b);
  });

  it("disagrees when a colour measurement changed", () => {
    const a = resultSignature([detection({ lid_color: "grey" })]);
    const b = resultSignature([detection({ lid_color: "blue" })]);
    expect(a).not.toBe(b);
  });

  it("does not depend on the order the service happened to return", () => {
    const one = detection({ box: { x: 5, y: 5, w: 10, h: 10 }, form_factor: "igloo" });
    const two = detection({ box: { x: 50, y: 5, w: 10, h: 10 }, form_factor: "wheelie_large" });
    expect(resultSignature([one, two])).toBe(resultSignature([two, one]));
  });

  it("distinguishes two bins from one", () => {
    const one = detection({ box: { x: 5, y: 5, w: 10, h: 10 } });
    const two = detection({ box: { x: 50, y: 5, w: 10, h: 10 } });
    expect(resultSignature([one])).not.toBe(resultSignature([one, two]));
  });

  it("gives an empty frame a stable signature so the lock can close on nothing", () => {
    expect(resultSignature([])).toBe(resultSignature([]));
  });
});
