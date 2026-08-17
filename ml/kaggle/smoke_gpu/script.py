#!/usr/bin/env python3
"""Step 1c: what accelerator does Kaggle give, and can ITS OWN torch use it?

**Installs nothing.** That is the entire point. Every other rung that touches a
GPU also runs `pip install`, so a torch/GPU mismatch seen there could always be
blamed on the install - and it was, wrongly. This rung reports the image exactly
as Kaggle shipped it, so the question "did we break torch, or did it arrive
broken" has an answer that does not depend on anything this project does.

The mismatch it exists to settle:

    Tesla P100-PCIE-16GB with CUDA capability sm_60 is not compatible with the
    current PyTorch installation. The current PyTorch install supports CUDA
    capabilities sm_70 sm_75 sm_80 sm_86 sm_90 sm_100 sm_120.

If this rung reports the same torch and the same gap with **no pip install
anywhere in it**, the image ships a torch that cannot use the GPU the platform
allocated, and no change to this repository fixes that.

Runs in seconds and burns a negligible slice of the 30 h/week GPU quota, which
is the cheapest possible way to be sure about a root cause.
"""

from __future__ import annotations

PROJECT_BUNDLE_B64 = "__SBR_PROJECT_BUNDLE_B64__"
CONFIG_NAME = "__SBR_CONFIG_NAME__"
MODEL_VERSION = "__SBR_MODEL_VERSION__"

import base64  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import zipfile  # noqa: E402

WORKING = pathlib.Path("/kaggle/working")
PROJECT = WORKING / "project"
NAME = "smoke_gpu"


def log(message: str) -> None:
    print(f"[sbr] {message}", flush=True)


def unpack_bundle() -> None:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError("bundle sentinel was not replaced - run via scripts/dispatch.py")
    PROJECT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(PROJECT_BUNDLE_B64))) as archive:
        archive.extractall(PROJECT)
    sys.path.insert(0, str(PROJECT / "ml" / "src"))


def main() -> None:
    unpack_bundle()

    # NOTHING IS INSTALLED. Recorded in the output so a reader does not have to
    # take the docstring's word for it.
    frozen = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True
    ).stdout
    torch_lines = [line for line in frozen.splitlines() if line.lower().startswith("torch")]

    from sbr.utils.gpu import inspect_accelerator

    accelerator = inspect_accelerator()
    log(f"accelerator: {accelerator.describe()}")

    payload = {
        "kernel": NAME,
        "isolates": "the image's own torch against the GPU the platform allocated",
        "installed_anything": False,
        "torch_packages_as_shipped": torch_lines,
        "accelerator": accelerator.as_dict(),
        "verdict": (
            "the image's torch can use the GPU it was given"
            if accelerator.usable
            else "THE IMAGE SHIPS A TORCH THAT CANNOT USE THIS GPU - nothing in this "
                 "repository caused it and nothing in it can fix it"
        ),
        "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    log(f"{NAME}: OK - '{payload['verdict']}'")


if __name__ == "__main__":
    main()
