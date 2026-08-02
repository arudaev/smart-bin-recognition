import raw from "@taxonomy/waste-streams.json";

import type { BinColor, FormFactor, StreamId } from "@/domain";

/* The ontology, read from the single copy in data/taxonomy/. Adding a stream or
   an item is a change to that file – never to this one.

   The accepted / rejected / common_mistakes lists here are what the rules
   browser and the answer card render. They are properties of the waste stream
   and hold in every jurisdiction; what changes per city is only which container
   the stream lives in, which is the region pack's job. */

export interface RawStream {
  id: StreamId;
  family: string;
  i18n_key: string;
  icon: string;
  typical_colors: BinColor[];
  accepted: string[];
  rejected: string[];
  common_mistakes: string[];
  confusable_with?: string[];
  note_key?: string;
}

export interface RawFormFactor {
  id: FormFactor;
  i18n_key: string;
  capacity_l?: [number, number];
  note?: string;
}

interface RawTaxonomy {
  version: string;
  updated: string;
  colors: { id: BinColor; hex_ref: string }[];
  form_factors: RawFormFactor[];
  families: { id: string; i18n_key: string }[];
  streams: RawStream[];
  items: string[];
}

const taxonomy = raw as unknown as RawTaxonomy;

export const TAXONOMY_VERSION = taxonomy.version;
export const ITEMS = taxonomy.items;
export const COLORS = taxonomy.colors.map((c) => c.id);
export const FORM_FACTORS = taxonomy.form_factors;
export const STREAMS = taxonomy.streams;

const byId = new Map(taxonomy.streams.map((s) => [s.id, s]));
const formById = new Map(taxonomy.form_factors.map((f) => [f.id, f]));

export function streamById(id: StreamId): RawStream | undefined {
  return byId.get(id);
}

export function formFactorById(id: FormFactor): RawFormFactor | undefined {
  return formById.get(id);
}

export interface RuleSet {
  yes: string[];
  no: string[];
  watch: string[];
}

/**
 * The three verdict groups for one stream.
 *
 * `watch` is drawn from common_mistakes and removed from the other two lists,
 * so no item appears twice: an item people habitually get wrong is called out
 * once, in its own group, rather than sitting quietly in a list of six.
 */
export function rulesFor(id: StreamId): RuleSet {
  const s = byId.get(id);
  if (!s) return { yes: [], no: [], watch: [] };
  const watch = new Set(s.common_mistakes);
  return {
    yes: s.accepted.filter((i) => !watch.has(i)),
    no: s.rejected.filter((i) => !watch.has(i)),
    watch: [...watch],
  };
}

/** Item -> stream, for the text-only route. Every rule is reachable without a camera. */
export interface LookupEntry {
  item: string;
  stream: StreamId;
  verdict: "yes" | "watch";
}

export const LOOKUP: LookupEntry[] = taxonomy.streams.flatMap((s) => {
  if (s.id === "unknown") return [];
  const { yes, watch } = rulesFor(s.id);
  return [
    ...yes.map((item) => ({ item, stream: s.id, verdict: "yes" as const })),
    ...watch.map((item) => ({ item, stream: s.id, verdict: "watch" as const })),
  ];
});
