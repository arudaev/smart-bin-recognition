/* The four gates, as pure logic.

   AGENTS.md calls these load-bearing infrastructure rather than polish, and
   means it: docs/05-cost-model.md makes inference concurrency the binding
   constraint, so a client that streams whenever it can is not a slightly
   worse client, it is one user eating a third of the service. Frames are
   expensive; not sending them is free.

   Nothing here touches a camera, a socket or a clock it did not receive as an
   argument. That is what makes the policy testable, and the policy is the part
   that is easy to get quietly wrong. */

/* ---- 1. Motion and stability ------------------------------------------- */

/** Mean absolute luma difference above which a scene counts as changed. */
export const MOTION_THRESHOLD = 3.5;

/**
 * A cheap luma diff on a 64x64 downsample.
 *
 * Absolute mean difference rather than anything cleverer: it costs one pass
 * over 4096 bytes, it is immune to the JPEG noise a smarter metric would chase,
 * and the only decision it has to support is "send or reuse".
 */
export class MotionGate {
  private previous: Uint8Array | null = null;
  private lastDiff = 0;

  constructor(private readonly threshold = MOTION_THRESHOLD) {}

  /** True when the scene changed enough to be worth a frame. */
  changed(luma: Uint8Array): boolean {
    const prev = this.previous;
    // Copy: the caller owns a reused buffer, and keeping a reference to it
    // would compare a frame against itself for ever.
    this.previous = luma.slice();

    if (!prev || prev.length !== luma.length) {
      this.lastDiff = Number.POSITIVE_INFINITY;
      return true;
    }

    let total = 0;
    for (let i = 0; i < luma.length; i += 1) {
      total += Math.abs(luma[i] - prev[i]);
    }
    this.lastDiff = total / luma.length;
    return this.lastDiff > this.threshold;
  }

  /** How different the last frame was. Reported in debug mode. */
  get difference(): number {
    return this.lastDiff;
  }

  reset(): void {
    this.previous = null;
    this.lastDiff = 0;
  }
}

/* ---- 2. Cadence cap ----------------------------------------------------- */

/** Never more than this many frames per second, whatever the network allows. */
export const MAX_FPS = 4;

/**
 * The cadence cap, which a loaded service may tighten and may never loosen.
 *
 * docs/05 § 3's ladder lets the service ask for 2 fps when its queue is deep,
 * so the interval cannot be `readonly` any more. What must not follow from that
 * is a cap the server controls: `MAX_FPS` is clamped against here, so `max_fps:
 * 30` from a server that is wrong, misconfigured or hostile buys exactly
 * nothing. `service/shed.py` enforces the same rule at its end and neither side
 * trusts the other to, because they are deployed separately – a client running
 * against a service six weeks ahead of it is the ordinary case, not the
 * exotic one.
 */
export class Cadence {
  private lastAt = Number.NEGATIVE_INFINITY;
  private minIntervalMs: number;
  private readonly floorMs: number;

  constructor(minIntervalMs = 1000 / MAX_FPS) {
    // Whatever this was constructed with is the fastest it will ever go. A test
    // that builds a slower Cadence gets a slower ceiling, not a licence to be
    // sped up to 4 fps by a response.
    this.minIntervalMs = minIntervalMs;
    this.floorMs = minIntervalMs;
  }

  /**
   * Apply the service's advice. Lowering only.
   *
   * `fps` of 0 is not this class's problem: "stop streaming and offer a tap" is
   * a scan-level decision, and the loop handles it by stopping with reason
   * `"shed"`. Anything at or below zero is ignored here rather than producing an
   * infinite interval that would silently wedge the loop.
   */
  setMaxFps(fps: number): void {
    if (!Number.isFinite(fps) || fps <= 0) return;
    this.minIntervalMs = Math.max(this.floorMs, 1000 / fps);
  }

  /**
   * Forget any advice and go back to the ceiling.
   *
   * Rungs are not sticky. A service that has stopped sending advice has stopped
   * shedding, and a client that stayed at 2 fps for the rest of the session
   * after one busy moment would be costing its user answers for nothing.
   */
  clearAdvice(): void {
    this.minIntervalMs = this.floorMs;
  }

  /** The interval currently in force. Read by the debug overlay and the tests. */
  get intervalMs(): number {
    return this.minIntervalMs;
  }

  ready(now: number): boolean {
    return now - this.lastAt >= this.minIntervalMs;
  }

  /** Record that a frame went out. Only the sender calls this. */
  mark(now: number): void {
    this.lastAt = now;
  }

  /** How long until the next frame is allowed. Drives the loop's timer. */
  waitFor(now: number): number {
    return Math.max(0, this.minIntervalMs - (now - this.lastAt));
  }

  /* A new scan is not bound by advice about a load that may long since have
     passed, so the interval goes back to the ceiling along with the clock. */
  reset(): void {
    this.lastAt = Number.NEGATIVE_INFINITY;
    this.minIntervalMs = this.floorMs;
  }
}

/* ---- 3. Result lock ----------------------------------------------------- */

/** Identical results in a row before the scan stops streaming. */
export const LOCK_STREAK = 3;

/**
 * The single biggest saving in the whole client.
 *
 * A scan is a task with an end. Once the same identification has held across
 * three consecutive results the answer is presented and the socket goes quiet –
 * the user can stand in front of the bin reading the rules for a minute without
 * costing anything. Motion unlocks it again, because pointing somewhere else is
 * a new question.
 */
export class ResultLock {
  private signature: string | null = null;
  private streak = 0;
  private locked = false;

  constructor(private readonly required = LOCK_STREAK) {}

  /** Feed one result. Returns true once the lock closes. */
  push(signature: string): boolean {
    if (signature === this.signature) {
      this.streak += 1;
    } else {
      this.signature = signature;
      this.streak = 1;
    }
    if (this.streak >= this.required) this.locked = true;
    return this.locked;
  }

  get isLocked(): boolean {
    return this.locked;
  }

  get held(): number {
    return this.streak;
  }

  /** The scene moved. Whatever was agreed is no longer about this scene. */
  release(): void {
    this.locked = false;
    this.streak = 0;
    this.signature = null;
  }
}

/* ---- 4. Hard stops ------------------------------------------------------ */

/** Give up on live streaming after this long without a confident result. */
export const ABORT_MS = 20_000;

/**
 * Why the loop stopped sending.
 *
 * `shed` is the service asking, rather than anything about this scan: docs/05
 * § 3's rung 2, where streaming is off and one tap still works. It is kept
 * distinct from `timeout` because the two are different sentences to a person
 * standing in front of a bin – "nothing held still long enough from this angle"
 * is about them, and "busy right now" is about us. They share an affordance and
 * must not share an explanation.
 */
export type StopReason = "locked" | "timeout" | "hidden" | "offline" | "stopped" | "shed";

/**
 * Whether the loop should still be running.
 *
 * Timeout is not a failure state on screen – docs/00 and the design both treat
 * falling back to tap-to-scan as an ordinary outcome. It is a hard stop here
 * because twenty seconds of streaming that has not converged is twenty seconds
 * of paying for a question the model cannot answer from this angle.
 */
export function shouldAbort(startedAt: number, now: number, limitMs = ABORT_MS): boolean {
  return now - startedAt >= limitMs;
}

/* ---- The policy the loop actually asks ---------------------------------- */

export interface GateInput {
  now: number;
  startedAt: number;
  /** The scene changed since the last frame we looked at. */
  moved: boolean;
  /** A result is currently agreed across LOCK_STREAK frames. */
  locked: boolean;
  /** Results seen so far in this scan. */
  results: number;
  /** A frame is already in flight; strict request-response forbids a second. */
  inFlight: boolean;
  /** Page is visible and the connection is up. */
  awake: boolean;
}

export type GateVerdict =
  | { send: true }
  | { send: false; reason: "in-flight" | "asleep" | "locked" | "still" | "cadence" | "timeout"; waitMs?: number };

/**
 * One decision, in order of cost.
 *
 * The subtle case is `results < LOCK_STREAK`. A perfectly still scene produces
 * no motion, so a naive motion gate would send exactly one frame and then wait
 * for movement that never comes – and the result lock, which needs three
 * results to close, would never close. Holding a phone steady is the *good*
 * case, so the gate lets frames through until there are enough results to reach
 * a verdict, and only then starts insisting on motion.
 */
export function gate(input: GateInput, cadence: Cadence): GateVerdict {
  if (input.inFlight) return { send: false, reason: "in-flight" };
  if (!input.awake) return { send: false, reason: "asleep" };
  if (shouldAbort(input.startedAt, input.now)) return { send: false, reason: "timeout" };
  if (input.locked) return { send: false, reason: "locked" };

  const converging = input.results < LOCK_STREAK;
  if (!input.moved && !converging) return { send: false, reason: "still" };

  if (!cadence.ready(input.now)) {
    return { send: false, reason: "cadence", waitMs: cadence.waitFor(input.now) };
  }
  return { send: true };
}
