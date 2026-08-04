import { describe, expect, it } from "vitest";

import type { StorageLike } from "./preferences";
import { DEFAULT_PREFERENCES, readPreferences, writePreferences } from "./preferences";

/* localStorage throws – not returns null, throws – when storage is partitioned,
   when cookies are blocked, and inside several in-app browsers. Reading it
   happens on the boot path, so every one of these cases is a case where the app
   either starts in paper mode or does not start at all. */

function memory(initial?: string): StorageLike & { written: string[] } {
  let value = initial ?? null;
  return {
    written: [],
    getItem: () => value,
    setItem(_key, next) {
      value = next;
      this.written.push(next);
    },
  };
}

const hostile: StorageLike = {
  getItem() {
    throw new DOMException("The operation is insecure.", "SecurityError");
  },
  setItem() {
    throw new DOMException("The operation is insecure.", "SecurityError");
  },
};

describe("readPreferences", () => {
  it("round-trips what was written", () => {
    const storage = memory();
    writePreferences({ mode: "night", locale: "ar", onboarded: true }, storage);
    expect(readPreferences(storage)).toEqual({ mode: "night", locale: "ar", onboarded: true });
  });

  it("starts in paper, in English, having asked nothing", () => {
    expect(readPreferences(memory())).toEqual(DEFAULT_PREFERENCES);
    expect(DEFAULT_PREFERENCES).toEqual({ mode: "paper", locale: "en", onboarded: false });
  });

  it("survives storage that throws on read", () => {
    expect(() => readPreferences(hostile)).not.toThrow();
    expect(readPreferences(hostile)).toEqual(DEFAULT_PREFERENCES);
  });

  it("survives having no storage at all", () => {
    expect(readPreferences(null)).toEqual(DEFAULT_PREFERENCES);
  });

  it("survives a value that is not JSON", () => {
    expect(readPreferences(memory("night"))).toEqual(DEFAULT_PREFERENCES);
    expect(readPreferences(memory("{"))).toEqual(DEFAULT_PREFERENCES);
  });

  it("survives JSON that is not a preferences object", () => {
    expect(readPreferences(memory("null"))).toEqual(DEFAULT_PREFERENCES);
    expect(readPreferences(memory("[1,2]"))).toEqual(DEFAULT_PREFERENCES);
  });

  /* The key outlives the build that wrote it. A locale that has since been
     withdrawn, or a mode renamed, is a thing that can genuinely be in there,
     and honouring it would set data-theme to something matching no rule. */
  it("does not trust a mode it no longer has", () => {
    expect(readPreferences(memory('{"mode":"dusk"}')).mode).toBe("paper");
  });

  it("does not trust a locale with no bundle", () => {
    // tr is declared in LOCALES and has no bundle yet: exactly the shape of
    // value a future build could have stored and this one cannot honour.
    expect(readPreferences(memory('{"locale":"tr"}')).locale).toBe("en");
    expect(readPreferences(memory('{"locale":"kl"}')).locale).toBe("en");
  });

  it("keeps the fields it does recognise alongside the ones it does not", () => {
    const stored = readPreferences(memory('{"mode":"sun","locale":"zz","onboarded":true}'));
    expect(stored).toEqual({ mode: "sun", locale: "en", onboarded: true });
  });

  it("treats anything but true as not yet onboarded", () => {
    // Being shown first run twice is a smaller failure than never being shown
    // it, so this one defaults towards asking.
    expect(readPreferences(memory('{"onboarded":"yes"}')).onboarded).toBe(false);
    expect(readPreferences(memory('{"onboarded":1}')).onboarded).toBe(false);
  });
});

describe("writePreferences", () => {
  it("survives storage that throws on write", () => {
    // Full, blocked, or private. It runs every time somebody changes language.
    expect(() => writePreferences(DEFAULT_PREFERENCES, hostile)).not.toThrow();
  });

  it("survives having no storage at all", () => {
    expect(() => writePreferences(DEFAULT_PREFERENCES, null)).not.toThrow();
  });

  it("writes one key", () => {
    const storage = memory();
    writePreferences({ mode: "sun", locale: "de", onboarded: true }, storage);
    expect(storage.written).toHaveLength(1);
    expect(JSON.parse(storage.written[0])).toEqual({ mode: "sun", locale: "de", onboarded: true });
  });
});
