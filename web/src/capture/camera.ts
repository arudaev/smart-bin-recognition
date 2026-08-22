/* Opening the camera, and closing it properly.

   Two things here are easy to get wrong and expensive when you do.

   The first is that a stream left open holds the camera light on. On a phone
   that is a privacy signal the user reads literally – docs/01-architecture.md
   § 7 promises the camera is only on while they are looking, and a track that
   survives a screen change makes that promise false. So every path out of this
   module stops the tracks, and the caller is given one `stop()` that is safe to
   call twice.

   The second is that `facingMode: "environment"` is a hint, not a guarantee.
   Chrome honours it, Safari mostly does, and a laptop with one webcam happily
   returns the front camera and reports success. So the settings that came back
   are inspected rather than assumed, and a stream that turned out to be
   front-facing is reported as such – the interface then offers still capture
   instead of a live loop, which is the `capture` tier in § 5.

   THE THIRD, found on a Surface Pro 11 on 2026-08-21, is that "reported as such"
   was not enough. Windows Chrome and Edge do not populate `facingMode` for UVC
   cameras at all, so on a two-camera tablet the ideal constraint is
   unsatisfiable, `getUserMedia` returns the system default – the SELFIE camera –
   and `facingOf` then reads the label, correctly concludes it got a front
   camera, and demotes a perfectly good scanner to still capture. The diagnosis
   was right and there was nowhere to go with it.

   So there is now a second attempt. Device labels are empty until permission is
   granted, which is why this cannot be done up front: only after the first
   `getUserMedia` resolves can `enumerateDevices` name "Surface Camera Rear".
   When the track we opened is not environment-facing and a device whose label
   says it is exists, we reopen on that `deviceId` and stop the first stream. If
   the reopen fails we keep the first stream rather than leaving the caller with
   nothing – a front camera the user can still point at a bin beats a refusal,
   which is the same reasoning that makes the constraint `ideal` rather than
   `exact`. */

export type Facing = "environment" | "user" | "unknown";

export class CameraDeniedError extends Error {
  constructor() {
    super("camera permission was refused");
    this.name = "CameraDeniedError";
  }
}

export class CameraUnavailableError extends Error {
  constructor(message = "no usable camera on this device") {
    super(message);
    this.name = "CameraUnavailableError";
  }
}

export interface OpenCameraOptions {
  /** Which way the camera should point. Requested, then verified. */
  facing?: "environment" | "user";
  /** Ideal capture size. The frame is downscaled to 448 before it is sent, so
   *  asking for more than this buys nothing but heat on the device. */
  width?: number;
  height?: number;
  /** Injectable for tests. */
  mediaDevices?: MediaDevices;
}

export interface OpenCamera {
  stream: MediaStream;
  track: MediaStreamTrack;
  /** What we actually got, which is not always what was asked for. */
  facing: Facing;
  width: number;
  height: number;
  /** Present only when the platform exposes a torch on this track. */
  setTorch: ((on: boolean) => Promise<void>) | null;
  stop: () => void;
}

const DEFAULT_WIDTH = 1280;
const DEFAULT_HEIGHT = 720;

export async function openCamera(options: OpenCameraOptions = {}): Promise<OpenCamera> {
  const devices = options.mediaDevices ?? (typeof navigator !== "undefined" ? navigator.mediaDevices : undefined);
  if (!devices || typeof devices.getUserMedia !== "function") {
    throw new CameraUnavailableError("this browser has no camera API");
  }

  const facing = options.facing ?? "environment";
  const constraints: MediaStreamConstraints = {
    audio: false,
    video: {
      // `ideal`, not `exact`: an exact constraint on a device with one camera
      // fails outright, and a front camera the user can still point at a bin is
      // better than a refusal.
      facingMode: { ideal: facing },
      width: { ideal: options.width ?? DEFAULT_WIDTH },
      height: { ideal: options.height ?? DEFAULT_HEIGHT },
    },
  };

  let stream: MediaStream;
  try {
    stream = await devices.getUserMedia(constraints);
  } catch (error) {
    throw translateError(error);
  }

  let track = stream.getVideoTracks()[0];
  if (!track) {
    stopStream(stream);
    throw new CameraUnavailableError("the camera returned no video track");
  }

  if (facing === "environment" && facingOf(track.getSettings(), track.label) !== "environment") {
    const better = await reopenOnRearDevice(devices, stream, options);
    if (better) {
      stopStream(stream);
      stream = better;
      track = stream.getVideoTracks()[0];
    }
  }

  const settings = track.getSettings();
  return {
    stream,
    track,
    facing: facingOf(settings, track.label),
    width: settings.width ?? options.width ?? DEFAULT_WIDTH,
    height: settings.height ?? options.height ?? DEFAULT_HEIGHT,
    setTorch: torchFor(track),
    stop: () => stopStream(stream),
  };
}

/* Look for a rear camera by LABEL and reopen on its id.

   Only reached when `facingMode` did not give us an environment camera, so this
   costs nothing on the platforms that honour it. Returns null – not an error –
   whenever it cannot do better, because "we already have a working front
   camera" is a worse outcome to throw away than to keep. */
async function reopenOnRearDevice(
  devices: MediaDevices,
  current: MediaStream,
  options: OpenCameraOptions,
): Promise<MediaStream | null> {
  if (typeof devices.enumerateDevices !== "function") return null;

  let cameras: MediaDeviceInfo[];
  try {
    cameras = (await devices.enumerateDevices()).filter((d) => d.kind === "videoinput");
  } catch {
    return null;
  }

  const openId = current.getVideoTracks()[0]?.getSettings().deviceId;
  const rear = cameras.find((d) => /back|rear|environment/i.test(d.label) && d.deviceId !== openId);
  if (!rear) return null;

  try {
    // `exact` here, unlike the facingMode above: we picked this device by name,
    // so silently getting a different one would be worse than failing and
    // keeping the stream we already have.
    return await devices.getUserMedia({
      audio: false,
      video: {
        deviceId: { exact: rear.deviceId },
        width: { ideal: options.width ?? DEFAULT_WIDTH },
        height: { ideal: options.height ?? DEFAULT_HEIGHT },
      },
    });
  } catch {
    return null;
  }
}

/* The permission errors are the ones the interface draws differently, so they
   are named rather than passed through as a DOMException the caller has to
   pattern-match on a string. */
function translateError(error: unknown): Error {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return new CameraDeniedError();
  if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") {
    return new CameraUnavailableError();
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return new CameraUnavailableError("another application is using the camera");
  }
  return error instanceof Error ? error : new CameraUnavailableError(String(error));
}

/* `facingMode` in settings is the honest answer where it exists. Where it does
   not – Safari has historically omitted it – the label is the next best thing,
   and "unknown" is an answer the tier logic already knows how to treat. */
function facingOf(settings: MediaTrackSettings, label: string): Facing {
  const mode = settings.facingMode;
  if (mode === "environment" || mode === "user") return mode;
  if (/back|rear|environment/i.test(label)) return "environment";
  if (/front|face|user/i.test(label)) return "user";
  return "unknown";
}

/* `torch` is an image-capture extension rather than part of the media-capture
   IDL, so it is absent from lib.dom on both the capability and the constraint.
   Firefox omits getCapabilities entirely. Both holes are narrowed here rather
   than at the call site, so the rest of the module reads as if the platform
   were tidy. */
type TorchCapabilities = MediaTrackCapabilities & { torch?: boolean };
type TorchTrack = MediaStreamTrack & { getCapabilities?: () => TorchCapabilities };

function torchFor(track: MediaStreamTrack): ((on: boolean) => Promise<void>) | null {
  let capabilities: TorchCapabilities | undefined;
  try {
    capabilities = (track as TorchTrack).getCapabilities?.();
  } catch {
    return null;
  }
  if (!capabilities?.torch) return null;
  return async (on: boolean) => {
    await track.applyConstraints({ advanced: [{ torch: on }] } as unknown as MediaTrackConstraints);
  };
}

export function stopStream(stream: MediaStream | null): void {
  if (!stream) return;
  for (const track of stream.getTracks()) {
    try {
      track.stop();
    } catch {
      // A track already ended is the state we wanted. Nothing to report.
    }
  }
}

/**
 * Wait until a video element actually has pixels.
 *
 * `play()` resolving is not the same thing as a frame being decodable, and
 * drawing a video with `readyState < HAVE_CURRENT_DATA` to a canvas yields a
 * transparent rectangle – which the motion gate would then read as a perfectly
 * still scene and the loop would send exactly one black frame and stop.
 */
export function waitForFrame(video: HTMLVideoElement, timeoutMs = 5000): Promise<void> {
  if (video.readyState >= video.HAVE_CURRENT_DATA) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new CameraUnavailableError("the camera produced no frames"));
    }, timeoutMs);

    const done = () => {
      cleanup();
      resolve();
    };
    const cleanup = () => {
      window.clearTimeout(timer);
      video.removeEventListener("loadeddata", done);
      video.removeEventListener("canplay", done);
    };

    video.addEventListener("loadeddata", done);
    video.addEventListener("canplay", done);
  });
}
