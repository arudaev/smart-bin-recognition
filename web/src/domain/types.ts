/* Domain types. This module imports no framework – it is the one layer that
   must stay testable without a browser, because it is the piece most likely to
   be quietly wrong.

   These mirror ml/src/sbr/taxonomy.py. The docs are the specification, not
   either implementation: docs/02-waste-taxonomy.md. */

export const UNKNOWN_STREAM = "unknown";

/** Physical shapes the detector is trained on. Order is the ONNX class index. */
export type FormFactor =
  | "wheelie_small"
  | "wheelie_large"
  | "igloo"
  | "underground"
  | "textile_bank"
  | "street_basket"
  | "sack"
  | "crate"
  | "wall_unit"
  | "container_bank";

/** Measured from pixels, never learnt, never authored by the interface. */
export type BinColor =
  | "blue"
  | "green"
  | "brown"
  | "black"
  | "grey"
  | "yellow"
  | "orange"
  | "red"
  | "white"
  | "transparent"
  | "metal";

export type StreamId = string;

export type RegionStatus = "draft" | "published" | "deprecated";

/** What the device saw: one detected bin, before interpretation. */
export interface Observation {
  form_factor: FormFactor;
  body_color?: BinColor | null;
  lid_color?: BinColor | null;
  aperture_color?: BinColor | null;
  text_hint?: string | null;
}

/* The shape in data/taxonomy/region-pack.schema.json. `options` are stream ids;
   the swatch beside each one is the stream's own typical colour, looked up from
   the taxonomy – the pack does not restate colours it does not own. */
export interface Disambiguation {
  prompt_key: string;
  options: StreamId[];
  note_key?: string;
}

/** One appearance-to-stream mapping within a region. */
export interface Rule {
  id: string;
  match: Partial<Record<keyof Observation, string[]>>;
  stream: StreamId;
  confidence: number;
  local_name?: string | null;
  requires_disambiguation?: boolean;
  disambiguation?: Disambiguation | null;
}

/** What an observation means in a given region. */
export interface Resolution {
  stream: StreamId;
  confidence: number;
  local_name?: string | null;
  rule_id?: string | null;
  requires_disambiguation: boolean;
  disambiguation?: Disambiguation | null;
}

export interface RegionSource {
  name: string;
  url?: string;
  retrieved?: string;
}

export interface RegionPack {
  region_id: string;
  pack_version: string;
  taxonomy_version: string;
  status: RegionStatus;
  name: string;
  country: string;
  rules: Rule[];
  local_names?: Record<StreamId, string>;
  sources?: RegionSource[];
}
