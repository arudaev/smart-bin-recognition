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

export class Cadence {
  private lastAt = Number.NEGATIVE_INFINITY;

  constructor(private readonly minIntervalMs = 1000 / MAX_FPS) {}

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

  reset(): void {
    this.lastAt = Number.NEGATIVE_INFINITY;
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

export type StopReason = "locked" | "timeout" | "hidden" | "offline" | "stopped";

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
