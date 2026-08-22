/* Choosing a transport.

   Three exist and the choice is made once, here, from configuration and device
   tier rather than at every call site. `service/` is empty today, so with no
   endpoint configured the app runs against the in-process mock – which is not a
   degraded mode for the client: the loop, the gates, the lock and every screen
   are exercised identically, and only the pixels are imaginary.

   A `capture`-tier device never gets a socket. It has no live loop to feed, so
   holding a connection open would cost the service a slot for a device that
   sends one frame when a button is pressed. */

import type { Tier } from "@/capture/capability";
import type { DetectClient } from "./client";
import { MockClient } from "./mock";
import { RestClient } from "./rest";
import { SocketClient } from "./socket";

export * from "./client";
export * from "./protocol";
export { MockClient, MOCK_DEFAULTS } from "./mock";
export type { MockConfig, MockMode } from "./mock";
export { RestClient } from "./rest";
export { SocketClient } from "./socket";

export interface Endpoints {
  /** wss://…/stream */
  socket?: string;
  /** https://…/detect */
  rest?: string;
}

export function endpoints(): Endpoints {
  const env = import.meta.env;
  return {
    socket: env.VITE_DETECT_WS || undefined,
    rest: env.VITE_DETECT_URL || undefined,
  };
}

export function isConfigured(): boolean {
  const { socket, rest } = endpoints();
  return Boolean(socket || rest);
}

/** Named so the settings screen can say what it is talking to, honestly. */
export type TransportKind = "socket" | "rest" | "mock";

export interface ClientChoice {
  client: DetectClient;
  kind: TransportKind;
}

/* Which transport this device would get, without building one.
 *
 * Two screens ask this question on every render – the settings row, and the
 * scanner's banner, which must not say "Connected" when the answer is `mock`.
 * Constructing a client to ask it its own name is how that used to be done, and
 * it means opening a socket to answer a question about naming. The policy lives
 * here once; `createClient` reads it rather than repeating it. */
export function clientKind(tier: Tier, override?: Endpoints): TransportKind {
  const { socket, rest } = override ?? endpoints();
  if (tier === "scanner" && socket) return "socket";
  if (rest) return "rest";
  if (socket) return "socket";
  return "mock";
}

export function createClient(tier: Tier, override?: Endpoints): ClientChoice {
  const { socket, rest } = override ?? endpoints();
  const kind = clientKind(tier, override);

  if (kind === "socket") return { client: new SocketClient({ url: socket as string }), kind };
  if (kind === "rest") return { client: new RestClient({ url: rest as string }), kind };
  return { client: new MockClient(), kind };
}
