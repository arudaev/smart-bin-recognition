import type { Tier } from "@/capture/capability";

/* THE URL SPACE.
 *
 * Every state the shell can be in has a path, and every path means the same
 * thing to a bookmark, a manifest shortcut, the back button and a cold launch.
 * No framework: this file plus useRoute.ts is the whole router, and it is
 * deliberately free of React and of the DOM so the policy below can be tested
 * without either.
 *
 * The names are `scanner` and `viewer`, never `phone` and `desktop`. That is
 * CONVENTIONS.md's rule about the surfaces, and a URL keeps whatever word it is
 * given for as long as anyone has it in a bookmark.
 */

export type Surface = "scanner" | "viewer";
export type PhoneScreen = "first-run" | "scan" | "rules" | "contribute" | "settings";
export type ViewerView = "map" | "rules" | "queue" | "settings";

export type Route = { surface: "scanner"; screen: PhoneScreen } | { surface: "viewer"; view: ViewerView };

/* `sent` is not here on purpose. It is what the contribute screen shows after a
   report goes in, and a URL somebody can arrive at cold must not claim they
   just sent something. Back from it leads where /contribute was reached from. */
const SCANNER_PATHS: Record<PhoneScreen, string> = {
  "first-run": "/",
  scan: "/scan",
  rules: "/rules",
  contribute: "/contribute",
  settings: "/settings",
};

const VIEWER_PATHS: Record<ViewerView, string> = {
  map: "/viewer",
  rules: "/viewer/rules",
  queue: "/viewer/queue",
  settings: "/viewer/settings",
};

/* Where a scanner path lands on a device that has no camera to point. Contribute
   has no viewer counterpart – reporting a bin is something you do standing in
   front of one – so it falls back to the map rather than to nothing. */
const VIEWER_EQUIVALENT: Record<PhoneScreen, ViewerView> = {
  "first-run": "map",
  scan: "map",
  rules: "rules",
  contribute: "map",
  settings: "settings",
};

export function pathOf(route: Route): string {
  return route.surface === "scanner" ? SCANNER_PATHS[route.screen] : VIEWER_PATHS[route.view];
}

/** The paths by name, so the shell navigates without retyping a literal. */
export const PATH = {
  firstRun: SCANNER_PATHS["first-run"],
  scan: SCANNER_PATHS.scan,
  rules: SCANNER_PATHS.rules,
  contribute: SCANNER_PATHS.contribute,
  settings: SCANNER_PATHS.settings,
  viewer: VIEWER_PATHS.map,
} as const;

/** Trailing slashes are stripped: vercel.json sets `trailingSlash: false`. */
export function normalisePath(pathname: string): string {
  const path = pathname.replace(/\/+$/, "");
  return path === "" ? "/" : path;
}

export function routeOf(pathname: string): Route | null {
  const path = normalisePath(pathname);
  for (const [screen, candidate] of Object.entries(SCANNER_PATHS)) {
    if (candidate === path) return { surface: "scanner", screen: screen as PhoneScreen };
  }
  for (const [view, candidate] of Object.entries(VIEWER_PATHS)) {
    if (candidate === path) return { surface: "viewer", view: view as ViewerView };
  }
  return null;
}

/**
 * Three tiers, two surfaces, so the mapping has to be written down somewhere.
 *
 * Only `viewer` – no getUserMedia, no camera, or permission already denied –
 * gets the viewer. `capture` covers two devices and both want the scanner:
 *
 *   "Camera not enumerated yet"  a real phone that has not been asked for
 *   permission. Safari and Firefox report no devices until a stream has been
 *   opened once, and sending that device to the viewer hides the camera from
 *   exactly the phone this product is written for.
 *
 *   "Only a front-facing camera"  a laptop. The scanner already draws a state
 *   for it and `capability.reason` exists to be read; the viewer would hide the
 *   explanation instead of giving it.
 */
export function surfaceFor(tier: Tier): Surface {
  return tier === "viewer" ? "viewer" : "scanner";
}

export interface Where {
  tier: Tier;
  /** First run has been through once, so "/" stops asking. */
  onboarded: boolean;
}

export interface Placement {
  route: Route;
  /** Non-null when the address bar is wrong. Always applied with replaceState. */
  redirect: string | null;
}

function landing(surface: Surface, onboarded: boolean): Route {
  if (surface === "viewer") return { surface: "viewer", view: "map" };
  return { surface: "scanner", screen: onboarded ? "scan" : "first-run" };
}

function place(pathname: string, where: Where): Route {
  const surface = surfaceFor(where.tier);
  const asked = routeOf(pathname);

  if (!asked) return landing(surface, where.onboarded);

  /* A scanner-tier device asking for the viewer gets the viewer. It is a real
     surface at every width now, and reviewing it from a phone is legitimate. */
  if (asked.surface === "viewer") return asked;

  if (surface === "viewer") return { surface: "viewer", view: VIEWER_EQUIVALENT[asked.screen] };

  if (asked.screen === "first-run" && where.onboarded) return { surface: "scanner", screen: "scan" };

  /* THE CAMERA DOES NOT OPEN BEFORE THE EXPLANATION.
     Arriving at /scan starts getUserMedia, and first run is where this product
     says what it does with the frames: step 2 is the privacy notice, step 3 is
     the camera and the button that asks for it. A shared link, a bookmark or a
     home-screen shortcut must not be a way round that, so an un-onboarded
     device asking for the scanner is sent to the beginning - once, since
     FirstRun sets the flag on either exit.
     Only /scan. /rules and /contribute open no camera and are legitimate places
     to arrive cold; bouncing somebody off a rules link would be an obstacle
     rather than a disclosure. */
  if (asked.screen === "scan" && !where.onboarded) return { surface: "scanner", screen: "first-run" };

  return asked;
}

/**
 * Which route a path means here, and whether the address bar has to be corrected.
 *
 * Takes the full `Tier` rather than a surface somebody narrowed on the way in,
 * so `surfaceFor` is applied in one place a test can reach.
 */
export function resolveRoute(pathname: string, where: Where): Placement {
  const route = place(pathname, where);
  const path = pathOf(route);
  return { route, redirect: path === normalisePath(pathname) ? null : path };
}
