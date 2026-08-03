import { describe, expect, it } from "vitest";

import type { FrameBin } from "@/data/frames";
import type { Region } from "@/data/regions";
import type { RegionPack } from "@/domain";
import { EMPTY_SESSION, answerFor, cardLevel } from "./answers";
import type { SessionState } from "./answers";

/* The resolver decides what a bin is. This decides what to say about it once
   the session knows things the resolver does not: what the user has already
   been asked and answered, what they have confirmed is still there, and what
   they have reported that nobody has corroborated.

   The layering is the whole content of this module, and it is an ordering of
   trust rather than of recency. A user's own answer outranks a guess. A user's
   own report outranks nothing at all, because a report is not an answer until
   a second person has seen the same thing. */

const pack: RegionPack = {
  region_id: "de-by-test",
  pack_version: "1.0.0",
  taxonomy_version: "1.0.0",
  status: "published",
  name: "Testhausen",
  country: "DE",
  local_names: { bio: "Biotonne", residual: "Restmülltonne", glass_mixed: "Altglas" },
  sources: [{ name: "Test", url: "https://example.test", retrieved: "2026-01-01" }],
  rules: [
    {
      id: "t-bio",
      match: { form_factor: ["wheelie_small"], lid_color: ["brown"] },
      stream: "bio",
      confidence: 0.95,
    },
    {
      id: "t-residual-hedge",
      match: { form_factor: ["wheelie_small"], lid_color: ["grey"] },
      stream: "residual",
      confidence: 0.6,
    },
    {
      id: "t-glass",
      match: { form_factor: ["igloo"] },
      stream: "glass_mixed",
      confidence: 0.9,
      requires_disambiguation: true,
      disambiguation: {
        prompt_key: "ask.title",
        options: ["glass_clear", "glass_green", "glass_brown"],
      },
    },
  ],
};

const region: Region = { key: "published", pack, bins: 10, operator: "Test", checkedKey: "provenance.retrieved" };
const noPack: Region = { key: "none", pack: null, bins: 0, operator: null, checkedKey: null };

const bin = (n: number, over: Partial<FrameBin["observation"]> = {}): FrameBin => ({
  n,
  rect: { x: 0, y: 0, w: 10, h: 10 },
  quoted: [],
  observation: { form_factor: "wheelie_small", lid_color: "brown", body_color: "brown", ...over },
});

const session = (over: Partial<SessionState> = {}): SessionState => ({ ...EMPTY_SESSION, ...over });

describe("answerFor", () => {
  it("states a confident rule plainly", () => {
    const answer = answerFor(bin(1), region, session());
    expect(answer.stream).toBe("bio");
    expect(answer.kind).toBe("assert");
    expect(answer.localName).toBe("Biotonne");
  });

  it("hedges a rule the pack is not sure about", () => {
    const answer = answerFor(bin(1, { lid_color: "grey" }), region, session());
    expect(answer.stream).toBe("residual");
    expect(answer.kind).toBe("hedge");
  });

  it("asks rather than hedging when the pack says a question is required", () => {
    // A glass bank with three colour-coded slots is not a low-confidence guess.
    // It is a question, and the two read differently on screen.
    const answer = answerFor(bin(1, { form_factor: "igloo", lid_color: null }), region, session());
    expect(answer.kind).toBe("ask");
    expect(answer.disambiguation?.options).toEqual(["glass_clear", "glass_green", "glass_brown"]);
  });

  it("says unknown where there is no pack, rather than guessing from shape", () => {
    const answer = answerFor(bin(1), noPack, session());
    expect(answer.stream).toBe("unknown");
    expect(answer.kind).toBe("unknown");
    expect(answer.localName).toBeNull();
    // Nothing has been confirmed about a bin nobody has any rules for.
    expect(answer.freshness).toBe(0);
  });

  it("replaces the question with what the user said, and marks who said it", () => {
    const answer = answerFor(bin(1, { form_factor: "igloo" }), region, session({ answered: { 1: "glass_green" } }));
    expect(answer.stream).toBe("glass_green");
    expect(answer.kind).toBe("answered");
  });

  it("lets a report outrank everything, and lets it claim nothing", () => {
    // Submitted and not published: visible to the person who sent it, and to
    // nobody else. It shows what they reported, not a stream.
    const answer = answerFor(bin(1), region, session({ pending: { 1: { form: "igloo", color: "green" } } }));
    expect(answer.kind).toBe("pending");
    expect(answer.stream).toBe("unknown");
    expect(answer.report).toEqual({ form: "igloo", color: "green" });
    expect(answer.freshness).toBe(0);
  });

  it("fills the freshness the moment a user confirms the bin is still there", () => {
    const answer = answerFor(bin(1), region, session({ confirmed: { 1: true } }), { lastConfirmed: "2020-01-01" });
    expect(answer.freshness).toBe(4);
    expect(answer.stale).toBe(false);
  });

  it("asks for a confirmation when the registry copy has gone quiet", () => {
    const answer = answerFor(bin(1), region, session(), { lastConfirmed: "2020-01-01" });
    expect(answer.freshness).toBe(1);
    expect(answer.stale).toBe(true);
  });

  it("treats a bin nobody has ever confirmed as level 0, not as stale", () => {
    // Level 0 means nobody has claimed this bin is here. That is a different
    // sentence from "last seen in March", and the card says a different thing.
    const answer = answerFor(bin(1), region, session(), { lastConfirmed: null });
    expect(answer.freshness).toBe(0);
    expect(answer.stale).toBe(false);
  });

  it("applies a director override to the lead bin only, so a frame stays coherent", () => {
    const lead = answerFor(bin(1), region, session(), { level: "unknown" });
    const second = answerFor(bin(2), region, session(), { level: "unknown" });
    expect(lead.kind).toBe("unknown");
    expect(lead.stream).toBe("unknown");
    expect(second.kind).toBe("assert");
    expect(second.stream).toBe("bio");
  });

  it("never reports an unknown bin as fresh, whatever the registry said", () => {
    const answer = answerFor(bin(1), noPack, session(), { lastConfirmed: new Date().toISOString() });
    expect(answer.freshness).toBe(0);
  });
});

describe("cardLevel", () => {
  it("reads a user's own answer as a statement, not as a question", () => {
    expect(cardLevel("answered")).toBe("assert");
    expect(cardLevel("pending")).toBe("assert");
  });

  it("passes a resolver level through unchanged", () => {
    expect(cardLevel("hedge")).toBe("hedge");
    expect(cardLevel("ask")).toBe("ask");
    expect(cardLevel("unknown")).toBe("unknown");
  });
});
