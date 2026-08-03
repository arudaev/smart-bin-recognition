/* Geohash, because the privacy rule needs a unit of place that is coarse by
   construction rather than by promise.

   docs/01-architecture.md § 7: location travelling with a frame is geohash-6 –
   about 1.2 km on a side – which is enough to choose a jurisdiction and not
   enough to locate a household. Rounding coordinates would leave a number that
   still looks like a coordinate and invites somebody to add a decimal back.
   A six-character string cannot be un-rounded.

   Precise coordinates exist in exactly one flow: an explicit registry
   contribution, where the user is deliberately marking a bin's position. */

const BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";

export const PACK_PRECISION = 6;

export interface LatLon {
  lat: number;
  lon: number;
}

export function encodeGeohash(lat: number, lon: number, precision = PACK_PRECISION): string {
  let latMin = -90;
  let latMax = 90;
  let lonMin = -180;
  let lonMax = 180;
  let hash = "";
  let bits = 0;
  let value = 0;
  let even = true;

  while (hash.length < precision) {
    if (even) {
      const mid = (lonMin + lonMax) / 2;
      if (lon >= mid) {
        value = (value << 1) + 1;
        lonMin = mid;
      } else {
        value <<= 1;
        lonMax = mid;
      }
    } else {
      const mid = (latMin + latMax) / 2;
      if (lat >= mid) {
        value = (value << 1) + 1;
        latMin = mid;
      } else {
        value <<= 1;
        latMax = mid;
      }
    }
    even = !even;
    bits += 1;
    if (bits === 5) {
      hash += BASE32[value];
      bits = 0;
      value = 0;
    }
  }
  return hash;
}

export function decodeGeohash(hash: string): { lat: number; lon: number; latError: number; lonError: number } {
  let latMin = -90;
  let latMax = 90;
  let lonMin = -180;
  let lonMax = 180;
  let even = true;

  for (const char of hash.toLowerCase()) {
    const index = BASE32.indexOf(char);
    if (index < 0) throw new Error(`not a geohash: ${hash}`);
    for (let bit = 4; bit >= 0; bit -= 1) {
      const on = (index >> bit) & 1;
      if (even) {
        const mid = (lonMin + lonMax) / 2;
        if (on) lonMin = mid;
        else lonMax = mid;
      } else {
        const mid = (latMin + latMax) / 2;
        if (on) latMin = mid;
        else latMax = mid;
      }
      even = !even;
    }
  }
  return {
    lat: (latMin + latMax) / 2,
    lon: (lonMin + lonMax) / 2,
    latError: (latMax - latMin) / 2,
    lonError: (lonMax - lonMin) / 2,
  };
}

/** Truncation is the whole point: a finer hash is a prefix of a coarser one. */
export function coarsen(hash: string, precision = PACK_PRECISION): string {
  return hash.slice(0, precision);
}
