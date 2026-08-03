import { describe, expect, it } from "vitest";

import { PACK_PRECISION, coarsen, decodeGeohash, encodeGeohash } from "./geohash";

/* docs/01-architecture.md § 7: location travelling with a frame is geohash-6,
   about 1.2 km on a side. The privacy claim rests on the coarseness being
   structural rather than promised, so what is tested here is the coarseness. */

describe("encodeGeohash", () => {
  it("agrees with the reference example for the algorithm", () => {
    // The canonical worked example: 42.6, -5.6 -> ezs42.
    expect(encodeGeohash(42.6, -5.6, 5)).toBe("ezs42");
  });

  it("places Deggendorf where the pack expects it", () => {
    const hash = encodeGeohash(48.8372, 12.9611, PACK_PRECISION);
    expect(hash).toHaveLength(6);
    const back = decodeGeohash(hash);
    expect(back.lat).toBeCloseTo(48.8372, 2);
    expect(back.lon).toBeCloseTo(12.9611, 2);
  });

  it("defaults to the precision the packs are keyed on", () => {
    expect(encodeGeohash(48.8372, 12.9611)).toHaveLength(PACK_PRECISION);
    expect(PACK_PRECISION).toBe(6);
  });

  it("handles the poles and the antimeridian without throwing", () => {
    for (const [lat, lon] of [
      [90, 180],
      [-90, -180],
      [0, 0],
    ] as const) {
      expect(encodeGeohash(lat, lon)).toHaveLength(6);
    }
  });
});

describe("decodeGeohash", () => {
  it("reports a cell about 1.2 km across at precision 6", () => {
    // The whole privacy argument in one assertion: this is a neighbourhood,
    // not a doorstep. Roughly 610 m x 610 m, so under a kilometre each way.
    const { latError, lonError } = decodeGeohash(encodeGeohash(48.8372, 12.9611));
    const metresLat = latError * 111_320;
    const metresLon = lonError * 111_320 * Math.cos((48.8372 * Math.PI) / 180);
    expect(metresLat).toBeGreaterThan(200);
    expect(metresLat).toBeLessThan(700);
    expect(metresLon).toBeGreaterThan(200);
    expect(metresLon).toBeLessThan(900);
  });

  it("is case-insensitive, because a hash pasted from a log is often upper", () => {
    expect(decodeGeohash("U1Q0RZ")).toEqual(decodeGeohash("u1q0rz"));
  });

  it("refuses a string that is not a geohash rather than returning a place", () => {
    // 'a', 'i', 'l' and 'o' are deliberately absent from the alphabet.
    expect(() => decodeGeohash("u1q0ra")).toThrow(/not a geohash/);
    expect(() => decodeGeohash("hello!")).toThrow();
  });
});

describe("coarsen", () => {
  it("truncates, because a finer hash is a prefix of a coarser one", () => {
    const fine = encodeGeohash(48.8372, 12.9611, 9);
    expect(coarsen(fine)).toBe(fine.slice(0, 6));
    expect(coarsen(fine, 4)).toBe(fine.slice(0, 4));
  });

  it("cannot be un-rounded, which is why it is a string and not a number", () => {
    const coarse = coarsen(encodeGeohash(48.83721, 12.96114, 9));
    const other = coarsen(encodeGeohash(48.83729, 12.96119, 9));
    expect(coarse).toBe(other);
  });
});
