import { beforeEach, describe, expect, it } from "vitest";

import { Metrics } from "@/perf/metrics";
import { FakeClient, fakeClock, fakeEncoder, fakeSource, wireDetection } from "@/test/harness";
import type { FakeSource } from "@/test/harness";
import { ABORT_MS, LOCK_STREAK, MAX_FPS } from "./gates";
import { ScanLoop } from "./loop";
import type { ScanState } from "./loop";

/* The loop is where the four gates, the encoder, the transport and the clock
   meet, and it is the only place their interaction can be wrong. Everything
   here runs on a fake clock against a fake service, so the awkward sequences –
   the lock closing and then the user turning around, the service shedding load
   mid-scan, the phone going into a pocket – are reachable in a line each. */

const FRAME_INTERVAL = 1000 / MAX_FPS;

interface Rig {
  loop: ScanLoop;
  client: FakeClient;
  source: FakeSource;
  clock: ReturnType<typeof fakeClock>;
  metrics: Metrics;
  states: ScanState[];
  encoder: ReturnType<typeof fakeEncoder>;
  last: () => ScanState;
}

function rig(options: { detections?: (seq: number) => ReturnType<typeof wireDetection>[] } = {}): Rig {
  const clock = fakeClock();
  const source = fakeSource();
  const encoder = fakeEncoder(source);
  const metrics = new Metrics();
  const client = new FakeClient({
    detections: options.detections ?? (() => [wireDetection()]),
  });
  const states: ScanState[] = [];

  const loop = new ScanLoop({
    client,
    source,
    geohash: () => "u1q0rz",
    locale: () => "de",
    debug: () => false,
    onState: (state) => states.push(state),
    metrics,
    now: clock.now,
    processor: encoder,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });

  return { loop, client, source, clock, metrics, states, encoder, last: () => states[states.length - 1] };
}

describe("ScanLoop", () => {
  let r: Rig;
  beforeEach(() => {
    r = rig();
  });

  it("connects, sends a frame, and reports what came back", async () => {
    await r.loop.start();
    await r.clock.advance(0);

    expect(r.client.connects).toBe(1);
    expect(r.client.requests).toHaveLength(1);
    expect(r.last().detections).toHaveLength(1);
    expect(r.last().phase).toBe("ready");
  });

  it("sends the geohash and locale the caller supplies, and nothing else about the user", async () => {
    await r.loop.start();
    await r.clock.advance(0);

    const request = r.client.requests[0];
    expect(request).toEqual({ seq: 1, geohash6: "u1q0rz", locale: "de", debug: false });
    // geohash-6 is about 1.2 km. Anything finer would be a promise broken in
    // the one place docs/01-architecture.md § 7 is most explicit.
    expect(request.geohash6).toHaveLength(6);
  });

  it("never has two frames in flight", async () => {
    await r.loop.start();
    await r.clock.advance(3000);
    expect(r.client.peakInFlight).toBe(1);
  });

  it("holds the next frame until the last has been answered", async () => {
    r.client.holdNext = true;
    await r.loop.start();
    await r.clock.advance(2000);

    // Two seconds is eight frames' worth of cadence. None of them went.
    expect(r.client.requests).toHaveLength(1);

    r.client.release([wireDetection()]);
    await r.clock.advance(FRAME_INTERVAL);
    expect(r.client.requests.length).toBeGreaterThan(1);
  });

  it("locks after three identical answers and stops sending", async () => {
    await r.loop.start();
    await r.clock.advance(FRAME_INTERVAL * (LOCK_STREAK + 1));

    expect(r.last().locked).toBe(true);
    expect(r.last().phase).toBe("locked");
    expect(r.client.requests).toHaveLength(LOCK_STREAK);

    // The user stands there reading the rules. It costs nothing.
    await r.clock.advance(10_000);
    expect(r.client.requests).toHaveLength(LOCK_STREAK);
  });

  it("releases the lock when the scene changes, because that is a new question", async () => {
    await r.loop.start();
    await r.clock.advance(FRAME_INTERVAL * (LOCK_STREAK + 1));
    expect(r.last().locked).toBe(true);
    const sent = r.client.requests.length;

    r.source.scene = 220; // turned to face something else
    await r.clock.advance(FRAME_INTERVAL);

    expect(r.client.requests.length).toBeGreaterThan(sent);
  });

  it("stops sending on a still scene once it has enough results to decide", async () => {
    // Answers that never agree, so the lock cannot be what stops it.
    const drifting = rig({ detections: (seq) => [wireDetection({ box: { x: seq * 20, y: 10, w: 10, h: 10 } })] });
    await drifting.loop.start();
    await drifting.clock.advance(FRAME_INTERVAL * (LOCK_STREAK + 1));

    const sent = drifting.client.requests.length;
    expect(sent).toBe(LOCK_STREAK);

    await drifting.clock.advance(5000);
    expect(drifting.client.requests).toHaveLength(sent);
  });

  it("never exceeds the cadence cap even with a scene that will not sit still", async () => {
    const moving = rig({ detections: (seq) => [wireDetection({ box: { x: seq * 20, y: 10, w: 10, h: 10 } })] });
    await moving.loop.start();

    // One second of continuous movement, sampled far faster than the cap.
    for (let i = 0; i < 20; i += 1) {
      moving.source.scene = 40 + i * 10;
      await moving.clock.advance(50);
    }

    expect(moving.client.requests.length).toBeLessThanOrEqual(MAX_FPS + 1);
  });

  it("gives up after twenty seconds that did not converge, and says why", async () => {
    const moving = rig({ detections: (seq) => [wireDetection({ box: { x: seq * 7, y: 10, w: 10, h: 10 } })] });
    await moving.loop.start();

    for (let i = 0; i < 60; i += 1) {
      moving.source.scene = 40 + ((i * 17) % 200);
      await moving.clock.advance(400);
    }

    expect(moving.clock.time).toBeGreaterThan(ABORT_MS);
    expect(moving.last().phase).toBe("stopped");
    expect(moving.last().stopReason).toBe("timeout");
  });

  it("calls itself offline after three failures in a row", async () => {
    r.client.failures = 3;
    await r.loop.start();
    await r.clock.advance(FRAME_INTERVAL * 4);

    expect(r.last().phase).toBe("stopped");
    expect(r.last().stopReason).toBe("offline");
    expect(r.last().lastError).toContain("busy");
  });

  it("recovers when a failure is followed by an answer", async () => {
    r.client.failures = 2;
    await r.loop.start();
    await r.clock.advance(FRAME_INTERVAL * 4);

    expect(r.last().phase).not.toBe("stopped");
    expect(r.last().detections).toHaveLength(1);
  });

  it("stops when the page is hidden and starts a fresh question when it returns", async () => {
    await r.loop.start();
    await r.clock.advance(FRAME_INTERVAL * (LOCK_STREAK + 1));
    const sent = r.client.requests.length;

    r.loop.setVisible(false);
    await r.clock.advance(10_000);
    expect(r.last().phase).toBe("stopped");
    expect(r.last().stopReason).toBe("hidden");
    expect(r.client.requests).toHaveLength(sent);

    r.loop.setVisible(true);
    await r.clock.advance(FRAME_INTERVAL);
    expect(r.last().locked).toBe(false);
    expect(r.client.requests.length).toBeGreaterThan(sent);
  });

  it("waits for the camera rather than encoding an empty frame", async () => {
    // A video with no decodable frame draws as a transparent rectangle, which
    // the motion gate would read as a perfectly still scene.
    r.source.ready = false;
    await r.loop.start();
    await r.clock.advance(2000);
    expect(r.client.requests).toHaveLength(0);

    r.source.ready = true;
    await r.clock.advance(200);
    expect(r.client.requests).toHaveLength(1);
  });

  it("takes one frame on demand, ignoring the cadence cap", async () => {
    await r.loop.start();
    await r.clock.advance(0);
    const sent = r.client.requests.length;

    await r.loop.captureOnce();
    expect(r.client.requests).toHaveLength(sent + 1);
  });

  it("records what the scan cost", async () => {
    await r.loop.start();
    await r.clock.advance(FRAME_INTERVAL * (LOCK_STREAK + 1));
    r.loop.stop();

    expect(r.metrics.summary("frame.bytes")?.count).toBe(LOCK_STREAK);
    expect(r.metrics.summary("scan.frames")?.max).toBe(LOCK_STREAK);
    expect(r.metrics.summary("scan.bytes")?.max).toBe(LOCK_STREAK * 30_000);
  });

  it("releases the camera surfaces and the transport on dispose", async () => {
    await r.loop.start();
    await r.clock.advance(0);
    r.loop.dispose();

    expect(r.encoder.disposed).toBe(true);
    expect(r.client.closed).toBe(true);
    expect(r.clock.pending).toBe(0);
  });

  it("stops cleanly when nothing was ever sent", async () => {
    r.source.ready = false;
    await r.loop.start();
    r.loop.stop();
    expect(r.last().phase).toBe("stopped");
    expect(r.clock.pending).toBe(0);
  });
});
