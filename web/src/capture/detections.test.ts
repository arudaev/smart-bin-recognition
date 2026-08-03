import { describe, expect, it } from "vitest";

import { wireDetection } from "@/test/harness";
import { binFromDetection, binsFromDetections, liveFrame, unidentified } from "./detections";

/* A live detection and a fixture describe the same thing – a box on the frame
   plus the colours measured off the pixels inside it. If one needed different
   markup from the other, the fixtures were lying about what the camera
   produces, and every screen built against them would be built on that lie. */

describe("binFromDetection", () => {
  it("numbers bins from one, because the number is what the user reads on the tab", () => {
    const bins = binsFromDetections([wireDetection(), wireDetection()]);
    expect(bins.map((b) => b.n)).toEqual([1, 2]);
  });

  it("quotes the lid before the body", () => {
    // German bins carry their colour coding on the lid, and it is the part a
    // user checks first when matching the screen to the object.
    const bin = binFromDetection(wireDetection({ lid_color: "brown", body_color: "grey" }), 0);
    expect(bin.quoted).toEqual([
      { color: "brown", part: "lid" },
      { color: "grey", part: "body" },
    ]);
  });

  it("quotes nothing it did not measure", () => {
    const bin = binFromDetection(wireDetection({ lid_color: null, body_color: null }), 0);
    expect(bin.quoted).toEqual([]);
    expect(bin.observation.body_color).toBeNull();
    expect(bin.observation.lid_color).toBeNull();
  });

  it("carries the box through unchanged, in percentages of the frame", () => {
    const bin = binFromDetection(wireDetection({ box: { x: 12.5, y: 3, w: 40, h: 60 } }), 0);
    expect(bin.rect).toEqual({ x: 12.5, y: 3, w: 40, h: 60 });
  });

  it("keeps a null colour null rather than inventing one", () => {
    // The resolver refuses to match a constraint against a missing measurement.
    // Substituting a plausible colour here would turn "we did not see" into a
    // confident wrong answer, which is this product's worst failure.
    const bin = binFromDetection(wireDetection({ body_color: null, lid_color: "blue" }), 0);
    expect(bin.observation.body_color).toBeNull();
  });
});

describe("liveFrame", () => {
  it("is always verified, because a live frame is a real one", () => {
    // The unverified-layout notice marks the synthetic six-bin probe in the
    // fixtures. Over a photograph the user is taking now it would be nonsense.
    const frame = liveFrame([wireDetection(), wireDetection(), wireDetection()], "3 / 4");
    expect(frame.verified).toBe(true);
    expect(frame.photo).toBeNull();
    expect(frame.bins).toHaveLength(3);
  });

  it("holds however many bins there are, not one of three fixture counts", () => {
    expect(liveFrame(Array.from({ length: 7 }, () => wireDetection()), "3 / 4").bins).toHaveLength(7);
  });
});

describe("unidentified", () => {
  it("catches a bin the identifier would not commit to", () => {
    const detections = [wireDetection(), wireDetection({ form_factor: null })];
    expect(unidentified(detections)).toHaveLength(1);
  });

  it("catches a bin the pipeline flagged as new, whatever it decided", () => {
    // "confident bin + unknown type" is the highest-value acquisition signal in
    // docs/01-architecture.md § 3, and it survives the identifier being sure.
    const detections = [wireDetection({ novelty: "unknown_type" }), wireDetection({ novelty: "new_region" })];
    expect(unidentified(detections)).toHaveLength(2);
  });

  it("leaves an ordinary answer alone", () => {
    expect(unidentified([wireDetection()])).toHaveLength(0);
  });
});
