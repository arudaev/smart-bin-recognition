#!/usr/bin/env python3
"""Step 2b: can an API-PUSHED kernel read a Kaggle Secret at all?

This one exists to stop a remedy being assumed. If step 2 shows the attached
dataset is what breaks the run, the obvious fix is "use a Kaggle Secret
instead" - and `ml/tests/test_kernels.py` currently carries the opposite belief
in a comment: *"UserSecretsClient only works in an interactive session."*

Neither the belief nor the fix has ever been tested here, and the documented
kernel metadata schema has fields for attaching datasets and **no field for
binding a secret**. So a secret created in the web UI may or may not be visible
to a kernel pushed through the API, and swapping `hub.load_hf_token` over to it
on the strength of a guess would replace a known failure with an unknown one.

This kernel asks. It attaches no dataset, so a token reaching it can only have
come through `UserSecretsClient`. **Not finding one is a perfectly good result**
and the kernel still completes: what is being measured is whether the mechanism
exists, and a crash would conflate "no secret" with "the platform is broken",
which is the exact confusion this ladder is built to avoid.

Set the secret in the Kaggle UI as `HF_TOKEN` before running, or expect
`secret_found: false` and read it as "not configured" rather than "not possible".
"""

from __future__ import annotations

PROJECT_BUNDLE_B64 = "__SBR_PROJECT_BUNDLE_B64__"
CONFIG_NAME = "__SBR_CONFIG_NAME__"
MODEL_VERSION = "__SBR_MODEL_VERSION__"

import base64  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import zipfile  # noqa: E402

WORKING = pathlib.Path("/kaggle/working")
PROJECT = WORKING / "project"
NAME = "smoke_usersecret"
SECRET_NAME = "HF_TOKEN"


def unpack_bundle() -> int:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError("bundle sentinel was not replaced - run via scripts/dispatch.py")
    PROJECT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(PROJECT_BUNDLE_B64))) as archive:
        archive.extractall(PROJECT)
        count = len(archive.namelist())
    sys.path.insert(0, str(PROJECT / "ml" / "src"))
    return count


def read_secret() -> dict:
    """Every outcome is a result, so nothing here is allowed to end the run."""
    try:
        from kaggle_secrets import UserSecretsClient
    except Exception as error:  # noqa: BLE001
        return {"available": False, "reason": f"import failed: {type(error).__name__}: {error}"}

    try:
        value = UserSecretsClient().get_secret(SECRET_NAME)
    except Exception as error:  # noqa: BLE001
        # The interesting case. The distinction between "no such secret" and
        # "secrets do not work here" is in this message and nowhere else.
        return {"available": True, "secret_found": False,
                "reason": f"{type(error).__name__}: {error}"}

    return {
        "available": True,
        "secret_found": bool(value),
        "length": len(value) if value else 0,
        "prefix": value[:3] if value else None,
    }


def main() -> None:
    print(f"[sbr] {NAME}: alive", flush=True)
    files = unpack_bundle()
    secret = read_secret()

    payload = {
        "kernel": NAME,
        "isolates": "whether a UI-created Kaggle Secret is visible to an API-pushed kernel",
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bundle_files": files,
        "secret_name": SECRET_NAME,
        "user_secrets": secret,
        "attached_datasets": sorted(p.name for p in pathlib.Path("/kaggle/input").glob("*"))
        if pathlib.Path("/kaggle/input").exists()
        else [],
        "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    print(f"[sbr] {NAME}: OK - and 'no secret' is an answer, not a failure", flush=True)


if __name__ == "__main__":
    main()
