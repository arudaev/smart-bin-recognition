/* POST /detect – one frame, one answer, no socket.

   docs/01-architecture.md § 4 keeps this alongside the stream for tap-to-scan,
   for uploads, and for any client that cannot hold a socket open. It is also
   what the `capture` device tier uses: a laptop with only a front camera gets
   a still-capture button rather than a live loop, and this is what that button
   talks to.

   Same framing as the socket, so the service parses one wire format. */

import { metrics, now } from "@/perf/metrics";
import { BaseClient, InFlightError, TransportError } from "./client";
import type { DetectRequest, DetectResponse } from "./protocol";
import { encodeFrameMessage } from "./protocol";

export interface RestOptions {
  url: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

export class RestClient extends BaseClient {
  private inFlight = false;

  constructor(private readonly options: RestOptions) {
    super();
  }

  async connect(): Promise<void> {
    // Nothing to open. The state is "live" in the sense the interface means it:
    // a request would go out now. Whether it succeeds is the request's business.
    this.setState("live");
  }

  async detect(request: DetectRequest, jpeg: Uint8Array): Promise<DetectResponse> {
    if (this.inFlight) throw new InFlightError();
    this.inFlight = true;

    const doFetch = this.options.fetchImpl ?? globalThis.fetch;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 20_000);
    const sentAt = now();

    try {
      const response = await doFetch(this.options.url, {
        method: "POST",
        headers: { "content-type": "application/octet-stream" },
        body: encodeFrameMessage(request, jpeg),
        signal: controller.signal,
      });

      if (response.status === 429 || response.status === 503) {
        const retryAfter = Number(response.headers.get("retry-after") ?? 0) * 1000;
        this.setState("busy");
        throw new TransportError("the service is busy", retryAfter || 5000);
      }
      if (!response.ok) {
        throw new TransportError(`service returned ${response.status}`);
      }

      const body = (await response.json()) as DetectResponse;
      const rtt = now() - sentAt;
      metrics.sample("net.rtt", rtt);
      metrics.sample("net.server", body.ms);
      metrics.sample("net.overhead", Math.max(0, rtt - body.ms));
      this.setState("live");
      return body;
    } catch (error) {
      if (error instanceof TransportError) throw error;
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new TransportError("the service did not answer in time");
      }
      this.setState("offline");
      throw new TransportError(error instanceof Error ? error.message : String(error));
    } finally {
      clearTimeout(timer);
      this.inFlight = false;
    }
  }

  close(): void {
    this.setState("offline");
  }
}
