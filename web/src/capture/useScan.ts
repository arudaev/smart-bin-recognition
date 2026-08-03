/* The scan, as React sees it.

   Deliberately thin. Everything that could be got wrong – the gates, the lock,
   the request-response discipline, the twenty-second budget – lives in
   ScanLoop, which has no idea React exists and is tested without it. What is
   left here is lifecycle: probe the device, open the camera, hand the loop a
   video element to read, and make sure that when this unmounts the camera light
   goes out. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { DetectClient } from "@/transport";
import { createClient } from "@/transport";
import type { Capability, Tier } from "./capability";
import { VIEWER, probeCapability } from "./capability";
import type { OpenCamera } from "./camera";
import { CameraDeniedError, openCamera, waitForFrame } from "./camera";
import type { ScanState } from "./loop";
import { ScanLoop, videoSource } from "./loop";

export type CameraStatus = "idle" | "opening" | "open" | "denied" | "unavailable";

export interface UseScanOptions {
  /** False keeps the camera closed – the first-run screen before consent, and
   *  every screen that is not the scanner. */
  enabled: boolean;
  locale: string;
  geohash?: string | null;
  debug?: boolean;
  /** Injectable so a test or the director panel can supply its own service. */
  client?: DetectClient;
}

export interface UseScanResult {
  state: ScanState;
  capability: Capability;
  tier: Tier;
  camera: CameraStatus;
  cameraError: string | null;
  /** Non-null only where the platform exposes a torch. */
  setTorch: ((on: boolean) => Promise<void>) | null;
  videoRef: React.RefObject<HTMLVideoElement>;
  retry: () => void;
  captureOnce: () => void;
  /** Ask for camera permission explicitly, from a user gesture. */
  requestCamera: () => void;
}

const INITIAL: ScanState = {
  phase: "idle",
  connection: "offline",
  detections: [],
  locked: false,
  stopReason: null,
  framesSent: 0,
  results: 0,
  lastError: null,
  debug: null,
};

export function useScan(options: UseScanOptions): UseScanResult {
  const { enabled, locale, geohash = null, debug = false } = options;

  const videoRef = useRef<HTMLVideoElement>(null);
  const loopRef = useRef<ScanLoop | null>(null);
  const cameraRef = useRef<OpenCamera | null>(null);

  const [state, setState] = useState<ScanState>(INITIAL);
  const [capability, setCapability] = useState<Capability>(VIEWER);
  const [camera, setCamera] = useState<CameraStatus>("idle");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [setTorch, setSetTorch] = useState<((on: boolean) => Promise<void>) | null>(null);
  const [attempt, setAttempt] = useState(0);

  /* Read through refs inside the loop rather than closed over, so walking into
     the next jurisdiction or switching language does not tear the loop down. */
  const localeRef = useRef(locale);
  const geohashRef = useRef(geohash);
  const debugRef = useRef(debug);
  localeRef.current = locale;
  geohashRef.current = geohash;
  debugRef.current = debug;

  useEffect(() => {
    let live = true;
    void probeCapability().then((c) => {
      if (live) setCapability(c);
    });
    return () => {
      live = false;
    };
  }, [attempt]);

  const injected = options.client;
  const client = useMemo(
    () => injected ?? createClient(capability.tier).client,
    [injected, capability.tier],
  );

  useEffect(() => {
    if (!enabled) return;
    if (capability.tier === "viewer") return;

    let cancelled = false;
    const video = videoRef.current;
    if (!video) return;

    setCamera("opening");
    setCameraError(null);

    const run = async () => {
      try {
        const opened = await openCamera();
        if (cancelled) {
          opened.stop();
          return;
        }
        cameraRef.current = opened;
        video.srcObject = opened.stream;
        video.muted = true;
        video.playsInline = true;
        await video.play().catch(() => {
          // Autoplay refusal on a muted inline stream is rare and recoverable:
          // waitForFrame still resolves once the decoder produces one.
        });
        await waitForFrame(video);
        if (cancelled) {
          opened.stop();
          return;
        }

        setCamera("open");
        setSetTorch(() => opened.setTorch);

        const loop = new ScanLoop({
          client,
          source: videoSource(video),
          geohash: () => geohashRef.current,
          locale: () => localeRef.current,
          debug: () => debugRef.current,
          onState: setState,
        });
        loopRef.current = loop;
        void loop.start();
      } catch (error) {
        if (cancelled) return;
        if (error instanceof CameraDeniedError) {
          setCamera("denied");
        } else {
          setCamera("unavailable");
        }
        setCameraError(error instanceof Error ? error.message : String(error));
      }
    };

    void run();

    return () => {
      cancelled = true;
      loopRef.current?.dispose();
      loopRef.current = null;
      const video2 = videoRef.current;
      if (video2) video2.srcObject = null;
      cameraRef.current?.stop();
      cameraRef.current = null;
      setSetTorch(null);
      setCamera("idle");
    };
  }, [enabled, capability.tier, client, attempt]);

  /* The camera light must go out when the tab does, and a loop that keeps a
     socket busy for a phone in a pocket is the worst cost in the product. */
  useEffect(() => {
    if (typeof document === "undefined") return;
    const onVisibility = () => loopRef.current?.setVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const retry = useCallback(() => {
    const loop = loopRef.current;
    if (loop) {
      void loop.retry();
      return;
    }
    // No loop means the camera never opened. Re-run the whole effect.
    setAttempt((n) => n + 1);
  }, []);

  const captureOnce = useCallback(() => {
    void loopRef.current?.captureOnce();
  }, []);

  const requestCamera = useCallback(() => setAttempt((n) => n + 1), []);

  return {
    state,
    capability,
    tier: capability.tier,
    camera,
    cameraError,
    setTorch,
    videoRef,
    retry,
    captureOnce,
    requestCamera,
  };
}
