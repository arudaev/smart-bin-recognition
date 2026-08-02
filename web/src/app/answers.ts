import type { Region } from "@/data/regions";
import { localNameFor } from "@/data/regions";
import type { FrameBin } from "@/data/frames";
import type { BinColor, Disambiguation, FormFactor, FreshnessLevel, ResultLevel } from "@/domain";
import { freshnessFrom, isStale, levelOf, resolve } from "@/domain";

/* Turning one detected bin into one answer.

   The resolver does the interpretation; everything here is what the session
   knows on top of it – what the user has already told us, what they have
   confirmed, what they have reported and we have not published. That layering
   matters: a user's own answer outranks a guess, and a user's own report
   outranks nothing at all, because a report is not an answer until a second
   person sees the same thing. */

export type LevelOverride = "auto" | ResultLevel;

export interface ContributionReport {
  form?: FormFactor | null;
  color?: BinColor | null;
  count?: number;
}

export interface SessionState {
  /** Bin number -> the stream the user picked when asked. */
  answered: Record<number, string>;
  /** Bin number -> the user said it is still here. */
  confirmed: Record<number, boolean>;
  /** Bin number -> what the user reported, awaiting a second sighting. */
  pending: Record<number, ContributionReport>;
}

export const EMPTY_SESSION: SessionState = { answered: {}, confirmed: {}, pending: {} };

export type AnswerKind = ResultLevel | "answered" | "pending";

export interface BinAnswer {
  stream: string;
  /** How the card should speak. */
  kind: AnswerKind;
  localName: string | null;
  freshness: FreshnessLevel;
  stale: boolean;
  disambiguation: Disambiguation | null;
  confidence: number;
  report?: ContributionReport;
}

export interface AnswerOptions {
  /** Director override, applied to the lead bin only so a frame stays coherent. */
  level?: LevelOverride;
  /** Director override: age the lead bin so the confirm prompt can be seen. */
  forceStale?: boolean;
  lastConfirmed?: string | null;
}

export function answerFor(
  bin: FrameBin,
  region: Region,
  session: SessionState,
  options: AnswerOptions = {},
): BinAnswer {
  const { level = "auto", forceStale = false, lastConfirmed = null } = options;
  const isLead = bin.n === 1;

  // A report of our own outranks everything: it claims nothing yet.
  const report = session.pending[bin.n];
  if (report) {
    return {
      stream: "unknown",
      kind: "pending",
      localName: null,
      freshness: 0,
      stale: false,
      disambiguation: null,
      confidence: 0,
      report,
    };
  }

  const resolution = resolve(region.pack, bin.observation);
  let kind: AnswerKind = levelOf(resolution);
  let stream = resolution.stream;

  if (isLead && level !== "auto") {
    kind = level;
    if (level === "unknown") stream = "unknown";
  }

  // What the user told us when asked replaces the question, and says who said so.
  const chosen = session.answered[bin.n];
  if (chosen) {
    stream = chosen;
    kind = "answered";
  }

  const confirmedNow = Boolean(session.confirmed[bin.n]);
  let freshness: FreshnessLevel = confirmedNow ? 4 : freshnessFrom(lastConfirmed);
  if (isLead && forceStale && !confirmedNow && stream !== "unknown") freshness = 1;
  if (stream === "unknown") freshness = 0;

  return {
    stream,
    kind,
    localName: stream === "unknown" ? null : localNameFor(region, stream),
    freshness,
    stale: isStale(freshness),
    disambiguation: kind === "ask" ? resolution.disambiguation ?? null : null,
    confidence: resolution.confidence,
  };
}

/** The register the ResultCard should use. `answered` reads as a statement. */
export function cardLevel(kind: AnswerKind): ResultLevel {
  if (kind === "answered" || kind === "pending") return "assert";
  return kind;
}
