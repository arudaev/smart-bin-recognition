#!/usr/bin/env python3
"""Step 1a: does ANY kernel from this account run at all?

The 2026-08-16 validator run and a re-push of the much cheaper bench kernel both
ended with status ERROR, **an empty log and an empty failureMessage**, while
`probe_latency` had completed hours earlier. With no diagnostic from the
platform, the only way to find the boundary is to change one thing at a time and
watch where it breaks.

This is the floor of that ladder and it is deliberately the smallest thing that
can run:

- **no injected bundle** - no sentinel in this file, so `dispatch.py` has nothing
  to replace and the pushed script stays a few hundred bytes rather than the
  ~500 KB a base64 project bundle makes it;
- **no attached dataset**;
- **no GPU**;
- **no network use**, though internet is enabled so that this differs from
  `smoke_plain` in exactly one way.

**If this fails, stop.** The account or the platform is the problem, and no
amount of reading training code will find it. If it passes, the next rung adds
the bundle.

It writes a file as well as printing, because "no artefact and an empty log" is
the failure being diagnosed: a run that produces both is distinguishable from one
that produced neither, and that distinction is the entire point.
"""

from __future__ import annotations

import json
import os
import pathlib
import platform
import sys
import time

WORKING = pathlib.Path("/kaggle/working")
NAME = "smoke_bare"


def main() -> None:
    print(f"[sbr] {NAME}: alive", flush=True)

    payload = {
        "kernel": NAME,
        "isolates": "the platform and the account, with nothing else present",
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "bundle": False,
        "attached_datasets": sorted(
            p.name for p in pathlib.Path("/kaggle/input").glob("*")
        )
        if pathlib.Path("/kaggle/input").exists()
        else [],
        "env_markers": {
            key: os.environ.get(key)
            for key in ("KAGGLE_KERNEL_RUN_TYPE", "KAGGLE_DOCKER_IMAGE", "KAGGLE_URL_BASE")
        },
    }

    # A little arithmetic, so "it ran" means the interpreter actually worked
    # rather than that the process started and was killed.
    payload["sum_to_a_million"] = sum(range(1_000_001))
    payload["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    WORKING.mkdir(parents=True, exist_ok=True)
    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, indent=2), flush=True)
    print(f"[sbr] {NAME}: wrote {out}", flush=True)
    print(f"[sbr] {NAME}: OK", flush=True)


if __name__ == "__main__":
    main()
