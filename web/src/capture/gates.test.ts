import { describe, expect, it } from "vitest";

import {
  ABORT_MS,
  Cadence,
  LOCK_STREAK,
  MAX_FPS,
  MOTION_THRESHOLD,
  MotionGate,
  ResultLock,
  gate,
  shouldAbort,
} from "./gates";
import type { GateInput } from "./gates";

/* AGENTS.md: "Never remove the client-side gates… They are load-bearing
   infrastructure, not polish – without them a single user can consume a third
   of total capacity." These tests are what makes removing one loud. */

const luma = (fill: number) => new Uint8Array(64 * 64).fill(fill);

describe("MotionGate", () => {
  it("passes the first frame – there is nothing to compare it to", () => {
    const motion = new MotionGate();
    expect(motion.changed(luma(120))).toBe(true);
  });

  it("holds an identical scene back", () => {
    const motion = new MotionGate();
    motion.changed(luma(120));
    expect(motion.changed(luma(120))).toBe(false);
    expect(motion.difference).toBe(0);
  });

  it("keeps its own copy of the buffer the caller reuses", () => {
    const motion = new MotionGate();
    // The encoder hands out one buffer and overwrites it every frame. A gate
    // that kept the reference would compare a frame against itself for ever
    // and never send a second frame in a scan.
    const shared = luma(120);
    motion.changed(shared);
    shared.fill(200);
    expect(motion.changed(shared)).toBe(true);
  });

  it("fires just above the threshold and not just below", () => {
    const under = new MotionGate();
    under.changed(luma(100));
    expect(under.changed(luma(100 + Math.floor(MOTION_THRESHOLD)))).toBe(false);

    const over = new MotionGate();
    over.changed(luma(100));
    expect(over.changed(luma(100 + Math.ceil(MOTION_THRESHOLD) + 1))).toBe(true);
  });

  it("treats a resize as a change rather than comparing mismatched buffers", () => {
    const motion = new MotionGate();
    motion.changed(luma(120));
    expect(motion.changed(new Uint8Array(16).fill(120))).toBe(true);
  });
});

describe("Cadence", () => {
  it("caps at MAX_FPS however fast it is asked", () => {
    const cadence = new Cadence();
    expect(cadence.ready(0)).toBe(true);
    cadence.mark(0);

    const interval = 1000 / MAX_FPS;
    expect(cadence.ready(interval - 1)).toBe(false);
    expect(cadence.ready(interval)).toBe(true);
  });

  it("reports how long the loop should wait, never a negative", () => {
    const cadence = new Cadence();
    cadence.mark(1000);
    expect(cadence.waitFor(1000)).toBe(1000 / MAX_FPS);
    expect(cadence.waitFor(9999)).toBe(0);
  });

  /* THE HALF OF THE LADDER THE SERVICE MUST NOT CONTROL.
     docs/05 § 3 lets a loaded service ask for 2 fps, which means the interval
     cannot be readonly any more. What must not come with that is a cap the
     server owns: the gates are load-bearing infrastructure precisely because a
     client that streams whenever it can is one user eating a third of the
     service, and a gate a server could switch off is not a gate. */
  describe("advice from the service", () => {
    it("lowers the cadence when asked", () => {
      const cadence = new Cadence();
      cadence.setMaxFps(2);
      expect(cadence.intervalMs).toBe(500);

      cadence.mark(0);
      expect(cadence.ready(499)).toBe(false);
      expect(cadence.ready(500)).toBe(true);
    });

    it("REFUSES to raise it above MAX_FPS", () => {
      const cadence = new Cadence();
      cadence.setMaxFps(30);
      expect(cadence.intervalMs).toBe(1000 / MAX_FPS);

      cadence.mark(0);
      // 33 ms would be 30 fps. The cap is 250 ms and stays 250 ms.
      expect(cadence.ready(33)).toBe(false);
      expect(cadence.ready(1000 / MAX_FPS)).toBe(true);
    });

    it("refuses to raise it even one frame per second over", () => {
      // The obvious version of this bug is a server asking for 30. The one that
      // would actually ship is a server asking for 5.
      const cadence = new Cadence();
      cadence.setMaxFps(MAX_FPS + 1);
      expect(cadence.intervalMs).toBe(1000 / MAX_FPS);
    });

    it("ignores nonsense rather than wedging the loop", () => {
      // An interval of Infinity would stop the scan for ever, and it would do
      // so silently - the loop would simply never think a frame was due.
      const cadence = new Cadence();
      for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
        cadence.setMaxFps(bad);
        expect(cadence.intervalMs).toBe(1000 / MAX_FPS);
      }
    });

    it("keeps a slower ceiling than the default when it was built with one", () => {
      // Whatever a Cadence was constructed with is the fastest it will ever go.
      // Advice may not talk it up to 4 fps.
      const cadence = new Cadence(1000);
      cadence.setMaxFps(MAX_FPS);
      expect(cadence.intervalMs).toBe(1000);
    });

    it("goes back to the ceiling when the service stops shedding", () => {
      // Rungs are not sticky. A client stuck at 2 fps for the rest of a session
      // after one busy moment is costing its user answers for nothing.
      const cadence = new Cadence();
      cadence.setMaxFps(2);
      cadence.clearAdvice();
      expect(cadence.intervalMs).toBe(1000 / MAX_FPS);
    });

    it("forgets advice on reset, because a new scan is a new question", () => {
      const cadence = new Cadence();
      cadence.setMaxFps(2);
      cadence.reset();
      expect(cadence.intervalMs).toBe(1000 / MAX_FPS);
    });
  });
});

describe("ResultLock", () => {
  it("closes on the third identical result, not the second", () => {
    const lock = new ResultLock();
    expect(lock.push("a")).toBe(false);
    expect(lock.push("a")).toBe(false);
    expect(lock.push("a")).toBe(true);
    expect(lock.isLocked).toBe(true);
    expect(LOCK_STREAK).toBe(3);
  });

  it("restarts the streak when the answer changes", () => {
    const lock = new ResultLock();
    lock.push("a");
    lock.push("a");
    lock.push("b");
    expect(lock.isLocked).toBe(false);
    expect(lock.held).toBe(1);
  });

  it("releases, because pointing somewhere else is a new question", () => {
    const lock = new ResultLock();
    lock.push("a");
    lock.push("a");
    lock.push("a");
    lock.release();
    expect(lock.isLocked).toBe(false);
    expect(lock.push("a")).toBe(false);
  });
});

describe("shouldAbort", () => {
  it("gives up exactly at the limit", () => {
    expect(shouldAbort(0, ABORT_MS - 1)).toBe(false);
    expect(shouldAbort(0, ABORT_MS)).toBe(true);
  });
});

describe("gate", () => {
  const base: GateInput = {
    now: 10_000,
    startedAt: 10_000,
    moved: true,
    locked: false,
    results: 0,
    inFlight: false,
    awake: true,
  };

  it("sends when everything says yes", () => {
    expect(gate(base, new Cadence())).toEqual({ send: true });
  });

  it("never sends a second frame while one is in flight", () => {
    // Strict request-response is what makes backpressure automatic. A gate that
    // allowed two in flight would undo the whole protocol.
    expect(gate({ ...base, inFlight: true }, new Cadence())).toMatchObject({ send: false, reason: "in-flight" });
  });

  it("stops for a backgrounded page before it considers anything else", () => {
    expect(gate({ ...base, awake: false }, new Cadence())).toMatchObject({ send: false, reason: "asleep" });
  });

  it("stops streaming once the lock has closed", () => {
    expect(gate({ ...base, locked: true, results: 3 }, new Cadence())).toMatchObject({
      send: false,
      reason: "locked",
    });
  });

  it("reports the timeout in preference to the lock, so the loop can end the scan", () => {
    const verdict = gate({ ...base, now: base.startedAt + ABORT_MS, locked: true, results: 3 }, new Cadence());
    expect(verdict).toMatchObject({ send: false, reason: "timeout" });
  });

  /* The subtle one, and the reason the gate is a function rather than four ifs
     at the call site. A perfectly still scene produces no motion, so a naive
     motion gate sends one frame and then waits for movement that never comes –
     and the result lock, which needs three results, never closes. Holding a
     phone steady is the GOOD case. */
  it("lets a still scene through until there are enough results to lock", () => {
    const still = { ...base, moved: false };
    expect(gate({ ...still, results: 0 }, new Cadence())).toEqual({ send: true });
    expect(gate({ ...still, results: LOCK_STREAK - 1 }, new Cadence())).toEqual({ send: true });
    expect(gate({ ...still, results: LOCK_STREAK }, new Cadence())).toMatchObject({
      send: false,
      reason: "still",
    });
  });

  it("holds for the cadence cap and says how long", () => {
    const cadence = new Cadence();
    cadence.mark(base.now);
    const verdict = gate(base, cadence);
    expect(verdict).toMatchObject({ send: false, reason: "cadence" });
    if (!verdict.send) expect(verdict.waitMs).toBe(1000 / MAX_FPS);
  });
});
