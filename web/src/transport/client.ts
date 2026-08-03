/* What the scan loop is allowed to know about the network.

   One interface, three implementations: a WebSocket for the live loop, a POST
   for anything that cannot hold a socket, and an in-process mock so the whole
   client runs – and is tested – before service/ exists. The loop is written
   against this and never against a WebSocket, which is why the loop's tests
   need no network at all. */

import type { ConnectionState } from "@/components";
import type { DetectRequest, DetectResponse } from "./protocol";

export type { ConnectionState };

export interface DetectClient {
  readonly state: ConnectionState;
  /** Open, if this transport has a connection to open. Safe to call twice. */
  connect(): Promise<void>;
  /**
   * Send one frame and wait for its answer.
   *
   * Strict request-response: calling this while a frame is in flight is a bug
   * in the caller, and it throws rather than queueing. A queue here would undo
   * the backpressure the whole protocol is designed around.
   */
  detect(request: DetectRequest, jpeg: Uint8Array): Promise<DetectResponse>;
  close(): void;
  subscribe(listener: (state: ConnectionState) => void): () => void;
}

export class InFlightError extends Error {
  constructor() {
    super("a frame is already in flight");
    this.name = "InFlightError";
  }
}

export class TransportError extends Error {
  constructor(
    message: string,
    readonly retryAfterMs?: number,
  ) {
    super(message);
    this.name = "TransportError";
  }
}

/** Shared state plumbing, so each transport only writes its own transitions. */
export abstract class BaseClient implements DetectClient {
  private current: ConnectionState = "offline";
  private readonly listeners = new Set<(state: ConnectionState) => void>();

  get state(): ConnectionState {
    return this.current;
  }

  protected setState(next: ConnectionState): void {
    if (next === this.current) return;
    this.current = next;
    for (const listener of this.listeners) listener(next);
  }

  subscribe(listener: (state: ConnectionState) => void): () => void {
    this.listeners.add(listener);
    listener(this.current);
    return () => this.listeners.delete(listener);
  }

  abstract connect(): Promise<void>;
  abstract detect(request: DetectRequest, jpeg: Uint8Array): Promise<DetectResponse>;
  abstract close(): void;
}

/** Backoff for reconnects: quick at first, then out of the way. */
export function backoffMs(attempt: number, base = 250, ceiling = 8000): number {
  const flat = Math.min(ceiling, base * 2 ** Math.max(0, attempt - 1));
  // Jitter, because every phone in a dead-spot reconnecting on the same
  // schedule is how a free-tier service gets knocked over on recovery.
  return Math.round(flat * (0.5 + Math.random() * 0.5));
}
