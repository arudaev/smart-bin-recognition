/* Installing, updating, and knowing whether there is a network.
 *
 * Three rules shape this, and all three are the same rule: the product does not
 * interrupt somebody who is standing in front of a bin.
 *
 * An update is never applied on its own. A worker that calls skipWaiting the
 * moment it activates reloads the page underneath whoever is reading an answer
 * off it, and "the screen changed while I was looking at it" is a worse failure
 * here than being one deployment behind. So a waiting worker raises a flag, the
 * settings screen offers a button, and the swap happens when a person asks.
 *
 * Install is never prompted. `beforeinstallprompt` is captured and its default
 * suppressed, so the browser's own banner does not appear over the camera; the
 * offer lives in settings, where somebody who wants it will look.
 *
 * Listeners are attached at import time, before React mounts, because
 * `beforeinstallprompt` fires once and early and a listener added in an effect
 * misses it on most page loads.
 */

export interface PwaStatus {
  /** Service workers exist on this origin. False on http:// and in some tests. */
  supported: boolean;
  registered: boolean;
  /** A new build is downloaded and waiting for permission to take over. */
  updateReady: boolean;
  /** The shell is cached: this app would now start with no connection. */
  offlineReady: boolean;
  /** The browser offered an install, and we kept the offer. */
  installable: boolean;
  /** Running from a home screen or an app window rather than a tab. */
  installed: boolean;
  online: boolean;
}

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const listeners = new Set<(status: PwaStatus) => void>();

let deferredInstall: BeforeInstallPromptEvent | null = null;
let waiting: ServiceWorker | null = null;
let registration: ServiceWorkerRegistration | null = null;

let status: PwaStatus = {
  supported: typeof navigator !== "undefined" && "serviceWorker" in navigator,
  registered: false,
  updateReady: false,
  offlineReady: false,
  installable: false,
  installed: isStandalone(),
  online: typeof navigator === "undefined" ? true : navigator.onLine,
};

function set(patch: Partial<PwaStatus>): void {
  status = { ...status, ...patch };
  for (const listener of listeners) listener(status);
}

export function pwaStatus(): PwaStatus {
  return status;
}

export function subscribePwa(listener: (status: PwaStatus) => void): () => void {
  listeners.add(listener);
  listener(status);
  return () => listeners.delete(listener);
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  if (window.matchMedia?.("(display-mode: standalone)").matches) return true;
  if (window.matchMedia?.("(display-mode: minimal-ui)").matches) return true;
  // iOS predates display-mode and reports it here instead.
  return (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstall = event as BeforeInstallPromptEvent;
    set({ installable: true });
  });

  window.addEventListener("appinstalled", () => {
    deferredInstall = null;
    set({ installable: false, installed: true });
  });

  window.addEventListener("online", () => set({ online: true }));
  window.addEventListener("offline", () => set({ online: false }));
}

/**
 * Register the worker.
 *
 * Called once from main.tsx, after first paint. Registering earlier competes
 * with the assets the first screen needs on exactly the connection this product
 * assumes is bad.
 */
export async function registerServiceWorker(url = "/sw.js"): Promise<void> {
  if (!status.supported) return;
  if (import.meta.env.DEV) return; // The dev server serves no worker to register.

  try {
    const reg = await navigator.serviceWorker.register(url, { scope: "/", updateViaCache: "none" });
    registration = reg;
    set({ registered: true });

    if (reg.active && !navigator.serviceWorker.controller) {
      // Active but not controlling: this page loaded before the first install
      // finished. It will be controlled on the next navigation.
      set({ offlineReady: true });
    }
    if (navigator.serviceWorker.controller) set({ offlineReady: true });

    if (reg.waiting) {
      waiting = reg.waiting;
      set({ updateReady: true });
    }

    reg.addEventListener("updatefound", () => {
      const installing = reg.installing;
      if (!installing) return;
      installing.addEventListener("statechange", () => {
        if (installing.state !== "installed") return;
        if (navigator.serviceWorker.controller) {
          // Something was already in charge, so this is genuinely an update
          // rather than the first install.
          waiting = installing;
          set({ updateReady: true });
        } else {
          set({ offlineReady: true });
        }
      });
    });

    /* Check for a new build when the app is brought back to the foreground.
       A scanner spends long stretches in the background and `update()` on a
       timer would poll a CDN from a phone in a pocket. */
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") void reg.update().catch(() => {});
    });
  } catch {
    // A worker that will not register is a missing optimisation, not a broken
    // app: everything still works, it just needs the network to start.
    set({ registered: false });
  }
}

/** Swap to the waiting build and reload. Only ever called from a user gesture. */
export function applyUpdate(): void {
  const target = waiting ?? registration?.waiting;
  if (!target) return;

  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloaded) return;
    reloaded = true;
    window.location.reload();
  });
  target.postMessage("skip-waiting");
}

/**
 * Show the browser's install dialog.
 *
 * Returns false when there was nothing to show – Firefox and iOS never fire the
 * event, so the settings screen explains the manual route instead of offering a
 * button that does nothing.
 */
export async function promptInstall(): Promise<boolean> {
  const event = deferredInstall;
  if (!event) return false;
  deferredInstall = null;
  set({ installable: false });
  await event.prompt();
  const { outcome } = await event.userChoice;
  return outcome === "accepted";
}
