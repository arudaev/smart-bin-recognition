/* A camera, a clock and a service, none of them real.

   The scan loop is the piece of this client most worth testing and the piece
   hardest to reach through a browser: reproducing "the lock closed, then the
   user turned around, then the service started shedding load" by hand is not
   something anyone will do twice. So everything the loop touches that it did
   not compute itself – time, scheduling, pixels, the network – arrives as an
   argument, and this file supplies deterministic versions of all four. */

import { BaseClient, TransportError } from "@/transport/client";
import type { DetectRequest, DetectResponse, WireDetection } from "@/transport/protocol";
import type { EncodedFrame } from "@/capture/encode";
import type { FrameEncoder, PixelSource } from "@/capture/loop";

/* ---- clock and scheduler ------------------------------------------------ */

export interface FakeClock {
  now: () => number;
  setTimer: (fn: () => void, ms: number) => number;
  clearTimer: (handle: number) => void;
  /** Run every timer due within `ms`, settling promises between each. */
  advance: (ms: number) => Promise<void>;
  /** Settle the microtask queue without moving the clock. */
  flush: () => Promise<void>;
  readonly time: number;
  readonly pending: number;
}

export function fakeClock(start = 0): FakeClock {
  let clock = start;
  let nextId = 1;
  let tasks: { id: number; at: number; fn: () => void }[] = [];

  const flush = async () => {
    // Twenty turns is far more than the loop's deepest await chain (encode →
    // detect → receive) and costs nothing when the queue is already empty.
    for (let i = 0; i < 20; i += 1) await Promise.resolve();
  };

  const advance = async (ms: number) => {
    const target = clock + ms;
    await flush();
    for (;;) {
      tasks.sort((a, b) => a.at - b.at);
      const next = tasks[0];
      if (!next || next.at > target) break;
      tasks = tasks.slice(1);
      clock = next.at;
      next.fn();
      await flush();
    }
    clock = target;
    await flush();
  };

  return {
    now: () => clock,
    setTimer: (fn, ms) => {
      const id = nextId;
      nextId += 1;
      tasks.push({ id, at: clock + Math.max(0, ms), fn });
      return id;
    },
    clearTimer: (handle) => {
      tasks = tasks.filter((t) => t.id !== handle);
    },
    advance,
    flush,
    get time() {
      return clock;
    },
    get pending() {
      return tasks.length;
    },
  };
}

/* ---- pixels ------------------------------------------------------------- */

export interface FakeSource extends PixelSource {
  /** What the scene looks like, as one number. Change it to turn the phone. */
  scene: number;
  ready: boolean;
}

export function fakeSource(width = 1280, height = 720): FakeSource {
  return { ready: true, scene: 100, width, height, image: {} as CanvasImageSource };
}

export interface FakeEncoder extends FrameEncoder {
  frames: number;
  disposed: boolean;
}

/** Produces a luma plane whose value follows the source's scene number, so a
 *  test turns the phone by assigning to `source.scene`. */
export function fakeEncoder(source: FakeSource, bytes = 30_000): FakeEncoder {
  const encoder: FakeEncoder = {
    frames: 0,
    disposed: false,
    luma() {
      return new Uint8Array(64 * 64).fill(source.scene);
    },
    async encode(): Promise<EncodedFrame> {
      encoder.frames += 1;
      return { bytes: new Uint8Array(bytes), width: 448, height: 252 };
    },
    dispose() {
      encoder.disposed = true;
    },
  };
  return encoder;
}

/* ---- service ------------------------------------------------------------ */

export interface FakeClientOptions {
  /** What to answer with. Called per request, so a test can drift the answer. */
  detections?: (seq: number) => WireDetection[];
  /** Reported server time, and nothing is actually waited for. */
  ms?: number;
}

export class FakeClient extends BaseClient {
  readonly requests: DetectRequest[] = [];
  /** Set to make the next N calls fail, the way a shedding service would. */
  failures = 0;
  failureRetryMs: number | undefined = undefined;
  /** Make the next detect hang until `release()` is called. */
  holdNext = false;
  /** Highest concurrency ever observed. The protocol says this must stay 1. */
  peakInFlight = 0;
  connects = 0;
  closed = false;

  private live = 0;
  private hold: ((value: DetectResponse) => void) | null = null;

  constructor(private readonly options: FakeClientOptions = {}) {
    super();
  }

  async connect(): Promise<void> {
    this.connects += 1;
    this.setState("live");
  }

  detect(request: DetectRequest): Promise<DetectResponse> {
    this.requests.push(request);
    this.live += 1;
    this.peakInFlight = Math.max(this.peakInFlight, this.live);

    // Settled in a `finally` rather than before returning, so a caller that
    // started a second frame inside the same synchronous stretch is counted.
    const done = <T>(promise: Promise<T>) =>
      promise.finally(() => {
        this.live -= 1;
      });

    if (this.failures > 0) {
      this.failures -= 1;
      return done(Promise.reject(new TransportError("the service is busy", this.failureRetryMs)));
    }

    const response: DetectResponse = {
      seq: request.seq,
      ms: this.options.ms ?? 20,
      detections: this.options.detections?.(request.seq) ?? [],
    };

    if (this.holdNext) {
      this.holdNext = false;
      return done(
        new Promise<DetectResponse>((resolve) => {
          this.hold = resolve;
        }),
      );
    }

    return done(Promise.resolve(response));
  }

  release(detections: WireDetection[] = []): void {
    const seq = this.requests[this.requests.length - 1]?.seq ?? 0;
    this.hold?.({ seq, ms: this.options.ms ?? 20, detections });
    this.hold = null;
  }

  close(): void {
    this.closed = true;
    this.setState("offline");
  }
}

/** A plausible detection, so tests say what they are varying and nothing else. */
export function wireDetection(over: Partial<WireDetection> = {}): WireDetection {
  return {
    box: { x: 10, y: 20, w: 30, h: 40 },
    validator_conf: 0.95,
    form_factor: "wheelie_small",
    identifier_conf: 0.88,
    body_color: "black",
    lid_color: "grey",
    stream: null,
    stream_conf: 0,
    novelty: "none",
    ...over,
  };
}
