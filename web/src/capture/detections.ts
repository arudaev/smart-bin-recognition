/* Turning what the service saw into what the screens already know how to draw.

   The fixtures in data/frames.ts and a live detection describe the same thing –
   a box on the frame plus the colours measured off the pixels inside it – so
   they become the same type here rather than the screens learning two shapes.
   That is also the honest test of the architecture: if a live detection did not
   fit FrameBin, the fixtures were lying about what the camera produces. */

import type { Frame, FrameBin } from "@/data/frames";
import type { BinColor } from "@/domain";
import type { WireDetection } from "@/transport/protocol";

function quotedFrom(detection: WireDetection): FrameBin["quoted"] {
  const quoted: FrameBin["quoted"] = [];
  // Lid first: it is the part a German bin carries its colour coding on, and
  // the part a user checks first when matching the screen to the object.
  if (detection.lid_color) quoted.push({ color: detection.lid_color as BinColor, part: "lid" });
  if (detection.body_color) quoted.push({ color: detection.body_color as BinColor, part: "body" });
  return quoted;
}

export function binFromDetection(detection: WireDetection, index: number): FrameBin {
  return {
    n: index + 1,
    rect: { x: detection.box.x, y: detection.box.y, w: detection.box.w, h: detection.box.h },
    quoted: quotedFrom(detection),
    observation: {
      // A detection with no form factor is model B declining to commit, which
      // resolves to `unknown` – a designed answer, not a hole to paper over.
      form_factor: detection.form_factor ?? "wheelie_small",
      body_color: detection.body_color ?? null,
      lid_color: detection.lid_color ?? null,
      aperture_color: detection.aperture_color ?? null,
      text_hint: detection.text_hint ?? null,
    },
  };
}

export function binsFromDetections(detections: WireDetection[]): FrameBin[] {
  return detections.map(binFromDetection);
}

/**
 * A live scan wearing the Frame type the screens take.
 *
 * `verified` is true because a live frame is by definition a real one: the
 * unverified-layout notice exists to mark the synthetic six-bin probe in the
 * fixtures, and it would be nonsense over a photograph the user is taking now.
 */
export function liveFrame(detections: WireDetection[], aspect: string): Frame {
  const bins = binsFromDetections(detections);
  return {
    // `count` is a fixture discriminator with three legal values; a live frame
    // holds whatever it holds, so the bins array is the truth and the screens
    // read `bins`, never `count`, for anything that matters.
    count: 1,
    photo: null,
    verified: true,
    noteKey: "frame.singleNote",
    aspect,
    bins,
  };
}

/** Detections whose form factor model B never committed to. Worth collecting. */
export function unidentified(detections: WireDetection[]): WireDetection[] {
  return detections.filter((d) => d.form_factor === null || d.novelty !== "none");
}
