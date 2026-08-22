import { describe, expect, it } from "vitest";

import type { Tier } from "@/capture/capability";
import type { Route } from "./routes";
import { PATH, normalisePath, pathOf, resolveRoute, routeOf, surfaceFor } from "./routes";

/* The router's whole policy is in routes.ts, and it is here rather than in a
   browser because every rule below is a decision rather than a rendering:
   which path means what, which device is sent where, and – the one that is
   quietly load-bearing – whether the correction is a push or a replace. */

const SCANNER: Tier[] = ["scanner", "capture"];

function scanner(screen: Extract<Route, { surface: "scanner" }>["screen"]): Route {
  return { surface: "scanner", screen };
}
function viewer(view: Extract<Route, { surface: "viewer" }>["view"]): Route {
  return { surface: "viewer", view };
}

describe("paths and routes", () => {
  it("round-trips every route through its path", () => {
    const all: Route[] = [
      scanner("first-run"),
      scanner("scan"),
      scanner("rules"),
      scanner("contribute"),
      scanner("settings"),
      viewer("map"),
      viewer("rules"),
      viewer("queue"),
      viewer("settings"),
    ];
    for (const route of all) {
      expect(routeOf(pathOf(route))).toEqual(route);
    }
  });

  it("gives the scanner and the viewer different paths for the same rules", () => {
    // One URL rendering two different screens depending on the device would
    // make a shared link mean something different to whoever opened it.
    expect(pathOf(scanner("rules"))).not.toEqual(pathOf(viewer("rules")));
  });

  it("names the surfaces, not the devices", () => {
    // CONVENTIONS.md: the surfaces are scanner and viewer, never phone and
    // desktop. A URL keeps the word it is given for as long as anyone has it.
    for (const path of Object.values(PATH)) {
      expect(path).not.toMatch(/desk|phone|mobile|desktop/);
    }
  });

  it("ignores a trailing slash", () => {
    expect(normalisePath("/rules/")).toBe("/rules");
    expect(normalisePath("/")).toBe("/");
    expect(routeOf("/viewer/rules/")).toEqual(viewer("rules"));
  });

  it("knows nothing about a path it does not have", () => {
    expect(routeOf("/nope")).toBeNull();
    expect(routeOf("/viewer/nope")).toBeNull();
  });
});

describe("surfaceFor", () => {
  it("gives the viewer only to a device with no camera to point", () => {
    expect(surfaceFor("viewer")).toBe("viewer");
  });

  /* The rule most likely to be "simplified" later by somebody reading `capture`
     as "not a scanner". Both states that produce it want the scanner, and for
     different reasons – see the doc comment on surfaceFor. */
  it("gives `capture` the scanner, from either state that produces it", () => {
    // capability.ts:100 – a real phone that has not been asked for permission,
    // on a browser that enumerates no devices until a stream has been opened.
    expect(surfaceFor("capture")).toBe("scanner");
    // capability.ts:121 – a laptop with only a front-facing camera. The scanner
    // draws a state for it and says why; the viewer would hide the reason.
    expect(surfaceFor("capture")).toBe("scanner");
  });

  it("gives a scanner the scanner", () => {
    expect(surfaceFor("scanner")).toBe("scanner");
  });
});

describe("where a device lands", () => {
  it("opens a fresh scanner on first run", () => {
    for (const tier of SCANNER) {
      const { route, redirect } = resolveRoute("/", { tier, onboarded: false });
      expect(route).toEqual(scanner("first-run"));
      expect(redirect).toBeNull();
    }
  });

  it("stops asking once first run has been through", () => {
    for (const tier of SCANNER) {
      const { route, redirect } = resolveRoute("/", { tier, onboarded: true });
      expect(route).toEqual(scanner("scan"));
      expect(redirect).toBe(PATH.scan);
    }
  });

  it("opens a viewer-tier device on the map, onboarded or not", () => {
    for (const onboarded of [false, true]) {
      const { route, redirect } = resolveRoute("/", { tier: "viewer", onboarded });
      expect(route).toEqual(viewer("map"));
      expect(redirect).toBe(PATH.viewer);
    }
  });

  it("sends an unknown path to the landing rather than to nothing", () => {
    const { route, redirect } = resolveRoute("/rulez", { tier: "scanner", onboarded: true });
    expect(route).toEqual(scanner("scan"));
    expect(redirect).toBe(PATH.scan);
  });
});

describe("a device without a camera", () => {
  const where = { tier: "viewer" as Tier, onboarded: true };

  it("reads the rules on the surface it has", () => {
    const { route, redirect } = resolveRoute(PATH.rules, where);
    expect(route).toEqual(viewer("rules"));
    expect(redirect).toBe("/viewer/rules");
  });

  it("keeps its settings", () => {
    expect(resolveRoute(PATH.settings, where).route).toEqual(viewer("settings"));
  });

  it("falls back to the map where there is no counterpart", () => {
    // Contribute is something you do standing in front of a bin. There is no
    // viewer version, so it lands somewhere real instead of somewhere empty.
    expect(resolveRoute(PATH.contribute, where).route).toEqual(viewer("map"));
    expect(resolveRoute(PATH.scan, where).route).toEqual(viewer("map"));
  });
});

describe("a device with a camera", () => {
  it("is not thrown off the viewer it asked for", () => {
    // The viewer is responsive at every width now, and reviewing it from a
    // phone – or reading the queue on one – is a legitimate thing to do.
    for (const tier of SCANNER) {
      const { route, redirect } = resolveRoute("/viewer/queue", { tier, onboarded: true });
      expect(route).toEqual(viewer("queue"));
      expect(redirect).toBeNull();
    }
  });

  /* A tester was handed a link to /scan and the camera opened on arrival, with
     the privacy notice and the camera explanation - first run's steps 2 and 3 -
     never shown. A shared URL is the ordinary way somebody reaches a beta, so
     that is the ordinary path, not an edge case. */
  it("sends an un-onboarded device to first run before opening a camera", () => {
    for (const tier of ["scanner", "capture"] as Tier[]) {
      const { route, redirect } = resolveRoute(PATH.scan, { tier, onboarded: false });
      expect(route).toEqual({ surface: "scanner", screen: "first-run" });
      expect(redirect).toBe(PATH.firstRun);
    }
  });

  it("lets an un-onboarded device read the rules without being intercepted", () => {
    // These open no camera. Bouncing somebody off a rules link would be an
    // obstacle with nothing to disclose.
    for (const path of [PATH.rules, PATH.contribute, PATH.settings]) {
      expect(resolveRoute(path, { tier: "scanner", onboarded: false }).redirect).toBeNull();
    }
  });

  it("is left alone on every path that is already right", () => {
    for (const path of [PATH.scan, PATH.rules, PATH.contribute, PATH.settings]) {
      expect(resolveRoute(path, { tier: "scanner", onboarded: true }).redirect).toBeNull();
    }
  });
});

describe("redirects", () => {
  it("never asks to be sent where it already is", () => {
    // A redirect equal to the current path is a replaceState in a loop.
    const cases: [string, Tier, boolean][] = [
      ["/", "scanner", false],
      [PATH.scan, "scanner", true],
      [PATH.viewer, "viewer", true],
      ["/viewer/rules", "viewer", true],
    ];
    for (const [path, tier, onboarded] of cases) {
      expect(resolveRoute(path, { tier, onboarded }).redirect).toBeNull();
    }
  });

  it("always names a path the router can parse back", () => {
    const cases: [string, Tier, boolean][] = [
      ["/", "scanner", true],
      ["/", "viewer", false],
      [PATH.rules, "viewer", true],
      ["/nowhere", "viewer", true],
    ];
    for (const [path, tier, onboarded] of cases) {
      const { route, redirect } = resolveRoute(path, { tier, onboarded });
      expect(redirect).not.toBeNull();
      expect(routeOf(redirect!)).toEqual(route);
    }
  });

  it("settles in one hop", () => {
    // Resolving the redirect must not produce another one, or the effect that
    // applies it runs forever.
    const tiers: Tier[] = ["scanner", "capture", "viewer"];
    for (const tier of tiers) {
      for (const onboarded of [false, true]) {
        for (const path of ["/", "/nope", ...Object.values(PATH), "/viewer/queue", "/viewer/settings"]) {
          const first = resolveRoute(path, { tier, onboarded });
          const again = resolveRoute(first.redirect ?? path, { tier, onboarded });
          expect(again.redirect, `${path} on ${tier} did not settle`).toBeNull();
          expect(again.route).toEqual(first.route);
        }
      }
    }
  });
});
