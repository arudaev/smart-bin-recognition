import { describe, expect, it } from "vitest";

import { REGIONS } from "@/data/regions";
import { translator } from "@/i18n";
import { connMessage } from "./Scanner";

/* The one line on the strip over the camera.

   docs/05 § 3 is explicit that the ladder's deepest rung must show a STATED
   wait and "never a spinner that lies", so the copy is the feature here rather
   than a label on one. Tested at this level because Scanner needs a DOM and
   this function does not - and because the thing worth pinning is which
   sentence is chosen, not how it is laid out. */

const t = translator("en");
const region = REGIONS.draft;

describe("connMessage", () => {
  it("names the place when connected, because the answer is jurisdictional", () => {
    expect(connMessage("live", t, region)).toContain("Connected");
    expect(connMessage("live", t, region)).toContain("Deggendorf");
  });

  it("says the plain busy sentence when the service quoted no wait", () => {
    expect(connMessage("busy", t, region)).toBe("Busy just now. Trying again.");
  });

  it("counts the wait when the service quoted a long one", () => {
    expect(connMessage("busy", t, region, 12_000)).toBe("Busy just now. About 12 seconds.");
  });

  it("rounds a wait up, never down", () => {
    // Reading as shorter than it is gets people tapping, which is exactly the
    // behaviour the rung exists to prevent.
    expect(connMessage("busy", t, region, 12_001)).toBe("Busy just now. About 13 seconds.");
    expect(connMessage("busy", t, region, 11_999)).toBe("Busy just now. About 12 seconds.");
  });

  it("describes a short wait rather than counting it", () => {
    /* shed.py's smallest wait rounds to one second, and "about 1 seconds" is a
       bug that appears only under load. A singular key would put English's two
       plural forms into a t() layer with no plural categories, and Arabic - a
       launch locale - has six. Every value below the floor gets a sentence that
       is true without agreeing with a number. */
    for (const ms of [1, 500, 1040, 2000, 4000]) {
      expect(connMessage("busy", t, region, ms)).toBe("Busy just now. A few seconds.");
    }
  });

  it("switches to counting exactly at the floor", () => {
    // 4000 ms is four seconds and is described; one millisecond more rounds to
    // five and is counted. Pinned because an off-by-one here is invisible until
    // somebody reads "about 1 seconds" in production.
    expect(connMessage("busy", t, region, 4000)).toBe("Busy just now. A few seconds.");
    expect(connMessage("busy", t, region, 4001)).toBe("Busy just now. About 5 seconds.");
  });

  it("falls back to the plain sentence when the wait is zero", () => {
    // A refusal quoting no wait at all is how every client that was just
    // refused comes back at once. shed.py guarantees a positive number; this is
    // the client refusing to render a nonsense one if it ever gets through.
    expect(connMessage("busy", t, region, 0)).toBe("Busy just now. Trying again.");
  });

  it("ignores a wait on states that are not busy", () => {
    // Advice can outlive the rung that produced it by a frame. Offline is about
    // the user's connection and must never borrow the service's excuse.
    expect(connMessage("offline", t, region, 4000)).toBe("Offline. The rules still work.");
    expect(connMessage("waking", t, region, 4000)).toBe("Waking the server. About ten seconds.");
  });
});
