#!/usr/bin/env python3
"""Dispatch training to a Kaggle GPU kernel.

Kaggle gives 30 h/week of free GPU. You push a kernel and walk away; it runs to
completion and pushes its artefacts to Hugging Face. Nothing trains locally.

    python ml/scripts/dispatch.py push validator  --version 1
    python ml/scripts/dispatch.py push identifier --version 1
    python ml/scripts/dispatch.py status validator
    python ml/scripts/dispatch.py output validator --out artifacts/

Requires ``KAGGLE_API_TOKEN`` (a ``KGAT_...`` token) in ``.env`` at the repo
root. See ``docs/04-ml-pipeline.md`` § 3.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
KAGGLE_DIR = ML_ROOT / "kaggle"

BUNDLE_SENTINEL = "__SBR_PROJECT_BUNDLE_B64__"
CONFIG_SENTINEL = "__SBR_CONFIG_NAME__"
VERSION_SENTINEL = "__SBR_MODEL_VERSION__"

KERNELS = {
    "validator": "train_validator",      # model A – "is there a bin?"
    "identifier": "train_identifier",    # model B – "which bin?"
    "negatives": "build_negatives",      # the corpus A is mostly trained on
    "bench": "bench_latency",            # the ship gate's measuring instrument
    "probe": "probe_latency",            # docs/12 P4 and P5 – no model needed
    "quant": "probe_quantisation",       # docs/12 P9 - why int8 destroys the validator
    # The smoke ladder. On 2026-08-16 the validator and the bench both ended
    # with status ERROR, an empty log and an empty failure message, while the
    # probe completed – so there is no diagnostic to read and the only way to
    # find the boundary is to change one thing at a time. Run them in this
    # order; the first failure is the answer. Each writes a file as well as
    # printing, because "no artefact and an empty log" is the thing being
    # diagnosed. See docs/07 phase 2.
    "smoke-bare": "smoke_bare",              # 1a: no bundle, no dataset, no GPU
    "smoke-plain": "smoke_plain",            # 1b: + the injected bundle
    "smoke-secrets": "smoke_secrets",        # 2:  + the attached secrets dataset
    "smoke-usersecret": "smoke_usersecret",  # 2b: a Kaggle Secret instead – does it bind?
    "smoke-data": "smoke_data",              # 3:  the pinned pool and the composition contract
    "smoke-gpu": "smoke_gpu",                # 1c: what GPU, and can the IMAGE'S torch use it?
    "smoke-train": "smoke_train",            # 4:  one epoch on the GPU, and a checkpoint
}

#: Which config each kernel loads, where it is not the kernel's own name.
CONFIGS = {
    "negatives": "open_images",
    "bench": "validator",
    "probe": "validator",
    "quant": "validator",
    "smoke-bare": "validator",
    "smoke-plain": "validator",
    "smoke-secrets": "validator",
    "smoke-usersecret": "validator",
    "smoke-data": "validator",
    "smoke-gpu": "validator",
    "smoke-train": "validator",
}

#: Bundled into the kernel payload. `data/taxonomy` is included because the
#: detector's class list is derived from it – the kernel must not have to guess.
#:
#: **THE PREFIXES MIRROR THE REPOSITORY, and that is load-bearing.** `sbr` finds
#: its data by walking up from its own file: `taxonomy.py` resolves the repo root
#: as `parents[3]` and `config.py` resolves configs as `parents[2]/configs`. The
#: earlier layout unpacked `src/` and `data/taxonomy` as siblings, so
#: `<unpack>/src/sbr/taxonomy.py` put `parents[3]` one level ABOVE the unpack
#: directory and every call to `load_taxonomy()` died with
#: `FileNotFoundError: .../data/taxonomy/waste-streams.json`.
#:
#: It was invisible for two reasons: `load_config` resolved correctly from the
#: same tree, and the one kernel that completed - `probe_latency` - never calls
#: `load_taxonomy`. The kernels that do were the ones failing. `service/Dockerfile`
#: mirrors the repo under `/app` for exactly this reason and says so.
BUNDLE_PATHS = [
    (ML_ROOT / "src", "ml/src"),
    (ML_ROOT / "configs", "ml/configs"),
    (REPO_ROOT / "data" / "taxonomy", "data/taxonomy"),
]

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def build_bundle() -> str:
    """Zip the project payload and base64-encode it for injection."""
    buffer = io.BytesIO()
    file_count = 0

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for source, prefix in BUNDLE_PATHS:
            if not source.exists():
                raise FileNotFoundError(f"bundle path missing: {source}")
            for path in sorted(source.rglob("*")):
                if not path.is_file() or path.suffix == ".pyc":
                    continue
                if EXCLUDE_DIRS & set(path.parts):
                    continue
                zf.write(path, f"{prefix}/{path.relative_to(source)}")
                file_count += 1

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    print(f"bundled {file_count} files ({len(encoded) / 1024:.0f} KB base64)")
    return encoded


def _resolve_taxonomy_note() -> None:
    """Fail early if the taxonomy is invalid – a bad class list wastes a GPU hour."""
    result = subprocess.run(
        [sys.executable, str(ML_ROOT / "scripts" / "validate_taxonomy.py"), "--skip-locales"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit("taxonomy validation failed – refusing to dispatch")


def push(kernel: str, config_name: str, version: int) -> None:
    """Render the kernel script with the bundle injected, then push it."""
    _resolve_taxonomy_note()

    source_dir = KAGGLE_DIR / KERNELS[kernel]
    script = (source_dir / "script.py").read_text(encoding="utf-8")
    metadata = json.loads((source_dir / "kernel-metadata.json").read_text(encoding="utf-8"))

    rendered = (
        script.replace(BUNDLE_SENTINEL, build_bundle())
        .replace(CONFIG_SENTINEL, config_name)
        .replace(VERSION_SENTINEL, str(version))
    )

    # Internet is what makes an unattended run possible: the kernel pulls its
    # pinned dataset and pushes its artefacts. GPU is NOT forced - build_negatives
    # is bandwidth, not compute, and burning the 30 h/week GPU quota on
    # downloading JPEGs would be a waste of the thing training actually needs.
    metadata["enable_internet"] = True
    metadata.setdefault("enable_gpu", False)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        (staging / "script.py").write_text(rendered, encoding="utf-8")
        (staging / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        _kaggle("kernels", "push", "-p", str(staging))

    print(f"pushed {metadata['id']} (config={config_name}, version={version})")
    print(f"  watch: python {Path(__file__).name} status {kernel}")


def status(kernel: str) -> None:
    metadata = json.loads((KAGGLE_DIR / KERNELS[kernel] / "kernel-metadata.json").read_text(encoding="utf-8"))
    _kaggle("kernels", "status", metadata["id"])


def output(kernel: str, out_dir: Path) -> None:
    metadata = json.loads((KAGGLE_DIR / KERNELS[kernel] / "kernel-metadata.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    _kaggle("kernels", "output", metadata["id"], "-p", str(out_dir))
    print(f"downloaded to {out_dir}")


def _kaggle(*args: str) -> None:
    executable = shutil.which("kaggle")
    if not executable:
        raise SystemExit("kaggle CLI not found – `pip install kaggle`")

    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass

    subprocess.run([executable, *args], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_push = sub.add_parser("push", help="bundle and dispatch a training run")
    p_push.add_argument("kernel", choices=KERNELS)
    p_push.add_argument("--config", default=None, help="config name (defaults to the kernel name)")
    p_push.add_argument("--version", type=int, required=True, help="model version for artefact naming")

    p_status = sub.add_parser("status", help="check a run")
    p_status.add_argument("kernel", choices=KERNELS)

    p_output = sub.add_parser("output", help="download artefacts")
    p_output.add_argument("kernel", choices=KERNELS)
    p_output.add_argument("--out", type=Path, default=Path("artifacts"))

    args = parser.parse_args()

    if args.command == "push":
        push(args.kernel, args.config or CONFIGS.get(args.kernel, args.kernel), args.version)
    elif args.command == "status":
        status(args.kernel)
    elif args.command == "output":
        output(args.kernel, args.out)


if __name__ == "__main__":
    main()
