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

export interface Preferences {
  mode: Mode;
  locale: Locale;
  /** First run has been through once, so "/" stops asking on every launch. */
  onboarded: boolean;
}

export const DEFAULT_PREFERENCES: Preferences = { mode: "paper", locale: "en", onboarded: false };

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
