import { describe, expect, it } from "vitest";

import { probeCapability } from "./capability";

/* docs/01-architecture.md § 5 is emphatic that the tier is a capability probe
   and never a user-agent string, and web/CONVENTIONS.md that it is never a
   viewport query. Both rules exist for the same reason: a tablet at 700 px with
   a rear camera is a scanner and a phone in landscape is still a scanner.

   Everything here is injected, so these are assertions about the policy rather
   than about whatever browser happens to run the suite. */

interface Devices {
  cameras?: { label?: string }[];
  facingMode?: boolean;
  getUserMedia?: boolean;
  throwsOnEnumerate?: boolean;
}

function mediaDevices(options: Devices = {}): MediaDevices {
  const cameras = options.cameras ?? [];
  return {
    getUserMedia: options.getUserMedia === false ? undefined : async () => new MediaStream(),
    enumerateDevices: async () => {
      if (options.throwsOnEnumerate) throw new Error("nope");
      return cameras.map((c, i) => ({
        kind: "videoinput",
        deviceId: String(i),
        label: c.label ?? "",
        groupId: "g",
        toJSON: () => ({}),
      })) as MediaDeviceInfo[];
    },
    getSupportedConstraints: () => ({ facingMode: options.facingMode ?? true }) as MediaTrackSupportedConstraints,
  } as unknown as MediaDevices;
}

function permissions(state: PermissionState | "throw"): Permissions {
  return {
    query: async () => {
      if (state === "throw") throw new Error("no camera descriptor");
      return { state } as PermissionStatus;
    },
  } as unknown as Permissions;
}

describe("probeCapability", () => {
  it("demotes an insecure origin, because getUserMedia will refuse anyway", async () => {
    const result = await probeCapability({ mediaDevices: mediaDevices(), isSecureContext: false });
    expect(result.tier).toBe("viewer");
    expect(result.reason).toMatch(/https/);
  });

  it("demotes a browser with no camera API at all", async () => {
    const result = await probeCapability({ mediaDevices: undefined, isSecureContext: true });
    expect(result.tier).toBe("viewer");
  });

  it("is a scanner when a camera faces away", async () => {
    const result = await probeCapability({
      mediaDevices: mediaDevices({ cameras: [{ label: "Front Camera" }, { label: "Back Triple Camera" }] }),
      permissions: permissions("granted"),
      isSecureContext: true,
    });
    expect(result.tier).toBe("scanner");
    expect(result.hasEnvironmentCamera).toBe(true);
  });

  it("is a capture device when the only camera faces the user", async () => {
    // A laptop webcam. Pointing it at a bin is not a thing anyone does, so it
    // gets the still-capture button rather than the live loop.
    const result = await probeCapability({
      mediaDevices: mediaDevices({ cameras: [{ label: "FaceTime HD Camera" }] }),
      permissions: permissions("granted"),
      isSecureContext: true,
    });
    expect(result.tier).toBe("capture");
    expect(result.reason).toMatch(/front-facing/);
  });

  it("reads two unlabelled cameras as a phone", async () => {
    // Before permission is granted labels are empty, so the count is the only
    // honest signal – and a device with two cameras has a rear one.
    const result = await probeCapability({
      mediaDevices: mediaDevices({ cameras: [{}, {}] }),
      permissions: permissions("prompt"),
      isSecureContext: true,
    });
    expect(result.tier).toBe("scanner");
  });

  it("is a viewer when permission has already been refused", async () => {
    const result = await probeCapability({
      mediaDevices: mediaDevices({ cameras: [{}, {}] }),
      permissions: permissions("denied"),
      isSecureContext: true,
    });
    expect(result.tier).toBe("viewer");
    expect(result.permission).toBe("denied");
    expect(result.reason).toMatch(/blocked/);
  });

  it("survives a browser with no camera permission descriptor", async () => {
    // Firefox throws on permissions.query({name:"camera"}). Not knowing is fine.
    const result = await probeCapability({
      mediaDevices: mediaDevices({ cameras: [{}, {}] }),
      permissions: permissions("throw"),
      isSecureContext: true,
    });
    expect(result.permission).toBe("unknown");
    expect(result.tier).toBe("scanner");
  });

  it("offers still capture when nothing enumerated but the platform knows facingMode", async () => {
    const result = await probeCapability({
      mediaDevices: mediaDevices({ cameras: [], facingMode: true }),
      permissions: permissions("prompt"),
      isSecureContext: true,
    });
    expect(result.tier).toBe("capture");
    expect(result.reason).toMatch(/not enumerated/);
  });

  it("is a viewer when there is genuinely no camera", async () => {
    const result = await probeCapability({
      mediaDevices: mediaDevices({ cameras: [], facingMode: false }),
      permissions: permissions("prompt"),
      isSecureContext: true,
    });
    expect(result.tier).toBe("viewer");
    expect(result.reason).toMatch(/No camera on this device/);
  });

  it("treats a failed enumerate as no camera rather than throwing", async () => {
    const result = await probeCapability({
      mediaDevices: mediaDevices({ throwsOnEnumerate: true, facingMode: false }),
      permissions: permissions("prompt"),
      isSecureContext: true,
    });
    expect(result.tier).toBe("viewer");
  });

  it("always explains itself, because the reason is shown in settings", async () => {
    const result = await probeCapability({
      mediaDevices: mediaDevices({ cameras: [{ label: "Back Camera" }] }),
      permissions: permissions("granted"),
      isSecureContext: true,
    });
    expect(result.reason.length).toBeGreaterThan(0);
  });
});
