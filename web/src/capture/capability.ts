/* Which device tier this is, decided by asking the platform what it has.

   docs/01-architecture.md § 5 is emphatic that this is a capability probe and
   never a user-agent string, and web/CONVENTIONS.md is emphatic that it is
   never a viewport query either. Both rules exist for the same reason: a
   tablet at 700 px with a rear camera is a scanner, and a phone in landscape is
   still a scanner. Deciding on width would give the right answer for the wrong
   reason and then be wrong the first time somebody rotated a device.

   The probe is deliberately cheap and permission-free. `enumerateDevices`
   returns entries before permission is granted; it just redacts their labels.
   That is enough to know a camera exists, which is all the tier needs. */

export type Tier = "scanner" | "capture" | "viewer";

export interface Capability {
  tier: Tier;
  /** getUserMedia exists at all. False on http:// origins and old browsers. */
  hasMediaDevices: boolean;
  /** At least one videoinput was enumerated. */
  hasCamera: boolean;
  /** An environment-facing camera was identified, or could not be ruled out. */
  hasEnvironmentCamera: boolean;
  /** Permission already decided, where the Permissions API says so. */
  permission: PermissionState | "unknown";
  /** Why the tier is what it is. Shown in settings, and in bug reports. */
  reason: string;
}

export const VIEWER: Capability = {
  tier: "viewer",
  hasMediaDevices: false,
  hasCamera: false,
  hasEnvironmentCamera: false,
  permission: "unknown",
  reason: "No camera API on this origin",
};

interface ProbeDeps {
  mediaDevices?: MediaDevices;
  permissions?: Permissions;
  isSecureContext?: boolean;
}

function deps(overrides?: ProbeDeps): ProbeDeps {
  if (overrides) return overrides;
  if (typeof navigator === "undefined") return {};
  return {
    mediaDevices: navigator.mediaDevices,
    permissions: navigator.permissions,
    isSecureContext: typeof isSecureContext === "boolean" ? isSecureContext : true,
  };
}

export async function probeCapability(overrides?: ProbeDeps): Promise<Capability> {
  const { mediaDevices, permissions, isSecureContext: secure = true } = deps(overrides);

  if (!secure) {
    return { ...VIEWER, reason: "Camera needs a secure origin (https)" };
  }
  if (!mediaDevices || typeof mediaDevices.getUserMedia !== "function") {
    return VIEWER;
  }

  let permission: PermissionState | "unknown" = "unknown";
  try {
    // Firefox has no "camera" descriptor and throws. Not knowing is fine.
    const status = await permissions?.query({ name: "camera" as PermissionName });
    if (status) permission = status.state;
  } catch {
    permission = "unknown";
  }

  if (permission === "denied") {
    return {
      tier: "viewer",
      hasMediaDevices: true,
      hasCamera: true,
      hasEnvironmentCamera: false,
      permission,
      reason: "Camera access is blocked for this site",
    };
  }

  let devices: MediaDeviceInfo[] = [];
  try {
    devices = await mediaDevices.enumerateDevices();
  } catch {
    devices = [];
  }
  const cameras = devices.filter((d) => d.kind === "videoinput");

  if (cameras.length === 0) {
    // Some browsers report nothing until a stream has been opened once. If the
    // platform advertises facingMode support we give it the benefit of the
    // doubt rather than demoting a real phone to a viewer on a technicality.
    const advertises = supportsFacingMode(mediaDevices);
    if (advertises && permission !== "granted") {
      return {
        tier: "capture",
        hasMediaDevices: true,
        hasCamera: false,
        hasEnvironmentCamera: false,
        permission,
        reason: "Camera not enumerated yet; still-capture offered",
      };
    }
    return {
      tier: "viewer",
      hasMediaDevices: true,
      hasCamera: false,
      hasEnvironmentCamera: false,
      permission,
      reason: "No camera on this device",
    };
  }

  const environment = hasEnvironmentFacing(cameras, mediaDevices);

  return {
    tier: environment ? "scanner" : "capture",
    hasMediaDevices: true,
    hasCamera: true,
    hasEnvironmentCamera: environment,
    permission,
    reason: environment
      ? `${cameras.length} camera${cameras.length === 1 ? "" : "s"}, one facing away`
      : "Only a front-facing camera; live scanning is off",
  };
}

function supportsFacingMode(mediaDevices: MediaDevices): boolean {
  try {
    return Boolean(mediaDevices.getSupportedConstraints?.().facingMode);
  } catch {
    return false;
  }
}

/* Before permission is granted, labels are empty and `getCapabilities` is not
   available, so more than one videoinput is the honest signal: a device with
   two cameras has a rear one. With labels, look for the platform's own word. */
function hasEnvironmentFacing(cameras: MediaDeviceInfo[], mediaDevices: MediaDevices): boolean {
  const labelled = cameras.filter((c) => c.label);
  if (labelled.length > 0) {
    const rear = /back|rear|environment|arrière|hinten|world/i;
    if (labelled.some((c) => rear.test(c.label))) return true;
    // Labels present and none says rear: a single labelled webcam is a webcam.
    if (labelled.length === 1) return false;
  }
  if (cameras.length > 1) return true;
  // One unlabelled camera on a platform that understands facingMode: treat a
  // phone as a phone. A desktop webcam still fails the try in openCamera and
  // demotes itself then, which is a state the interface already draws.
  return cameras.length === 1 && supportsFacingMode(mediaDevices) && isLikelyMobile();
}

/* The one place a user-agent hint is consulted, and only to break a tie the
   device API refused to break. It can never promote a device that has no
   camera, and it can never demote one that reported a rear camera. */
function isLikelyMobile(): boolean {
  if (typeof navigator === "undefined") return false;
  const data = (navigator as Navigator & { userAgentData?: { mobile?: boolean } }).userAgentData;
  if (typeof data?.mobile === "boolean") return data.mobile;
  if (typeof matchMedia === "function") return matchMedia("(pointer: coarse)").matches;
  return false;
}
