/* The service, in-process.

   service/ is empty and will be a FastAPI app on a Hugging Face Space. Until it
   answers, this stands in – and it is not throwaway scaffolding. It is what
   makes the scan loop testable without a network, what makes the director panel
   able to put the interface into `busy` or `offline` on demand, and what lets
   the app be demonstrated on a laptop with no camera and no backend.

   It answers from the same fixtures the prototype drew: `data/frames.ts` holds
   observations measured off real archive photographs, and turning them into
   wire detections keeps one description of what the camera sees rather than two.

   What it deliberately does NOT do is resolve. It returns `stream: null`, the
   way a service that had not yet been given a region pack would, so the client
   is exercised on its own resolver rather than on a server's kindness. */

import { FRAMES } from "@/data/frames";
import type { FrameBin } from "@/data/frames";
import { BaseClient, InFlightError, TransportError } from "./client";
import type { DetectRequest, DetectResponse, Novelty, WireDetection } from "./protocol";

export type MockMode = "live" | "busy" | "offline";

export interface MockConfig {
  /** Which fixture frame the camera is pointed at. */
  count: 1 | 3 | 6;
  /** Server-side inference time to report and to actually wait. */
  latencyMs: number;
  /** Random extra latency, so the result lock is exercised against jitter. */
  jitterMs: number;
  /** First-connect delay, standing in for a cold Space. */
  wakeMs: number;
  mode: MockMode;
}

export const MOCK_DEFAULTS: MockConfig = {
  count: 3,
  latencyMs: 90,
  jitterMs: 40,
  wakeMs: 600,
  mode: "live",
};

/* Box jitter, in percent of the frame. Small enough that resultSignature's 5%
   quantisation still agrees frame to frame – a hand-held phone drifts, and a
   lock that broke on drift would never close. */
const DRIFT = 0.4;

function noveltyFor(bin: FrameBin): Novelty {
  // An orange container matches no rule in any pack that exists. The six-bin
  // probe includes one on purpose, and this is where it becomes a collection
  // candidate rather than just a shrug on screen.
  if (bin.observation.body_color === "orange") return "unknown_type";
  return "none";
}

function toDetection(bin: FrameBin, drift: () => number): WireDetection {
  return {
    box: {
      x: bin.rect.x + drift(),
      y: bin.rect.y + drift(),
      w: bin.rect.w,
      h: bin.rect.h,
    },
    validator_conf: 0.93 + Math.random() * 0.06,
    form_factor: bin.observation.form_factor,
    identifier_conf: 0.78 + Math.random() * 0.18,
    body_color: bin.observation.body_color ?? null,
    lid_color: bin.observation.lid_color ?? null,
    aperture_color: bin.observation.aperture_color ?? null,
    text_hint: bin.observation.text_hint ?? null,
    // The client resolves. See the note at the top of this file.
    stream: null,
    stream_conf: 0,
    novelty: noveltyFor(bin),
  };
}

export class MockClient extends BaseClient {
  private inFlight = false;
  private woken = false;
  config: MockConfig;

  constructor(config: Partial<MockConfig> = {}) {
    super();
    this.config = { ...MOCK_DEFAULTS, ...config };
  }

  async connect(): Promise<void> {
    if (this.config.mode === "offline") {
      this.setState("offline");
      throw new TransportError("no connection");
    }
    this.setState("connecting");
    if (!this.woken && this.config.wakeMs > 0) {
      this.setState("waking");
      await sleep(this.config.wakeMs);
      this.woken = true;
    }
    this.setState(this.config.mode === "busy" ? "busy" : "live");
  }

  async detect(request: DetectRequest, jpeg: Uint8Array): Promise<DetectResponse> {
    if (this.inFlight) throw new InFlightError();
    this.inFlight = true;
    try {
      if (this.config.mode === "offline") {
        this.setState("offline");
        throw new TransportError("no connection");
      }
      if (this.config.mode === "busy") {
        this.setState("busy");
        throw new TransportError("the service is busy", 4000);
      }

      const ms = this.config.latencyMs + Math.random() * this.config.jitterMs;
      await sleep(ms);
      this.setState("live");

      const frame = FRAMES[this.config.count] ?? FRAMES[3];
      const drift = () => (Math.random() - 0.5) * 2 * DRIFT;

      return {
        seq: request.seq,
        ms: Math.round(ms),
        // Reported so the size of what left the device is visible in the
        // metrics panel even when nothing left the device.
        detections: frame.bins.slice(0, frame.count).map((bin) => toDetection(bin, drift)),
        region_id: null,
        debug: request.debug
          ? {
              validator_boxes: frame.bins
                .slice(0, frame.count)
                .map((bin) => ({ box: { ...bin.rect }, conf: 0.95 })),
              validator_ms: Math.round(ms * 0.6),
              identifier_ms: Math.round(ms * 0.3),
            }
          : undefined,
      };
    } finally {
      void jpeg.byteLength;
      this.inFlight = false;
    }
  }

  close(): void {
    this.setState("offline");
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
