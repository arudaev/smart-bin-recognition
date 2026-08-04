import type { Coverage } from "@/data/regions";
import type { ConnSetting } from "@/features/scan/Scanner";

import type { LevelOverride } from "./answers";

/* The seven knobs the state director turns, and what they are when nobody is
 * turning them.
 *
 * They live here rather than in dev/ because the shell holds them either way:
 * in production this object is its defaults and never changes, and the screens
 * cannot tell the difference. Keeping the shape out of dev/ is what lets the
 * whole director module leave the production bundle without App.tsx noticing.
 *
 * `source` is the one that is not really a director setting. The shipped client
 * runs the camera; fixtures exist so that every designed state can be reached
 * by a reviewer with no bin in front of them, and so the screens can be built
 * before service/ answers. A user-facing demo mode is a different question and
 * is not this.
 */

export type Source = "fixtures" | "live";
export type CameraSetting = "granted" | "denied";

export interface DirectorState {
  /** Where the bins come from: the real loop, or data/frames.ts on a timer. */
  source: Source;
  /** Fixtures only – how crowded the played-out frame is. */
  frameCount: 1 | 3 | 6;
  /** Fixtures only – the camera-denied screen without denying the camera. */
  camera: CameraSetting;
  coverage: Coverage;
  /** Force the lead bin's answer level, so every register can be read. */
  level: LevelOverride;
  forceStale: boolean;
  conn: ConnSetting;
}

/** Deggendorf is the one pack that exists, and it is a draft. Say so. */
export const PRODUCTION_DIRECTOR: DirectorState = {
  source: "live",
  frameCount: 3,
  camera: "granted",
  coverage: "draft",
  level: "auto",
  forceStale: false,
  conn: "auto",
};
