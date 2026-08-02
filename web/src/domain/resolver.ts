import type { Observation, RegionPack, Resolution, Rule } from "./types";
import { UNKNOWN_STREAM } from "./types";

/* The three-axis join: (form factor, measured colour) x region -> stream.
   The device knows the first two; only the region pack knows what they mean.
   No pack, no meaning – and `unknown` is a designed answer, not a failure.

   This is a TypeScript mirror of RegionPack.resolve in
   ml/src/sbr/taxonomy.py. The two must agree; docs/02-waste-taxonomy.md is the
   specification and neither implementation is. */

export const UNRESOLVED: Resolution = {
  stream: UNKNOWN_STREAM,
  confidence: 0,
  local_name: null,
  rule_id: null,
  requires_disambiguation: false,
  disambiguation: null,
};

/** How many constraints a rule imposes. More specific rules win. */
export function specificity(rule: Rule): number {
  return Object.keys(rule.match).length;
}

/**
 * True when every constraint is satisfied by the observation.
 *
 * An observation attribute of null/undefined (not measured) never satisfies a
 * constraint – we do not guess on missing evidence.
 */
export function matches(rule: Rule, observation: Observation): boolean {
  for (const [attribute, allowed] of Object.entries(rule.match)) {
    const value = observation[attribute as keyof Observation];
    if (value == null || !allowed?.includes(value as string)) return false;
  }
  return true;
}

/**
 * Resolve an observation to a stream. Pure and deterministic.
 * Most-specific rule wins; ties broken by confidence, then by file order.
 */
export function resolve(pack: RegionPack | null, observation: Observation): Resolution {
  if (!pack) return UNRESOLVED;

  const candidates = pack.rules
    .map((rule, index) => ({ rule, index }))
    .filter(({ rule }) => matches(rule, observation));

  if (candidates.length === 0) return UNRESOLVED;

  candidates.sort((a, b) => {
    const bySpecificity = specificity(b.rule) - specificity(a.rule);
    if (bySpecificity !== 0) return bySpecificity;
    const byConfidence = b.rule.confidence - a.rule.confidence;
    if (byConfidence !== 0) return byConfidence;
    return a.index - b.index;
  });

  const { rule } = candidates[0];
  return {
    stream: rule.stream,
    confidence: rule.confidence,
    local_name: rule.local_name ?? pack.local_names?.[rule.stream] ?? null,
    rule_id: rule.id,
    requires_disambiguation: rule.requires_disambiguation ?? false,
    disambiguation: rule.disambiguation ?? null,
  };
}

export function isKnown(resolution: Resolution): boolean {
  return resolution.stream !== UNKNOWN_STREAM;
}

/**
 * A pack may only be served to users if every source is traceable.
 *
 * This is the guardrail against the product's worst failure mode: telling
 * someone confidently that the wrong thing goes in the wrong bin.
 */
export function isPublishable(pack: RegionPack): boolean {
  if (!pack.sources || pack.sources.length === 0) return false;
  return pack.sources.every((s) => Boolean(s.url) && Boolean(s.retrieved));
}

/* How the interface should speak a resolution. The threshold is a presentation
   decision, not a resolver one – the resolver reports confidence and says
   whether a question is required; this turns that into a register.

     assert   a statement
     hedge    a qualified statement, with a way to disagree
     ask      a question, with the choices as the body
     unknown  a fourth, fully designed answer

   `requires_disambiguation` outranks confidence: a glass bank with three
   colour-coded slots is not a low-confidence guess, it is a question. */
export type ResultLevel = "assert" | "hedge" | "ask" | "unknown";

export const HEDGE_BELOW = 0.8;

export function levelOf(resolution: Resolution): ResultLevel {
  if (!isKnown(resolution)) return "unknown";
  if (resolution.requires_disambiguation) return "ask";
  return resolution.confidence < HEDGE_BELOW ? "hedge" : "assert";
}
