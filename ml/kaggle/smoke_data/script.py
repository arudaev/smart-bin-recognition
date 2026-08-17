#!/usr/bin/env python3
"""Step 3: pull the pinned pool and build the dataset. No training, no GPU.

Everything `train_validator` does up to the moment it would start spending GPU
time, and then stop. The 2026-08-16 run reached exactly this point - it pulled
the pool, wrote `composition.json`, wrote `args.yaml` - and died somewhere after
it with no log. Running the half that is known to work, on CPU, with the answer
written to a file, turns "it got at least this far" from an inference about a
missing log into a recorded fact.

It also runs the composition contract from `sbr.dataset.expected`, which is the
point of that module: a pool that no longer holds 18 954 frames = 17 474
background + 1 480 positive stops the ladder here, on a CPU kernel, instead of
inside a GPU run.

CPU only. The GPU quota is 30 h/week and nothing here needs one.
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
NAME = "smoke_data"


def log(message: str) -> None:
    print(f"[sbr] {message}", flush=True)


def unpack_bundle() -> None:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError("bundle sentinel was not replaced - run via scripts/dispatch.py")
    PROJECT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(PROJECT_BUNDLE_B64))) as archive:
        archive.extractall(PROJECT)
    sys.path.insert(0, str(PROJECT / "ml" / "src"))
    log(f"unpacked bundle to {PROJECT}")


def main() -> None:
    started = time.time()
    unpack_bundle()
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "huggingface_hub>=1.2.0", "pyyaml"]
    )

    from sbr.config import load_config
    from sbr.dataset.expected import check_composition, expectation_for
    from sbr.dataset.prepare import build_yolo_tree
    from sbr.utils.hub import configure_hf_runtime, download_dataset, resolve_revision

    configure_hf_runtime()
    config = load_config(CONFIG_NAME, PROJECT / "ml" / "configs")
    repo = config["data"]["repo_id"]

    resolved = resolve_revision(repo, config["data"]["revision"], strict=True)
    log(f"pulling {repo} @ {resolved[:12]}")

    pool = download_dataset(repo, revision=config["data"]["revision"], local_dir=WORKING / "pool", strict=True)
    pool_files = sum(1 for p in pool.rglob("*") if p.is_file())
    log(f"pool: {pool_files} files")

    tree = WORKING / "dataset"
    data_yaml = build_yolo_tree(pool, tree, config)
    composition = json.loads((tree / "composition.json").read_text(encoding="utf-8"))
    log(f"composition: {json.dumps(composition)}")

    payload = {
        "kernel": NAME,
        "isolates": "the pinned pool, the tree builder and the composition contract",
        "repo": repo,
        "revision": resolved,
        "pool_files": pool_files,
        "composition": composition,
        "data_yaml": data_yaml.read_text(encoding="utf-8"),
        "elapsed_s": None,
        "contract": None,
    }

    expectation = expectation_for(repo)
    if expectation is None:
        payload["contract"] = "none for this repo"
        log("no composition contract for this repo - nothing asserted")
    else:
        # The whole point of running this on CPU: a drifted pool fails here, for
        # free, rather than inside the GPU run that follows.
        check_composition(composition, expectation)
        payload["contract"] = {
            "revision": expectation.revision,
            "total_frames": expectation.total_frames,
            "background_frames": expectation.background_frames,
            "positive_frames": expectation.positive_frames,
            "negative_ratios": expectation.ratios(),
        }
        log(f"composition matches the contract for {expectation.revision[:12]}")

    payload["elapsed_s"] = round(time.time() - started, 1)
    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log(f"{NAME}: wrote {out}")
    log(f"{NAME}: OK - the data path works end to end without a GPU")


if __name__ == "__main__":
    main()
