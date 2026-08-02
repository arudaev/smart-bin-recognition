/* How old a registry fact is, as the four segments the interface draws.

   Bins move. Every fact that came from the shared registry carries when it was
   last confirmed, and the interface says so wherever that fact appears – on a
   map pin and on a result card alike. Segments rather than colour, so the
   difference survives greyscale, sunlight and colour blindness. */

export type FreshnessLevel = 0 | 1 | 2 | 3 | 4;

const DAY = 24 * 60 * 60 * 1000;

/** Thresholds in days, from freshest. Level 0 means never confirmed. */
export const FRESHNESS_DAYS = { 4: 7, 3: 30, 2: 90 } as const;

/** Level 1 or below is presented as stale: the card asks for a confirmation. */
export const STALE_AT_OR_BELOW: FreshnessLevel = 1;

export function freshnessFrom(lastConfirmed: Date | string | null, now: Date = new Date()): FreshnessLevel {
  if (!lastConfirmed) return 0;
  const then = typeof lastConfirmed === "string" ? new Date(lastConfirmed) : lastConfirmed;
  if (Number.isNaN(then.getTime())) return 0;

  const days = (now.getTime() - then.getTime()) / DAY;
  if (days <= FRESHNESS_DAYS[4]) return 4;
  if (days <= FRESHNESS_DAYS[3]) return 3;
  if (days <= FRESHNESS_DAYS[2]) return 2;
  return 1;
}

export function isStale(level: FreshnessLevel): boolean {
  return level > 0 && level <= STALE_AT_OR_BELOW;
}
