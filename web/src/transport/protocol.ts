/* The wire, exactly as docs/01-architecture.md § 4 states it.

   This file is the contract between web/ and service/, and `service/wire.py` is
   its other half. The two are NOT checked by both reading the same paragraph –
   that is how `advice` and `pack_status` came to exist on one side only.
   `scripts/emit-wire-fixtures.mjs` writes fixtures with the encoder below,
   `service/tests/test_wire_contract.py` decodes them and emits responses, and
   `contract.test.ts` reads those back. Both sides are pinned to the same bytes.

   Field names are snake_case because the wire is. Translating them here would
   put the vocabulary in two places and give drift somewhere to hide.

   Strict request-response: the client sends frame `seq` and sends nothing more
   until the server answers `seq`. That is what makes backpressure automatic – a
   slow server throttles the client without either side implementing a rate
   limit, and a queue can never build up because there is never more than one
   frame in flight. */

import type { BinColor, FormFactor, StreamId } from "@/domain";

/** Why the pipeline thinks this detection is worth collecting. */
export type Novelty = "none" | "unknown_type" | "new_region";

export interface WireBox {
  /** Percentages of the frame, so a client can draw without knowing the size. */
  x: number;
  y: number;
  w: number;
  h: number;
}

/** One bin, as the two models and the resolver leave it. */
export interface WireDetection {
  box: WireBox;
  /** Model A. High by design – it answers "is there a bin". */
  validator_conf: number;
  /** Model B, run on model A's crop. Null when B declined to commit. */
  form_factor: FormFactor | null;
  identifier_conf: number;
  body_color: BinColor | null;
  lid_color: BinColor | null;
  aperture_color?: BinColor | null;
  text_hint?: string | null;
  /** Server-side resolve against the region pack. The client re-resolves. */
  stream: StreamId | null;
  stream_conf: number;
  local_name?: string | null;
  novelty: Novelty;
}

export interface DetectRequest {
  seq: number;
  /** geohash-6, about 1.2 km. Enough to pick a jurisdiction, not a household. */
  geohash6: string | null;
  locale: string;
  debug?: boolean;
}

/**
 * What the service is asking the client to do about load.
 *
 * docs/05 § 3's degradation ladder, on the wire, decided by `service/shed.py`.
 * `max_fps` of 0 means *stop streaming and offer a tap* – a designed state with
 * its own copy, not an error and not a spinner. `queue_wait_ms` is the deepest
 * rung and is a **stated** wait, because the one thing the ladder must never do
 * is hold a connection open while pretending to work.
 *
 * **The service may only ever LOWER a cadence.** `MAX_FPS` in capture/gates.ts
 * is a hard ceiling and `Cadence.setMaxFps` clamps against it, so `max_fps: 30`
 * from a compromised or simply wrong server buys nothing. `shed.py` enforces the
 * same rule at its end. Both, deliberately: they are deployed separately, and a
 * gate a server could switch off is not a gate.
 */
export interface LoadAdvice {
  max_fps: number;
  queue_wait_ms?: number;
}

export interface DetectResponse {
  seq: number;
  /** Server-reported inference time. The client's own RTT minus this is transit. */
  ms: number;
  detections: WireDetection[];
  /** Which pack the server resolved against, so a mismatch is visible. */
  region_id?: string | null;
  /** The status of the pack that resolved these detections, so a client that did
   *  not bundle the pack still cannot present a draft as authoritative. */
  pack_status?: string | null;
  /** Absent when the service is not shedding. Absent, not null – see below. */
  advice?: LoadAdvice;
  /** Present only in debug builds: model A's raw boxes before model B ran. */
  debug?: {
    validator_boxes: { box: WireBox; conf: number }[];
    validator_ms: number;
    identifier_ms: number;
  };
}

export interface WireError {
  seq: number | null;
  error: string;
  /** Set when the service is up but shedding load, so the client can back off. */
  retry_after_ms?: number;
  /** Rung 3 carries advice too: a refusal that says nothing about when to come
   *  back is how a queue becomes a stampede. */
  advice?: LoadAdvice;
}

/* ABSENT IS NOT NULL, and the two are not interchangeable here.
   `wire.py:as_wire` omits `advice` and `debug` entirely when they are None, and
   emits `pack_status: null` explicitly. So the optional fields that may arrive
   as an explicit null are typed `?: T | null`, and the ones that are simply
   missing are typed `?: T` with no null alternative. A fixture pins each. */

export type ServerMessage = DetectResponse | WireError;

export function isError(msg: ServerMessage): msg is WireError {
  return "error" in msg;
}

/* Framing. The metadata is JSON and the frame is binary, and putting the JPEG
   through base64 to keep them in one JSON object would cost a third more
   uplink on the one payload that dominates the bill. So: one binary message,
   a 4-byte big-endian header length, the JSON header, then the JPEG bytes. */

const HEADER_BYTES = 4;

export function encodeFrameMessage(request: DetectRequest, jpeg: Uint8Array): ArrayBuffer {
  const header = new TextEncoder().encode(JSON.stringify(request));
  const out = new Uint8Array(HEADER_BYTES + header.byteLength + jpeg.byteLength);
  new DataView(out.buffer).setUint32(0, header.byteLength, false);
  out.set(header, HEADER_BYTES);
  out.set(jpeg, HEADER_BYTES + header.byteLength);
  return out.buffer;
}

export function decodeFrameMessage(buffer: ArrayBuffer): { request: DetectRequest; jpeg: Uint8Array } {
  const view = new DataView(buffer);
  const headerLength = view.getUint32(0, false);
  const bytes = new Uint8Array(buffer);
  const header = new TextDecoder().decode(bytes.subarray(HEADER_BYTES, HEADER_BYTES + headerLength));
  return {
    request: JSON.parse(header) as DetectRequest,
    jpeg: bytes.subarray(HEADER_BYTES + headerLength),
  };
}

/** A detection is only worth drawing if model A is sure something is there. */
export const VALIDATOR_FLOOR = 0.5;

export function usableDetections(response: DetectResponse): WireDetection[] {
  return response.detections.filter((d) => d.validator_conf >= VALIDATOR_FLOOR);
}

/* The identity of a result, for the result lock. Two results are "the same
   sighting" when they found the same number of bins in roughly the same places
   with the same form factors – not when their floats match, which they never
   will. Positions are quantised to 5% of the frame: a hand-held phone drifts
   by more than a pixel and less than a bin. */
export function resultSignature(detections: WireDetection[]): string {
  return detections
    .map((d) => {
      const cx = Math.round((d.box.x + d.box.w / 2) / 5);
      const cy = Math.round((d.box.y + d.box.h / 2) / 5);
      return `${d.form_factor ?? "?"}:${d.body_color ?? "?"}:${d.lid_color ?? "?"}@${cx},${cy}`;
    })
    .sort()
    .join("|");
}
