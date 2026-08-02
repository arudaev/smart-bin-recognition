import { useEffect, useRef, useState } from "react";

import {
  Button,
  DetectionMarker,
  EmptyState,
  Freshness,
  IconButton,
  ListRow,
  Notice,
  Sheet,
  StatusStrip,
  StreamGlyph,
} from "@/components";
import type { ConnectionState } from "@/components";
import type { BinAnswer, SessionState } from "@/app/answers";
import { answerFor } from "@/app/answers";
import type { AnswerOptions } from "@/app/answers";
import type { Frame, FrameBin } from "@/data/frames";
import { LAST_CONFIRMED } from "@/data/frames";
import type { Region } from "@/data/regions";
import { REGION_ID, REGION_PLACE } from "@/data/regions";
import type { T } from "@/i18n";
import { AnswerPanel } from "@/features/answer/AnswerPanel";

import { CameraOff } from "./CameraOff";

/* THE SCANNER IS NOT A SCREEN YOU LEAVE.

   Answers arrive in a sheet over the live frame, and opening one grows the
   sheet instead of navigating away. The user is holding the phone up against
   the object; a screen change breaks the correspondence between the number on
   the tab and the bin in front of them. "Result" is a state of the scanner, not
   a destination.

   Several bins is not a separate screen either – it is the sheet's ordinary
   state. One bin in frame opens its answer immediately, because 92% of the
   archive is a single bin and the common case should skip the list. */

export type ConnSetting = "auto" | ConnectionState;

interface Props {
  t: T;
  region: Region;
  frame: Frame;
  conn: ConnSetting;
  camera: "granted" | "denied";
  session: SessionState;
  answerOptions: Pick<AnswerOptions, "level" | "forceStale">;
  onBrowse: () => void;
  onContribute: (n: number | null) => void;
  onConfirm: (n: number) => void;
  onAnswer: (n: number, stream: string | null) => void;
  onAllowCamera: () => void;
}

type Phase = "connecting" | "waking" | "searching" | "ready" | "idle";

export function Scanner(p: Props) {
  const { t, region, frame, conn, camera, session, answerOptions } = p;
  const bins = frame.bins.slice(0, frame.count);
  const auto = conn === "auto";

  const [phase, setPhase] = useState<Phase>("connecting");
  const [shown, setShown] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const [sel, setSel] = useState(1);
  const cold = useRef(true);
  const key = `${region.key}/${frame.count}/${camera}`;

  useEffect(() => {
    setOpen(null);
    setSel(1);

    if (camera !== "granted") {
      setPhase("idle");
      setShown(0);
      return;
    }

    if (!auto) {
      if (conn === "live") {
        setPhase("ready");
        setShown(bins.length);
      } else {
        setPhase(conn as Phase);
        setShown(0);
      }
      return;
    }

    /* Plays out in about 1.5 seconds: connect, wake (first time only), search,
       then markers land one at a time. Fast enough to review repeatedly; the
       genuinely slow cold start is reachable from the director panel instead. */
    const timers: number[] = [];
    setPhase("connecting");
    setShown(0);

    const warm = !cold.current;
    let at = 180;
    if (!warm) {
      timers.push(window.setTimeout(() => setPhase("waking"), at));
      at += 420;
    }
    timers.push(window.setTimeout(() => setPhase("searching"), at));
    at += 400;
    bins.forEach((_, i) => timers.push(window.setTimeout(() => setShown(i + 1), at + i * 110)));
    timers.push(
      window.setTimeout(() => {
        setPhase("ready");
        if (bins.length === 1) setOpen(1);
      }, at + bins.length * 110),
    );
    cold.current = false;

    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, auto, conn]);

  const effConn: ConnectionState = auto
    ? phase === "connecting"
      ? "connecting"
      : phase === "waking"
        ? "waking"
        : "live"
    : (conn as ConnectionState);

  const blocked = effConn === "offline" || effConn === "busy" || effConn === "connecting" || effConn === "waking";

  const resolveBin = (b: FrameBin): BinAnswer =>
    answerFor(b, region, session, {
      ...answerOptions,
      lastConfirmed: LAST_CONFIRMED[frame.count]?.[b.n] ?? null,
    });

  if (camera === "denied") {
    return (
      <CameraOff
        t={t}
        region={region}
        onBrowse={p.onBrowse}
        onAllow={p.onAllowCamera}
        onContribute={() => p.onContribute(null)}
      />
    );
  }

  const openBin = open != null ? bins.find((b) => b.n === open) ?? null : null;
  const peekMedia = frame.photo ? 390 : 520;
  const sheetH = open != null ? "84%" : `calc(100% - ${peekMedia}px)`;

  return (
    <div style={{ position: "relative", blockSize: "100%", background: "var(--ink-1)", overflow: "hidden" }}>
      {/* The photograph is the evidence and the interface does not write on it:
          the media box keeps the frame's own aspect, so a marker sits exactly
          over the object rather than over a crop the user cannot see. */}
      <div
        style={{
          position: "absolute",
          insetBlockStart: 0,
          insetInline: 0,
          aspectRatio: frame.aspect,
          overflow: "hidden",
        }}
      >
        {frame.photo ? (
          <img
            src={frame.photo}
            alt=""
            style={{ position: "absolute", inset: 0, inlineSize: "100%", blockSize: "100%", objectFit: "cover" }}
          />
        ) : (
          <CameraPlaceholder />
        )}

        <div style={{ position: "absolute", inset: 0 }}>
          {!blocked &&
            bins.slice(0, shown).map((b) => {
              const a = resolveBin(b);
              return (
                <DetectionMarker
                  key={b.n}
                  index={b.n}
                  rect={b.rect}
                  selected={sel === b.n}
                  state={a.stream === "unknown" ? "unknown" : "found"}
                  label={
                    a.kind === "pending"
                      ? t("pending.title")
                      : a.stream === "unknown"
                        ? t("unknown.title")
                        : t(`stream.${a.stream}`)
                  }
                  onSelect={() => {
                    setSel(b.n);
                    setOpen(b.n);
                  }}
                />
              );
            })}
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          insetBlockStart: "var(--space-3)",
          insetInline: "var(--space-3)",
          display: "grid",
          gap: "var(--space-2)",
        }}
      >
        <StatusStrip state={effConn} message={connMessage(effConn, t, region)} onCamera />
      </div>

      <div
        style={{
          position: "absolute",
          insetBlockStart: 68,
          insetInlineEnd: "var(--space-3)",
          display: "grid",
          gap: "var(--space-2)",
        }}
      >
        <IconButton name="sun" label={t("scan.sunlight")} variant="onCamera" size="outdoor" />
        <IconButton name="list" label={t("scan.browse")} variant="onCamera" size="outdoor" onClick={p.onBrowse} />
      </div>

      <div
        style={{
          position: "absolute",
          insetInline: 0,
          insetBlockEnd: 0,
          blockSize: sheetH,
          transition: "block-size var(--dur-3) var(--ease-out)",
        }}
      >
        <Sheet
          style={{ blockSize: "100%" }}
          peek={open == null}
          register={
            open != null && openBin
              ? `${openBin.n} / ${bins.length} · ${REGION_ID[region.key].toUpperCase()}`
              : `${bins.length} ${t("scan.inView")} · ${REGION_PLACE[region.key]}`
          }
          title={open != null ? undefined : blocked || phase === "searching" ? undefined : t("scan.tapOne")}
          onClose={open != null ? () => setOpen(null) : undefined}
          closeLabel={t("nav.backToCamera")}
        >
          {open != null && openBin ? (
            <AnswerPanel
              bin={openBin}
              answer={resolveBin(openBin)}
              region={region}
              t={t}
              onContribute={() => p.onContribute(openBin.n)}
              onConfirm={p.onConfirm}
              onAnswer={(stream) => p.onAnswer(openBin.n, stream)}
            />
          ) : blocked ? (
            <ConnPanel state={effConn} t={t} region={region} onBrowse={p.onBrowse} />
          ) : phase === "searching" ? (
            <SearchingPanel t={t} />
          ) : !bins.length ? (
            <EmptyState
              icon="camera"
              title={t("scan.nothing")}
              action={
                <Button variant="secondary" icon="search" onClick={p.onBrowse}>
                  {t("scan.browse")}
                </Button>
              }
            >
              {t("scan.nothingBody")}
            </EmptyState>
          ) : (
            <BinList
              bins={bins}
              resolveBin={resolveBin}
              t={t}
              sel={sel}
              frame={frame}
              onOpen={(n) => {
                setSel(n);
                setOpen(n);
              }}
            />
          )}
        </Sheet>
      </div>
    </div>
  );
}

/* Where a real camera stream goes. Hatched rather than black, so an empty
   preview reads as "nothing here yet" and not as a failure. */
function CameraPlaceholder() {
  return (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        background: "var(--paper-3)",
        backgroundImage: "var(--hatch-unknown)",
      }}
    />
  );
}

/* Several bins: a list of names to choose between. No swatch appears here –
   this is not a moment of matching screen to object. */
function BinList({
  bins,
  resolveBin,
  t,
  sel,
  frame,
  onOpen,
}: {
  bins: FrameBin[];
  resolveBin: (b: FrameBin) => BinAnswer;
  t: T;
  sel: number;
  frame: Frame;
  onOpen: (n: number) => void;
}) {
  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div style={{ display: "grid" }}>
        {bins.map((b) => {
          const a = resolveBin(b);
          const unknown = a.stream === "unknown";
          return (
            <ListRow
              key={b.n}
              onClick={() => onOpen(b.n)}
              selected={sel === b.n}
              dense
              leading={
                <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flex: "none" }}>
                  <span
                    style={{
                      inlineSize: 22,
                      blockSize: 22,
                      display: "grid",
                      placeItems: "center",
                      background: "var(--ink-0)",
                      color: "var(--ink-inverse)",
                      borderRadius: "var(--radius-1)",
                      font: "var(--type-register)",
                      fontWeight: "var(--weight-semibold)" as unknown as number,
                    }}
                  >
                    {b.n}
                  </span>
                  <StreamGlyph stream={a.stream} size="sm" tone={unknown ? "unknown" : "plain"} />
                </span>
              }
              title={a.kind === "pending" ? t("pending.short") : t(`stream.${a.stream}`)}
              subtitle={
                a.kind === "pending"
                  ? t("pending.register")
                  : a.kind === "hedge"
                    ? t("hedge.mostLikely")
                    : a.kind === "ask"
                      ? t("ask.title")
                      : unknown
                        ? t(`form.${b.observation.form_factor}`)
                        : a.localName ?? undefined
              }
              trailing={<Freshness level={a.freshness} size="sm" />}
            />
          );
        })}
      </div>

      {!frame.verified ? (
        <Notice tone="quiet" icon="info" title={t("scan.probeTitle")}>
          {t(frame.noteKey)}
        </Notice>
      ) : null}
    </div>
  );
}

function SearchingPanel({ t }: { t: T }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-3)", alignContent: "start" }}>
      <span className="sbr-register">{t("scan.hold")}</span>
      <p style={{ font: "var(--type-body)", color: "var(--text-body)" }}>{t("scan.searching")}</p>
    </div>
  );
}

/* Connection states are ordinary. None of them is an error, so none of them
   gets an error's typography – a sentence, and the thing that still works. */
function ConnPanel({
  state,
  t,
  region,
  onBrowse,
}: {
  state: ConnectionState;
  t: T;
  region: Region;
  onBrowse: () => void;
}) {
  return (
    <div style={{ display: "grid", gap: "var(--space-4)", alignContent: "start" }}>
      <StatusStrip state={state} message={connMessage(state, t, region)} />
      {state === "offline" ? (
        <>
          <div style={{ display: "grid", gap: "var(--space-2)" }}>
            <h3 style={{ font: "var(--type-heading)", color: "var(--text-strong)" }}>{t("scan.offlineTitle")}</h3>
            <p style={{ font: "var(--type-body)", color: "var(--text-muted)" }}>{t("scan.offlineBody")}</p>
          </div>
          <Button size="outdoor" block icon="search" onClick={onBrowse}>
            {t("scan.browse")}
          </Button>
        </>
      ) : (
        <Button variant="secondary" block icon="search" onClick={onBrowse}>
          {t("scan.browse")}
        </Button>
      )}
    </div>
  );
}

export function connMessage(state: ConnectionState, t: T, region: Region): string {
  if (state === "live") return `${t("conn.live")} · ${REGION_PLACE[region.key]}`;
  return t(`conn.${state}`);
}
