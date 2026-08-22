import type { Locale } from "@/i18n";
import { AVAILABLE_LOCALES } from "@/i18n";
import type { Mode } from "./theme";
import { MODES } from "./theme";

/* What survives a reload.
 *
 * Three facts, one key. Somebody who taps the sunlight button while standing in
 * front of a bin should not find paper mode again after the service worker
 * hands them a new build, and somebody who chose Arabic should not have to
 * choose it twice.
 *
 * Every touch of localStorage is wrapped. It throws – not returns null, throws –
 * when storage is partitioned, when cookies are blocked, and inside some
 * in-app browsers, and reading it happens on the boot path. A display
 * preference must never be the reason the app does not start.
 *
 * Stored values are validated rather than trusted. This key outlives the build
 * that wrote it, so a locale that has since been withdrawn is a thing that can
 * genuinely be in there.
 */

const KEY = "sbr.prefs";

/* WHICH SURFACE, WHEN THE DEVICE CANNOT BE ASKED.
 *
 * `auto` is the capability probe, and it is right about capability: this device
 * has a camera facing away, or it does not. What no API reports is POSTURE - a
 * Surface Pro with two cameras is a scanner by every measurable fact and a
 * laptop on a desk by every practical one, and it changes between the two
 * several times a day without the page reloading.
 *
 * Orientation is not the missing signal either. `web/CONVENTIONS.md` is right
 * that a phone in landscape is still a scanner, so "landscape means desk" would
 * be wrong for the device this product is actually written for.
 *
 * So posture is a preference. The probe still decides the DEFAULT, and it still
 * refuses to promote a device with no camera - `surfaceFor` will not hand the
 * scanner to a tier that cannot feed it. This only records that a person chose
 * otherwise, so the choice survives the reload that used to undo it. */
export type SurfacePreference = "auto" | "scanner" | "viewer";

export const SURFACE_PREFERENCES: SurfacePreference[] = ["auto", "scanner", "viewer"];

export interface Preferences {
  mode: Mode;
  locale: Locale;
  /** First run has been through once, so "/" stops asking on every launch. */
  onboarded: boolean;
  surface: SurfacePreference;
}

export const DEFAULT_PREFERENCES: Preferences = { mode: "paper", locale: "en", onboarded: false, surface: "auto" };

/** The two methods used here, so a test can supply a storage that throws. */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function browserStorage(): StorageLike | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    // Reaching for the property is itself what throws when storage is blocked.
    return null;
  }
}

export function readPreferences(storage: StorageLike | null = browserStorage()): Preferences {
  let raw: string | null;
  try {
    raw = storage?.getItem(KEY) ?? null;
  } catch {
    return DEFAULT_PREFERENCES;
  }
  if (!raw) return DEFAULT_PREFERENCES;

  try {
    const stored = JSON.parse(raw) as Partial<Preferences>;
    return {
      mode: MODES.includes(stored.mode as Mode) ? (stored.mode as Mode) : DEFAULT_PREFERENCES.mode,
      locale: AVAILABLE_LOCALES.includes(stored.locale as Locale)
        ? (stored.locale as Locale)
        : DEFAULT_PREFERENCES.locale,
      onboarded: stored.onboarded === true,
      surface: SURFACE_PREFERENCES.includes(stored.surface as SurfacePreference)
        ? (stored.surface as SurfacePreference)
        : DEFAULT_PREFERENCES.surface,
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function writePreferences(preferences: Preferences, storage: StorageLike | null = browserStorage()): void {
  try {
    storage?.setItem(KEY, JSON.stringify(preferences));
  } catch {
    // Full, blocked, or private. Nothing here is worth an exception on a path
    // that runs every time somebody changes the language.
  }
}
