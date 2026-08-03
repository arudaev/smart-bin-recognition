import { describe, expect, it } from "vitest";

import { FRESHNESS_DAYS, STALE_AT_OR_BELOW, freshnessFrom, isStale } from "./freshness";

/* "Every registry-derived fact carries when it was last confirmed, in words as
   well as marks. Something checked yesterday and something last seen eight
   months ago never read the same." – the design system, §2. */

const NOW = new Date("2026-08-04T12:00:00Z");
const daysAgo = (n: number) => new Date(NOW.getTime() - n * 24 * 60 * 60 * 1000);

describe("freshnessFrom", () => {
  it("reports level 0 for something never confirmed", () => {
    expect(freshnessFrom(null, NOW)).toBe(0);
  });

  it("fills all four segments inside the week", () => {
    expect(freshnessFrom(daysAgo(0), NOW)).toBe(4);
    expect(freshnessFrom(daysAgo(FRESHNESS_DAYS[4]), NOW)).toBe(4);
  });

  it("steps down at each threshold and not before", () => {
    expect(freshnessFrom(daysAgo(FRESHNESS_DAYS[4] + 1), NOW)).toBe(3);
    expect(freshnessFrom(daysAgo(FRESHNESS_DAYS[3]), NOW)).toBe(3);
    expect(freshnessFrom(daysAgo(FRESHNESS_DAYS[3] + 1), NOW)).toBe(2);
    expect(freshnessFrom(daysAgo(FRESHNESS_DAYS[2]), NOW)).toBe(2);
    expect(freshnessFrom(daysAgo(FRESHNESS_DAYS[2] + 1), NOW)).toBe(1);
  });

  it("bottoms out at 1 rather than collapsing into never-confirmed", () => {
    // Level 0 means nobody has ever said this bin is here. Eight months old is
    // a different claim from no claim, and the card says something different.
    expect(freshnessFrom(daysAgo(240), NOW)).toBe(1);
    expect(freshnessFrom(daysAgo(4000), NOW)).toBe(1);
  });

  it("accepts an ISO string, which is what a pack and an API both carry", () => {
    expect(freshnessFrom("2026-08-03T09:00:00Z", NOW)).toBe(4);
  });

  it("treats an unparseable date as never confirmed rather than as fresh", () => {
    expect(freshnessFrom("not a date", NOW)).toBe(0);
    expect(freshnessFrom("", NOW)).toBe(0);
  });

  it("does not report the future as stale", () => {
    expect(freshnessFrom(daysAgo(-3), NOW)).toBe(4);
  });
});

describe("isStale", () => {
  it("asks for a confirmation at level 1 and below, but never at level 0", () => {
    // Level 0 has nothing to confirm: no one has claimed this bin exists.
    expect(isStale(0)).toBe(false);
    expect(isStale(1)).toBe(true);
    expect(isStale(2)).toBe(false);
    expect(STALE_AT_OR_BELOW).toBe(1);
  });
});
