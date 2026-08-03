/* Getting a frame off the camera and onto the wire as cheaply as possible.

   Two surfaces, allocated once and reused for the life of a scan: a 448 px
   canvas that produces the JPEG, and a 64x64 canvas that produces the luma
   plane the motion gate reads. Allocating either per frame would hand the
   garbage collector four allocations a second on the device least able to
   absorb them, which is exactly the phone this project exists to be kind to.

   448 is not a guess. docs/08-legacy-audit § 7 measured the predecessor's
   detector across four input sizes: 960 px scored mAP50 0.9873 at 406 ms, and
   448 px scored 0.9810 at 174 ms. Six tenths of a point for 2.3x the speed is
   the trade this product wants, and the client's job is to not send more pixels
   than the model will look at. */

import { now } from "@/perf/metrics";
import type { Metrics } from "@/perf/metrics";

/** Longest edge of the frame that leaves the device. */
export const FRAME_EDGE = 448;

/** JPEG quality. 0.7 lands a 448 px street scene around 25-35 kB. */
export const FRAME_QUALITY = 0.7;

/** The motion gate's working resolution. */
export const LUMA_EDGE = 64;

export interface EncodedFrame {
  bytes: Uint8Array;
  width: number;
  height: number;
}

type Surface =
  | { kind: "offscreen"; canvas: OffscreenCanvas; ctx: OffscreenCanvasRenderingContext2D }
  | { kind: "dom"; canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D };

function makeSurface(width: number, height: number): Surface {
  if (typeof OffscreenCanvas !== "undefined") {
    const canvas = new OffscreenCanvas(width, height);
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (ctx) return { kind: "offscreen", canvas, ctx };
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("2d canvas unavailable");
  return { kind: "dom", canvas, ctx };
}

function resize(surface: Surface, width: number, height: number): void {
  if (surface.canvas.width === width && surface.canvas.height === height) return;
  surface.canvas.width = width;
  surface.canvas.height = height;
}

async function toJpeg(surface: Surface, quality: number): Promise<Uint8Array> {
  if (surface.kind === "offscreen") {
    const blob = await surface.canvas.convertToBlob({ type: "image/jpeg", quality });
    return new Uint8Array(await blob.arrayBuffer());
  }
  const blob = await new Promise<Blob | null>((res) => surface.canvas.toBlob(res, "image/jpeg", quality));
  if (!blob) throw new Error("canvas produced no blob");
  return new Uint8Array(await blob.arrayBuffer());
}

/** Fit inside a square of `edge` without distorting, and never upscale. */
export function fitWithin(width: number, height: number, edge: number): { width: number; height: number } {
  if (width <= 0 || height <= 0) return { width: edge, height: edge };
  const scale = Math.min(edge / width, edge / height, 1);
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

export class FrameProcessor {
  private frame: Surface | null = null;
  private small: Surface | null = null;
  private lumaBuffer = new Uint8Array(LUMA_EDGE * LUMA_EDGE);

  constructor(
    private readonly metrics?: Metrics,
    private readonly edge = FRAME_EDGE,
    private readonly quality = FRAME_QUALITY,
  ) {}

  /**
   * The luma plane for the motion gate.
   *
   * Returns a buffer this instance owns and overwrites next call. MotionGate
   * copies what it needs; nothing else should hold on to it.
   */
  luma(source: CanvasImageSource, sourceWidth: number, sourceHeight: number): Uint8Array {
    const t0 = now();
    if (!this.small) this.small = makeSurface(LUMA_EDGE, LUMA_EDGE);
    const s = this.small;
    // Squashed to a square rather than letterboxed: the gate compares a frame
    // to the frame before it, so a consistent distortion cancels out, and
    // avoiding the fit arithmetic keeps this under a millisecond.
    s.ctx.drawImage(source, 0, 0, sourceWidth, sourceHeight, 0, 0, LUMA_EDGE, LUMA_EDGE);
    const { data } = s.ctx.getImageData(0, 0, LUMA_EDGE, LUMA_EDGE);
    const out = this.lumaBuffer;
    for (let i = 0, p = 0; i < out.length; i += 1, p += 4) {
      // Rec. 601 luma, integer-weighted. The gate needs brightness, not colour.
      out[i] = (data[p] * 77 + data[p + 1] * 150 + data[p + 2] * 29) >> 8;
    }
    this.metrics?.sample("capture.gate", now() - t0);
    return out;
  }

  /** Downscale to the model's input size and JPEG-encode. */
  async encode(source: CanvasImageSource, sourceWidth: number, sourceHeight: number): Promise<EncodedFrame> {
    const t0 = now();
    const { width, height } = fitWithin(sourceWidth, sourceHeight, this.edge);
    if (!this.frame) this.frame = makeSurface(width, height);
    resize(this.frame, width, height);
    const f = this.frame;
    f.ctx.drawImage(source, 0, 0, sourceWidth, sourceHeight, 0, 0, width, height);
    const bytes = await toJpeg(f, this.quality);
    this.metrics?.sample("capture.encode", now() - t0);
    return { bytes, width, height };
  }

  /** Release the surfaces. Called when a scan ends, not between frames. */
  dispose(): void {
    if (this.frame?.kind === "dom") this.frame.canvas.remove();
    if (this.small?.kind === "dom") this.small.canvas.remove();
    this.frame = null;
    this.small = null;
    this.lumaBuffer = new Uint8Array(LUMA_EDGE * LUMA_EDGE);
  }
}
