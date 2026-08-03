/* The live loop's transport.

   Two details carry most of the behaviour on screen.

   `waking` is a real state, not a nicety. The inference service is a free-tier
   HF Space; a cold one takes seconds to answer its first request, and during
   those seconds a socket that says "connecting" is lying about which of the two
   slow things is happening. So an open that has not completed within
   WAKING_AFTER_MS announces itself as waking, and the interface says the
   service is starting up rather than implying the user's signal is bad.

   Reconnection is silent up to a point and then honest. The socket retries with
   jittered backoff and stays in `connecting`; once it has failed past
   GIVE_UP_AFTER attempts it reports `offline`, which is a designed state with
   its own copy and its own still-working list. */

import { metrics, now } from "@/perf/metrics";
import { BaseClient, InFlightError, TransportError, backoffMs } from "./client";
import type { DetectRequest, DetectResponse, ServerMessage } from "./protocol";
import { encodeFrameMessage, isError } from "./protocol";

const WAKING_AFTER_MS = 900;
const GIVE_UP_AFTER = 4;
const RESPONSE_TIMEOUT_MS = 15_000;

interface Pending {
  seq: number;
  resolve: (response: DetectResponse) => void;
  reject: (error: Error) => void;
  timer: number;
  sentAt: number;
}

export interface SocketOptions {
  url: string;
  /** Injectable so tests drive a fake without a server. */
  factory?: (url: string) => WebSocket;
}

export class SocketClient extends BaseClient {
  private socket: WebSocket | null = null;
  private pending: Pending | null = null;
  private opening: Promise<void> | null = null;
  private attempt = 0;
  private closed = false;
  private wakingTimer = 0;

  constructor(private readonly options: SocketOptions) {
    super();
  }

  async connect(): Promise<void> {
    if (this.socket?.readyState === WebSocket.OPEN) return;
    if (this.opening) return this.opening;
    this.closed = false;
    this.opening = this.open();
    try {
      await this.opening;
    } finally {
      this.opening = null;
    }
  }

  private open(): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const startedAt = now();
      this.setState("connecting");

      // A cold Space is a different sentence from a bad signal. Say which.
      this.wakingTimer = window.setTimeout(() => this.setState("waking"), WAKING_AFTER_MS);

      let socket: WebSocket;
      try {
        socket = this.options.factory ? this.options.factory(this.options.url) : new WebSocket(this.options.url);
      } catch (error) {
        window.clearTimeout(this.wakingTimer);
        this.setState("offline");
        reject(error instanceof Error ? error : new Error(String(error)));
        return;
      }
      socket.binaryType = "arraybuffer";
      this.socket = socket;

      socket.onopen = () => {
        window.clearTimeout(this.wakingTimer);
        metrics.sample("net.connect", now() - startedAt);
        this.attempt = 0;
        this.setState("live");
        resolve();
      };

      socket.onmessage = (event) => this.receive(event);

      socket.onerror = () => {
        // onclose always follows, and carries the information worth acting on.
      };

      socket.onclose = () => {
        window.clearTimeout(this.wakingTimer);
        this.socket = null;
        this.failPending(new TransportError("connection closed"));
        if (this.closed) return;
        this.attempt += 1;
        if (this.attempt > GIVE_UP_AFTER) {
          this.setState("offline");
          reject(new TransportError("connection closed"));
          return;
        }
        this.setState("connecting");
        window.setTimeout(() => {
          if (!this.closed) void this.connect();
        }, backoffMs(this.attempt));
        reject(new TransportError("connection closed"));
      };
    });
  }

  private receive(event: MessageEvent): void {
    let message: ServerMessage;
    try {
      const raw = typeof event.data === "string" ? event.data : new TextDecoder().decode(event.data as ArrayBuffer);
      message = JSON.parse(raw) as ServerMessage;
    } catch {
      return;
    }

    const pending = this.pending;
    if (!pending) return;

    if (isError(message)) {
      // A sequence-less error is about the connection, not about this frame.
      if (message.seq != null && message.seq !== pending.seq) return;
      if (message.retry_after_ms) this.setState("busy");
      this.settle(null, new TransportError(message.error, message.retry_after_ms));
      return;
    }

    if (message.seq !== pending.seq) return; // A straggler from before a reset.

    const rtt = now() - pending.sentAt;
    metrics.sample("net.rtt", rtt);
    metrics.sample("net.server", message.ms);
    metrics.sample("net.overhead", Math.max(0, rtt - message.ms));
    if (this.state === "busy") this.setState("live");
    this.settle(message, null);
  }

  private settle(response: DetectResponse | null, error: Error | null): void {
    const pending = this.pending;
    if (!pending) return;
    this.pending = null;
    window.clearTimeout(pending.timer);
    if (response) pending.resolve(response);
    else pending.reject(error ?? new TransportError("unknown transport failure"));
  }

  private failPending(error: Error): void {
    this.settle(null, error);
  }

  detect(request: DetectRequest, jpeg: Uint8Array): Promise<DetectResponse> {
    if (this.pending) return Promise.reject(new InFlightError());
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new TransportError("socket is not open"));
    }

    return new Promise<DetectResponse>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        // A server that never answers is worse than one that says no: it holds
        // the single in-flight slot for ever and the loop stops dead.
        this.settle(null, new TransportError("no answer from the service"));
      }, RESPONSE_TIMEOUT_MS);

      this.pending = { seq: request.seq, resolve, reject, timer, sentAt: now() };
      try {
        socket.send(encodeFrameMessage(request, jpeg));
      } catch (error) {
        this.settle(null, error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  close(): void {
    this.closed = true;
    window.clearTimeout(this.wakingTimer);
    this.failPending(new TransportError("client closed"));
    this.socket?.close();
    this.socket = null;
    this.setState("offline");
  }
}
