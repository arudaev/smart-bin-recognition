import { useSyncExternalStore } from "react";

import type { PwaStatus } from ".";
import { pwaStatus, subscribePwa } from ".";

/* One subscription to the install/update/network store.
   `useSyncExternalStore` rather than an effect and a useState: the status is
   read during render by the settings screen and the offline strip, and a store
   that tears between those two would show "offline" in one place and "online"
   in the other on the same frame. */
export function usePwa(): PwaStatus {
  return useSyncExternalStore(subscribePwa, pwaStatus, pwaStatus);
}
