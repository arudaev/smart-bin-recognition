import type { BinColor, FormFactor, StreamId } from "@/domain";

import type { Coverage } from "./regions";

/* The shared registry, as the desk surface sees it: where bins are, and how
   recently each was confirmed. Demonstration data – the real thing comes from
   the sightings API. Staleness is carried as a date so the four segments are
   computed the same way here as anywhere else. */

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

export interface RegistryEntry {
  stream: StreamId;
  where: string;
  count: number;
  lastConfirmed: string | null;
  /** Percentage position on the map surface. Coarse on purpose – see desk.coarseBody. */
  at: [number, number];
}

export const REGISTRY: Record<Coverage, RegistryEntry[]> = {
  published: [
    { stream: "bio", where: "Sendlinger Tor", count: 6, lastConfirmed: daysAgo(2), at: [24, 38] },
    { stream: "paper", where: "Sendlinger Tor", count: 4, lastConfirmed: daysAgo(2), at: [30, 47] },
    { stream: "glass_green", where: "Baldeplatz", count: 1, lastConfirmed: daysAgo(25), at: [58, 26] },
    { stream: "textiles", where: "Kolumbusplatz", count: 1, lastConfirmed: daysAgo(150), at: [70, 62] },
    { stream: "packaging", where: "Auenstraße 3", count: 3, lastConfirmed: daysAgo(1), at: [42, 68] },
    { stream: "residual", where: "Fraunhoferstraße", count: 5, lastConfirmed: daysAgo(4), at: [63, 48] },
  ],
  draft: [
    { stream: "bio", where: "Rathausplatz 4", count: 5, lastConfirmed: daysAgo(25), at: [26, 40] },
    { stream: "paper", where: "Rathausplatz 4", count: 2, lastConfirmed: daysAgo(25), at: [33, 50] },
    { stream: "glass_green", where: "Amanstraße", count: 1, lastConfirmed: daysAgo(150), at: [60, 28] },
    { stream: "packaging", where: "Egger Straße 3", count: 3, lastConfirmed: daysAgo(80), at: [45, 70] },
    { stream: "textiles", where: "Bahnhofstraße 12", count: 1, lastConfirmed: daysAgo(25), at: [72, 60] },
    { stream: "unknown", where: "Grabengasse", count: 1, lastConfirmed: null, at: [55, 55] },
  ],
  none: [],
};

/* The contributor review queue. Publishing a rule needs agreement; entering the
   training set needs a person. Different blast radii, and the panel says so. */
export type QueueState = "pending" | "ready" | "disputed";

export interface QueueEntry {
  id: string;
  form: FormFactor;
  where: string;
  seenKey: string;
  agree: number;
  state: QueueState;
  colors: { color: BinColor; part: "lid" | "body" }[];
}

export const QUEUE: QueueEntry[] = [
  {
    id: "c-4192",
    form: "igloo",
    where: "Grabengasse",
    seenKey: "queue.hours4",
    agree: 1,
    state: "pending",
    colors: [{ color: "green", part: "body" }],
  },
  {
    id: "c-4188",
    form: "textile_bank",
    where: "Bahnhofstraße 12",
    seenKey: "queue.yesterday",
    agree: 2,
    state: "ready",
    colors: [
      { color: "white", part: "body" },
      { color: "blue", part: "lid" },
    ],
  },
  {
    id: "c-4171",
    form: "wheelie_small",
    where: "Amanstraße 9",
    seenKey: "queue.days3",
    agree: 1,
    state: "disputed",
    colors: [
      { color: "grey", part: "lid" },
      { color: "black", part: "body" },
    ],
  },
  {
    id: "c-4160",
    form: "wall_unit",
    where: "Luitpoldplatz",
    seenKey: "queue.days6",
    agree: 3,
    state: "ready",
    colors: [{ color: "red", part: "body" }],
  },
];

/* The shapes a contributor can choose from. Structured all the way down: no
   free text anywhere, so nothing submitted needs translating or moderating for
   language. Ordered by how often they are met, not by the taxonomy's order. */
export const CONTRIBUTE_FORMS: { id: FormFactor; icon: string }[] = [
  { id: "wheelie_small", icon: "package" },
  { id: "wheelie_large", icon: "trash-2" },
  { id: "igloo", icon: "cylinder" },
  { id: "textile_bank", icon: "shirt" },
  { id: "street_basket", icon: "trash" },
  { id: "wall_unit", icon: "battery" },
];
