#!/usr/bin/env python3
"""Step 1b: does the INJECTED BUNDLE change the answer?

Identical in intent to `smoke_bare` and different in exactly one way: this file
carries the injection sentinel, so `dispatch.py` replaces it with a base64 zip of
`src/`, `configs/` and `data/taxonomy` and the pushed script grows from a few
hundred bytes to roughly half a megabyte of string literal.

That matters because of what it would mean if `smoke_bare` passed and this
failed: the failure would be in how this project ships code to Kaggle - a size
limit, an encoding, a parse - and not in the account, the platform, the training
code, the data or the GPU. **`smoke_bare` failing exonerates the training path;
it does not exonerate the bundle.** Only the pair of them, read together, says
which.

Still no attached dataset and no GPU. Those are the next two rungs.
"""

from __future__ import annotations

PROJECT_BUNDLE_B64 = "__SBR_PROJECT_BUNDLE_B64__"
CONFIG_NAME = "__SBR_CONFIG_NAME__"
MODEL_VERSION = "__SBR_MODEL_VERSION__"

import base64  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import pathlib  # noqa: E402
import platform  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import zipfile  # noqa: E402

WORKING = pathlib.Path("/kaggle/working")
PROJECT = WORKING / "project"
NAME = "smoke_plain"


def unpack_bundle() -> dict:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError(
            "bundle sentinel was not replaced - run via scripts/dispatch.py, "
            "do not push this file directly"
        )
    PROJECT.mkdir(parents=True, exist_ok=True)
    raw = base64.b64decode(PROJECT_BUNDLE_B64)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        archive.extractall(PROJECT)
    sys.path.insert(0, str(PROJECT / "ml" / "src"))
    return {"encoded_chars": len(PROJECT_BUNDLE_B64), "zip_bytes": len(raw), "files": len(names)}


def main() -> None:
    print(f"[sbr] {NAME}: alive", flush=True)
    bundle = unpack_bundle()
    print(f"[sbr] {NAME}: unpacked {bundle['files']} files", flush=True)

    # Import one thing out of the bundle, because unpacking a zip proves the
    # bytes arrived and nothing about whether they are usable.
    from sbr.taxonomy import load_taxonomy

    taxonomy = load_taxonomy()

    payload = {
        "kernel": NAME,
        "isolates": "the injected project bundle, and only that",
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version,
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "config_name": CONFIG_NAME,
        "model_version": MODEL_VERSION,
        "bundle": bundle,
        "detector_classes": taxonomy.detector_classes,
        "attached_datasets": sorted(p.name for p in pathlib.Path("/kaggle/input").glob("*"))
        if pathlib.Path("/kaggle/input").exists()
        else [],
    }
    payload["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    print(f"[sbr] {NAME}: OK", flush=True)


if __name__ == "__main__":
    main()
