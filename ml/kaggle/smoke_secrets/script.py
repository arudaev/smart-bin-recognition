#!/usr/bin/env python3
"""Step 2: does ATTACHING THE SECRETS DATASET change the answer?

The one factor the two failing kernels share and the one passing kernel does not:
`train_validator` and `bench_latency` both declare
`dataset_sources: ["hlexnc/chexvision-secrets"]`; `probe_latency`, which
completed, declares none.

**It is a hypothesis, not a cause, and step 0 already weakened it**:
`kaggle datasets status` reports the dataset `ready` and `kaggle datasets files`
lists `hf_token.txt`, so it resolves at the API. What that does not test is
whether *attaching it to a kernel run* still mounts. This does.

Identical to `smoke_plain` except for the attachment and for reading the token
that comes with it. If `smoke_plain` passes and this fails, the mount is the
cause and the remedy is a different way of getting the token in - which step 2b
tests rather than assumes.

The token is never printed. Its length and its prefix are enough to prove it
arrived intact, and a kernel log is not a place to put a credential.
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
INPUT = pathlib.Path("/kaggle/input")
NAME = "smoke_secrets"


def unpack_bundle() -> int:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError("bundle sentinel was not replaced - run via scripts/dispatch.py")
    PROJECT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(PROJECT_BUNDLE_B64))) as archive:
        archive.extractall(PROJECT)
        count = len(archive.namelist())
    sys.path.insert(0, str(PROJECT / "ml" / "src"))
    return count


def main() -> None:
    print(f"[sbr] {NAME}: alive", flush=True)
    files = unpack_bundle()

    mounted = sorted(str(p.relative_to(INPUT)) for p in INPUT.rglob("*") if p.is_file()) if INPUT.exists() else []
    print(f"[sbr] {NAME}: {len(mounted)} file(s) under /kaggle/input", flush=True)

    # The resolver the real kernels use, rather than a hard-coded path - Kaggle
    # has moved the mount point before, and a test of a path nobody uses proves
    # nothing about the path everybody uses.
    from sbr.utils.hub import load_hf_token

    token = load_hf_token()

    payload = {
        "kernel": NAME,
        "isolates": "the attached secrets dataset, and only that",
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bundle_files": files,
        "mounted_files": mounted[:20],
        "mounted_count": len(mounted),
        # Never the token itself. Length and prefix prove it arrived whole.
        "token_found": token is not None,
        "token_length": len(token) if token else 0,
        "token_prefix": token[:3] if token else None,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    if not token:
        print(f"[sbr] {NAME}: the dataset mounted but no token was found in it", flush=True)
    print(f"[sbr] {NAME}: OK", flush=True)


if __name__ == "__main__":
    main()
