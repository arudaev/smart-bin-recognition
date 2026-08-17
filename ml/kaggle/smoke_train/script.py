#!/usr/bin/env python3
"""Step 4: ONE epoch on the GPU, and a checkpoint on disk.

The last rung before the real run. `train_validator` asks for 80 epochs at batch
32 over 18 954 images; if the failure is a time limit, a memory ceiling, an
Ultralytics incompatibility or a GPU quota, this finds it in minutes instead of
after a queue wait and most of an hour - and, unlike the run that failed, it
leaves a file behind whichever way it goes.

**One epoch and a small subset**, because this is not trying to produce a model.
Weights from one epoch over a fraction of the pool are worthless for accuracy and
are never uploaded: the artefact under test is `weights/best.pt` existing at all.
The 2026-08-16 run got as far as writing `args.yaml` and produced no weights,
so "did a checkpoint appear" is precisely the question.

Nothing here decides whether anything ships. It cannot: the latency budget is
stated on service CPU and this machine has a GPU and somebody else's CPU.
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
NAME = "smoke_train"

#: Frames per split in the cut-down tree. Enough for one epoch to be a real
#: epoch, small enough that a failure arrives in minutes.
SUBSET = {"train": 400, "val": 100, "test": 0}


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


def cut_down(tree: pathlib.Path, out: pathlib.Path, config: dict) -> pathlib.Path:
    """A smaller tree with the same shape, keeping the background/positive mix.

    Taking the first N files in sorted order would take them from one subset -
    the qualified names are prefixed by pool - and train on negatives alone.
    Striding keeps the mixture, which is what makes one epoch a real epoch.
    """
    import yaml

    for split, keep in SUBSET.items():
        images = sorted((tree / "images" / split).glob("*"))
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        if not images or keep == 0:
            continue
        stride = max(1, len(images) // keep)
        for image in images[::stride][:keep]:
            label = tree / "labels" / split / f"{image.stem}.txt"
            (out / "images" / split / image.name).write_bytes(image.read_bytes())
            (out / "labels" / split / label.name).write_text(
                label.read_text(encoding="utf-8") if label.exists() else "", encoding="utf-8"
            )
        log(f"{split}: kept {min(keep, len(images[::stride]))} of {len(images)}")

    data = {
        "path": str(out.resolve()),
        "train": "images/train",
        "val": "images/val",
        "nc": 1,
        "names": {0: "bin"},
    }
    path = out / "data.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def main() -> None:
    started = time.time()
    unpack_bundle()
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "--no-deps",
         "ultralytics>=8.3.0", "ultralytics-thop"]
    )
    # --no-deps above keeps the image's CUDA-matched torch. Letting pip resolve
    # ultralytics' own torch is what broke the 2026-08-16 run - see sbr.utils.gpu.
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "huggingface_hub>=1.2.0", "pyyaml"]
    )

    from sbr.config import load_config
    from sbr.dataset.prepare import build_yolo_tree
    from sbr.utils.hub import configure_hf_runtime, download_dataset

    configure_hf_runtime()
    config = load_config(CONFIG_NAME, PROJECT / "ml" / "configs")

    from sbr.utils.gpu import inspect_accelerator

    # Reported, not required: this rung's whole job is to say what the GPU is
    # and whether torch can use it, so refusing here would withhold the answer.
    accelerator = inspect_accelerator()
    log(f"accelerator: {accelerator.describe()}")

    pool = download_dataset(
        config["data"]["repo_id"], revision=config["data"]["revision"],
        local_dir=WORKING / "pool", strict=True,
    )
    tree = WORKING / "dataset"
    build_yolo_tree(pool, tree, config)
    data_yaml = cut_down(tree, WORKING / "subset", config)

    from ultralytics import YOLO

    model = YOLO(f"{config['model']['arch']}.pt")
    model.train(
        data=str(data_yaml),
        imgsz=config["data"]["imgsz"],
        epochs=1,
        batch=8,
        workers=2,
        seed=config["project"]["seed"],
        project=str(WORKING / "runs"),
        name=NAME,
        exist_ok=True,
        device=accelerator.device,
    )

    save_dir = pathlib.Path(model.trainer.save_dir)
    weights = sorted((save_dir / "weights").glob("*.pt"))
    payload = {
        "kernel": NAME,
        "isolates": "one epoch of GPU training, and whether a checkpoint appears",
        "accelerator": accelerator.as_dict(),
        "epochs": 1,
        "subset": SUBSET,
        "save_dir": str(save_dir),
        # THE question. The 2026-08-16 run wrote args.yaml and left this empty.
        "weights": [w.name for w in weights],
        "weights_bytes": {w.name: w.stat().st_size for w in weights},
        "elapsed_s": round(time.time() - started, 1),
    }

    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log(json.dumps(payload, indent=2))
    if not weights:
        raise SystemExit(
            "one epoch finished and produced NO weights - the same shape as the "
            "2026-08-16 failure, now reproduced in minutes rather than an hour"
        )
    log(f"{NAME}: OK - a checkpoint exists. These weights are NOT a model and are not uploaded.")


if __name__ == "__main__":
    main()
