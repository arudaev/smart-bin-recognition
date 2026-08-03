/* The scan loop: the one place the four gates, the encoder, the transport and
   the clock meet.

   It is a plain class rather than a hook on purpose. AGENTS.md calls the gates
   load-bearing infrastructure, and infrastructure that can only be exercised by
   mounting React is infrastructure nobody exercises. Everything here takes its
   clock, its transport and its pixel source as arguments, so the whole policy –
   including the awkward parts, like what happens when the lock closes and the
   user then turns around – runs in a unit test against MockClient with no
   camera, no socket and no DOM.

   The shape of a scan, in one paragraph. Connect. Then, four times a second at
   most: look at a 64x64 luma plane and ask whether the scene moved; ask the
   gate whether a frame is worth sending; if it is, downscale to 448, encode,
   send, and wait for the answer before even considering the next one. Once the
   same answer has held three times, stop sending. Start again when the scene
   moves, because pointing somewhere else is a new question. Give up after
   twenty seconds of not converging and offer a single tap instead. */

import type { ConnectionState } from "@/components";
import { metrics as defaultMetrics, now as defaultNow, ScanTimer } from "@/perf/metrics";
import type { Metrics } from "@/perf/metrics";
import type { DetectClient } from "@/transport/client";
import { InFlightError, TransportError } from "@/transport/client";
import type { DetectResponse, WireDetection } from "@/transport/protocol";
import { resultSignature, usableDetections } from "@/transport/protocol";
import { FrameProcessor } from "./encode";
import type { EncodedFrame } from "./encode";
import type { StopReason } from "./gates";
import { Cadence, MotionGate, ResultLock, gate } from "./gates";

/** How often the loop wakes to reconsider. Well under the 4 fps cadence cap. */
const POLL_MS = 90;

/** Consecutive transport failures before the loop calls itself offline. */
const FAILURES_BEFORE_OFFLINE = 3;

export type ScanPhase =
  | "idle"
  /** The transport is opening, or the service is cold. */
  | "connecting"
  /** Frames are going out and no answer has come back yet. */
  | "searching"
  /** At least one answer is on screen and the loop is still watching. */
  | "ready"
  /** The same answer held three times. Nothing is being sent. */
  | "locked"
  /** Deliberately not running: aborted, hidden, or stopped by the caller. */
  | "stopped";

export interface ScanState {
  phase: ScanPhase;
  connection: ConnectionState;
  /** The most recent usable answer. Held while locked, and across a still scene. */
  detections: WireDetection[];
  locked: boolean;
  /** Set when phase is "stopped", so the interface knows which sentence to use. */
  stopReason: StopReason | null;
  /** Frames actually sent in this scan. Shown in debug, asserted in tests. */
  framesSent: number;
  /** Answers received in this scan. */
  results: number;
  /** Last transport failure, for the debug overlay. Never shown to a user. */
  lastError: string | null;
  debug: DetectResponse["debug"] | null;
}

const IDLE: ScanState = {
  phase: "idle",
  connection: "offline",
  detections: [],
  locked: false,
  stopReason: null,
  framesSent: 0,
  results: 0,
  lastError: null,
  debug: null,
};

/** Whatever the loop is pointed at. A video element in the app; a stub in tests. */
export interface PixelSource {
  /** False while the camera has not produced a decodable frame yet. */
  readonly ready: boolean;
  readonly width: number;
  readonly height: number;
  readonly image: CanvasImageSource;
}

/* Structural rather than the FrameProcessor class, so a test can drive the loop
   with a stub. FrameProcessor has private fields, which makes it nominal to the
   compiler and would force every test to carry a canvas it never draws on. */
export interface FrameEncoder {
  luma(source: CanvasImageSource, sourceWidth: number, sourceHeight: number): Uint8Array;
  encode(source: CanvasImageSource, sourceWidth: number, sourceHeight: number): Promise<EncodedFrame>;
  dispose(): void;
}

export interface ScanLoopOptions {
  client: DetectClient;
  source: PixelSource;
  /** Read fresh on every frame: the user can walk into the next jurisdiction. */
  geohash: () => string | null;
  locale: () => string;
  debug?: () => boolean;
  onState: (state: ScanState) => void;
  /** Injectable so tests run on a fake clock and a fake scheduler. */
  metrics?: Metrics;
  now?: () => number;
  processor?: FrameEncoder;
  setTimer?: (fn: () => void, ms: number) => number;
  clearTimer?: (handle: number) => void;
}

export class ScanLoop {
  private state: ScanState = IDLE;
  private readonly motion: MotionGate;
  private readonly cadence: Cadence;
  private readonly lock: ResultLock;
  private readonly processor: FrameEncoder;
  private readonly metrics: Metrics;
  private readonly now: () => number;
  private readonly setTimer: (fn: () => void, ms: number) => number;
  private readonly clearTimer: (handle: number) => void;

  private timer = 0;
  private running = false;
  private inFlight = false;
  private awake = true;
  private seq = 0;
  private failures = 0;
  /** Start of the current *question*, not of the session. Reset when the lock
   *  releases, because pointing at a different bin restarts the 20 s budget. */
  private startedAt = 0;
  private scan: ScanTimer | null = null;
  private unsubscribe: (() => void) | null = null;

  constructor(private readonly options: ScanLoopOptions) {
    this.metrics = options.metrics ?? defaultMetrics;
    this.now = options.now ?? defaultNow;
    this.setTimer = options.setTimer ?? ((fn, ms) => window.setTimeout(fn, ms));
    this.clearTimer = options.clearTimer ?? ((handle) => window.clearTimeout(handle));
    this.processor = options.processor ?? new FrameProcessor(this.metrics);
    this.motion = new MotionGate();
    this.cadence = new Cadence();
    this.lock = new ResultLock();
  }

  get current(): ScanState {
    return this.state;
  }

  private emit(patch: Partial<ScanState>): void {
    this.state = { ...this.state, ...patch };
    this.options.onState(this.state);
  }

  /** Open the transport and begin. Safe to call on an already-running loop. */
  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;
    this.failures = 0;
    this.seq = 0;
    this.awake = isVisible();
    this.startedAt = this.now();
    this.motion.reset();
    this.cadence.reset();
    this.lock.release();
    this.scan = new ScanTimer(this.metrics);

    this.unsubscribe = this.options.client.subscribe((connection) => {
      if (!this.running) return;
      this.emit({ connection });
    });

    this.emit({
      phase: "connecting",
      stopReason: null,
      lastError: null,
      framesSent: 0,
      results: 0,
      detections: [],
      locked: false,
      debug: null,
    });

    try {
      await this.options.client.connect();
    } catch (error) {
      // A failed connect is not a dead loop: the socket retries underneath, and
      // the interface has a designed state for every rung of that ladder.
      this.note(error);
    }

    if (!this.running) return;
    if (this.state.phase === "connecting") this.emit({ phase: "searching" });
    this.schedule(0);
  }

  /** Stop sending. The transport is left open – reconnecting costs more than idling. */
  stop(reason: StopReason = "stopped"): void {
    if (!this.running) return;
    this.running = false;
    this.clearTimer(this.timer);
    this.timer = 0;
    this.unsubscribe?.();
    this.unsubscribe = null;
    this.scan?.finish();
    this.scan = null;
    this.emit({ phase: "stopped", stopReason: reason });
  }

  /** Release the loop's surfaces. Call when the scanner unmounts, not between scans. */
  dispose(): void {
    this.stop();
    this.processor.dispose();
    this.options.client.close();
  }

  /**
   * The page went to the background, or came back.
   *
   * Hidden is a hard stop rather than a slow one: a phone in a pocket that
   * keeps a socket busy is the worst kind of cost, because nobody is looking at
   * what it bought.
   */
  setVisible(visible: boolean): void {
    if (visible === this.awake) return;
    this.awake = visible;
    if (!this.running) return;
    if (visible) {
      // Coming back is a new question. The scene almost certainly changed, and
      // the twenty seconds spent in a pocket should not count against it.
      this.startedAt = this.now();
      this.motion.reset();
      this.lock.release();
      this.emit({ phase: "searching", locked: false, stopReason: null });
      this.schedule(0);
    } else {
      this.clearTimer(this.timer);
      this.timer = 0;
      this.emit({ phase: "stopped", stopReason: "hidden" });
    }
  }

  /** After a timeout or an abort: try again, from a clean slate. */
  retry(): Promise<void> {
    this.running = false;
    this.clearTimer(this.timer);
    return this.start();
  }

  /**
   * One frame, now, ignoring the motion gate and the cadence cap.
   *
   * This is tap-to-scan: the `capture` tier's only mode, the fallback offered
   * after a twenty-second abort, and what a user gets when they want an answer
   * about a scene the motion gate has decided is not interesting. It still
   * respects request-response – there is never more than one frame in flight.
   */
  async captureOnce(): Promise<void> {
    if (this.inFlight) return;
    if (!this.options.source.ready) return;
    this.startedAt = this.now();
    this.lock.release();
    this.emit({ phase: "searching", locked: false, stopReason: null });
    await this.send();
  }

  private schedule(ms: number): void {
    if (!this.running) return;
    this.clearTimer(this.timer);
    this.timer = this.setTimer(() => {
      this.timer = 0;
      void this.tick();
    }, ms);
  }

  private async tick(): Promise<void> {
    if (!this.running) return;

    const source = this.options.source;
    if (!source.ready || source.width === 0 || source.height === 0) {
      this.schedule(POLL_MS);
      return;
    }

    /* Motion is measured on every tick, including while locked. That is the
       whole point of the lock: it costs nothing to hold, and the thing that
       must release it is the user turning to face something else. */
    const luma = this.processor.luma(source.image, source.width, source.height);
    const moved = this.motion.changed(luma);

    if (moved && this.lock.isLocked) {
      this.lock.release();
      this.startedAt = this.now();
      this.emit({ phase: "searching", locked: false });
    }

    const verdict = gate(
      {
        now: this.now(),
        startedAt: this.startedAt,
        moved,
        locked: this.lock.isLocked,
        results: this.state.results,
        inFlight: this.inFlight,
        awake: this.awake,
      },
      this.cadence,
    );

    if (verdict.send) {
      await this.send();
      this.schedule(POLL_MS);
      return;
    }

    if (verdict.reason === "timeout") {
      // Twenty seconds that did not converge. Not an error – docs/00 and the
      // design both treat falling back to one tap as an ordinary outcome.
      this.stop(this.lock.isLocked ? "locked" : "timeout");
      return;
    }

    this.schedule(verdict.reason === "cadence" ? Math.max(1, verdict.waitMs ?? POLL_MS) : POLL_MS);
  }

  private async send(): Promise<void> {
    const source = this.options.source;
    this.inFlight = true;
    this.seq += 1;
    const seq = this.seq;

    try {
      const frame = await this.processor.encode(source.image, source.width, source.height);
      if (!this.running && seq !== 1) return;

      this.cadence.mark(this.now());
      this.scan?.frameSent(frame.bytes.byteLength);
      this.emit({ framesSent: this.state.framesSent + 1 });

      const response = await this.options.client.detect(
        {
          seq,
          geohash6: this.options.geohash(),
          locale: this.options.locale(),
          debug: this.options.debug?.() ?? false,
        },
        frame.bytes,
      );

      this.failures = 0;
      this.receive(response);
    } catch (error) {
      this.note(error);
    } finally {
      this.inFlight = false;
    }
  }

  private receive(response: DetectResponse): void {
    const detections = usableDetections(response);
    const locked = this.lock.push(resultSignature(detections));

    this.scan?.answered();
    if (locked) this.scan?.locked();

    this.emit({
      detections,
      results: this.state.results + 1,
      locked,
      phase: locked ? "locked" : "ready",
      lastError: null,
      debug: response.debug ?? null,
    });
  }

  private note(error: unknown): void {
    if (error instanceof InFlightError) return; // Caller bug, not a scan event.

    const message = error instanceof Error ? error.message : String(error);
    this.emit({ lastError: message });

    this.failures += 1;
    if (this.failures >= FAILURES_BEFORE_OFFLINE) {
      this.stop("offline");
      return;
    }

    // A service shedding load told us how long to wait. Waiting is the whole
    // cooperation: retrying immediately is how a busy free tier stays busy.
    if (error instanceof TransportError && error.retryAfterMs) {
      this.schedule(error.retryAfterMs);
    }
  }
}

function isVisible(): boolean {
  if (typeof document === "undefined") return true;
  return document.visibilityState !== "hidden";
}

/** A `PixelSource` backed by a `<video>`, which is what the app always uses. */
export function videoSource(video: HTMLVideoElement | null): PixelSource {
  return {
    get ready() {
      return Boolean(video) && video!.readyState >= video!.HAVE_CURRENT_DATA;
    },
    get width() {
      return video?.videoWidth ?? 0;
    },
    get height() {
      return video?.videoHeight ?? 0;
    },
    get image() {
      return video as CanvasImageSource;
    },
  };
}
