import { describe, expect, it } from "vitest";

import { FRAME_EDGE, FRAME_QUALITY, LUMA_EDGE, fitWithin } from "./encode";

/* 448 is not a guess. docs/08-legacy-audit § 7 measured the predecessor's
   detector across four input sizes: 960 px scored mAP50 0.9873 at 406 ms and
   448 px scored 0.9810 at 174 ms. Six tenths of a point for 2.3x the speed is
   the trade this product wants, and the client's job is to not send more pixels
   than the model will look at. */

describe("the frame constants", () => {
  it("matches the measured operating point", () => {
    expect(FRAME_EDGE).toBe(448);
  });

  it("keeps a 448 px street scene inside the frame budget", () => {
    // 0.7 lands around 25-35 kB, against a 45 kB budget in perf/metrics.
    expect(FRAME_QUALITY).toBeGreaterThanOrEqual(0.6);
    expect(FRAME_QUALITY).toBeLessThanOrEqual(0.8);
  });

  it("gates on a plane small enough to diff in a millisecond", () => {
    expect(LUMA_EDGE * LUMA_EDGE).toBe(4096);
  });
});

describe("fitWithin", () => {
  it("scales the long edge down to the target and keeps the aspect", () => {
    expect(fitWithin(1920, 1080, 448)).toEqual({ width: 448, height: 252 });
    expect(fitWithin(1080, 1920, 448)).toEqual({ width: 252, height: 448 });
  });

  it("never upscales – there is no information in a bigger copy", () => {
    expect(fitWithin(320, 240, 448)).toEqual({ width: 320, height: 240 });
  });

  it("leaves an exactly-sized frame alone", () => {
    expect(fitWithin(448, 448, 448)).toEqual({ width: 448, height: 448 });
  });

  it("never returns a zero dimension for a very wide frame", () => {
    // A canvas of width 0 throws, and the loop would die on the frame rather
    // than on the odd aspect ratio that caused it.
    const fit = fitWithin(4000, 3, 448);
    expect(fit.width).toBeGreaterThan(0);
    expect(fit.height).toBeGreaterThan(0);
  });

  it("falls back to a square rather than dividing by zero", () => {
    expect(fitWithin(0, 0, 448)).toEqual({ width: 448, height: 448 });
  });
});
