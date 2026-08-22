import { describe, expect, it, vi } from "vitest";

import { CameraDeniedError, CameraUnavailableError, openCamera } from "./camera";

/* The Surface Pro 11 bug, and the fallback that fixes it.

   Playwright cannot cover this. Chromium's `--use-fake-device-for-media-stream`
   gives one unlabelled device, and the whole failure is about a platform with
   TWO cameras that reports `facingMode` for NEITHER and names them in labels
   only after permission. So the platform is injected instead – which is what
   `OpenCameraOptions.mediaDevices` has always been for. */

interface FakeCam {
  deviceId: string;
  label: string;
  /** Windows Chrome reports no facingMode at all for UVC cameras. */
  facingMode?: "user" | "environment";
}

function fakePlatform(cameras: FakeCam[], opts: { defaultTo?: string; failOn?: string } = {}) {
  const opened: string[] = [];
  const stopped: string[] = [];

  const track = (cam: FakeCam) => ({
    label: cam.label,
    getSettings: () => ({
      deviceId: cam.deviceId,
      width: 1280,
      height: 720,
      ...(cam.facingMode ? { facingMode: cam.facingMode } : {}),
    }),
    stop: () => stopped.push(cam.deviceId),
    applyConstraints: async () => undefined,
  });

  const streamFor = (cam: FakeCam) => {
    const t = track(cam);
    return { getVideoTracks: () => [t], getTracks: () => [t] } as unknown as MediaStream;
  };

  const devices = {
    enumerateDevices: async () =>
      cameras.map((c) => ({ kind: "videoinput", deviceId: c.deviceId, label: c.label })) as MediaDeviceInfo[],
    getUserMedia: vi.fn(async (constraints: MediaStreamConstraints) => {
      const video = constraints.video as Record<string, unknown>;
      const exact = (video?.deviceId as { exact?: string } | undefined)?.exact;
      if (exact) {
        if (exact === opts.failOn) throw Object.assign(new Error("busy"), { name: "NotReadableError" });
        const cam = cameras.find((c) => c.deviceId === exact);
        if (!cam) throw Object.assign(new Error("gone"), { name: "NotFoundError" });
        opened.push(cam.deviceId);
        return streamFor(cam);
      }
      // No facingMode support: the platform ignores the hint and hands back its
      // default, which on a Surface is the selfie camera.
      const wanted = (video?.facingMode as { ideal?: string } | undefined)?.ideal;
      const match = cameras.find((c) => c.facingMode && c.facingMode === wanted);
      const cam = match ?? cameras.find((c) => c.deviceId === opts.defaultTo) ?? cameras[0];
      opened.push(cam.deviceId);
      return streamFor(cam);
    }),
  } as unknown as MediaDevices;

  return { devices, opened, stopped };
}

const SURFACE: FakeCam[] = [
  { deviceId: "front", label: "Surface Camera Front" },
  { deviceId: "rear", label: "Surface Camera Rear" },
];

describe("openCamera on a platform that does not report facingMode", () => {
  it("reopens on the rear device when the first attempt lands on the selfie camera", async () => {
    const { devices, opened, stopped } = fakePlatform(SURFACE, { defaultTo: "front" });

    const cam = await openCamera({ mediaDevices: devices });

    expect(opened).toEqual(["front", "rear"]);
    expect(cam.facing).toBe("environment");
    expect(cam.track.label).toBe("Surface Camera Rear");
    // The first stream must not be left holding the camera light on.
    expect(stopped).toContain("front");
  });

  it("keeps the front camera rather than failing when the rear device will not open", async () => {
    const { devices, opened } = fakePlatform(SURFACE, { defaultTo: "front", failOn: "rear" });

    const cam = await openCamera({ mediaDevices: devices });

    expect(opened).toEqual(["front"]);
    expect(cam.facing).toBe("user");
    expect(cam.track.label).toBe("Surface Camera Front");
  });

  it("does not reopen when there is only a front camera", async () => {
    const { devices, opened } = fakePlatform([{ deviceId: "front", label: "Integrated Webcam" }]);

    const cam = await openCamera({ mediaDevices: devices });

    expect(opened).toEqual(["front"]);
    expect(cam.facing).toBe("unknown");
  });
});

describe("openCamera where facingMode IS honoured", () => {
  it("does not enumerate or reopen - the existing path is untouched", async () => {
    const { devices, opened } = fakePlatform([
      { deviceId: "front", label: "front camera", facingMode: "user" },
      { deviceId: "rear", label: "rear camera", facingMode: "environment" },
    ]);

    const cam = await openCamera({ mediaDevices: devices });

    expect(opened).toEqual(["rear"]);
    expect(cam.facing).toBe("environment");
  });

  it("honours an explicit request for the front camera without hunting for a rear one", async () => {
    const { devices, opened } = fakePlatform(SURFACE, { defaultTo: "front" });

    const cam = await openCamera({ facing: "user", mediaDevices: devices });

    expect(opened).toEqual(["front"]);
    expect(cam.facing).toBe("user");
  });
});

describe("openCamera error translation", () => {
  it("names a refusal", async () => {
    const devices = {
      getUserMedia: async () => {
        throw Object.assign(new Error("no"), { name: "NotAllowedError" });
      },
    } as unknown as MediaDevices;
    await expect(openCamera({ mediaDevices: devices })).rejects.toBeInstanceOf(CameraDeniedError);
  });

  it("names a browser with no camera API", async () => {
    await expect(openCamera({ mediaDevices: {} as MediaDevices })).rejects.toBeInstanceOf(CameraUnavailableError);
  });
});
