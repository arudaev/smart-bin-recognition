#!/usr/bin/env python3
"""Build the validator's negative corpus, and harvest out-of-city bins.

CPU kernel, no GPU. It downloads tens of thousands of images and streams a
2.2 GB annotation CSV, which is bandwidth rather than compute, and Kaggle has
far more of both than a laptop – the laptop's jobs are ``push`` and ``output``.

Two pools come out of one pass:

``open_images/``  images containing Open Images' ``Waste container`` class, with
                  their human-verified boxes. Bins photographed worldwide, which
                  the legacy archive – one city, one week – cannot provide, and
                  including frames with four or more bins, of which the legacy
                  archive has exactly zero.

``negatives/``    street scenes and hard negatives, with **empty** label files.
                  Roughly 30:1 against the positives, because a detector trained
                  only on photographs of bins learns that everything is a bin.
                  Every one of these is guaranteed not to contain a waste
                  container; that exclusion is the part that must not fail.

Both are pushed to the same dataset repo as the legacy subset, as sibling
directories, so their contributions stay separately measurable.
"""

# ---------------------------------------------------------------------------
# 0. Bundle – injected by dispatch.py
# ---------------------------------------------------------------------------
PROJECT_BUNDLE_B64 = "__SBR_PROJECT_BUNDLE_B64__"
CONFIG_NAME = "__SBR_CONFIG_NAME__"
MODEL_VERSION = "__SBR_MODEL_VERSION__"

import base64  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import pathlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import zipfile  # noqa: E402

WORKING = pathlib.Path("/kaggle/working")
PROJECT = WORKING / "project"


def log(message: str) -> None:
    print(f"[sbr] {message}", flush=True)


def unpack_bundle() -> None:
    if PROJECT_BUNDLE_B64.startswith("__SBR"):
        raise RuntimeError(
            "bundle sentinel was not replaced - run via scripts/dispatch.py, "
            "do not push this file directly"
        )
    PROJECT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(PROJECT_BUNDLE_B64))) as archive:
        archive.extractall(PROJECT)
    sys.path.insert(0, str(PROJECT / "src"))
    log(f"unpacked bundle to {PROJECT}")


def install_dependencies() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "huggingface_hub>=0.24.0", "pyyaml", "pillow"]
    )
    log("dependencies installed")


def main() -> None:
    unpack_bundle()
    install_dependencies()

    import random

    from sbr.config import load_config
    from sbr.dataset.open_images import (
        Candidate,
        harvest,
        load_attribution,
        load_class_index,
        resolve_mids,
        sample,
        scan_boxes,
    )
    from sbr.utils.hub import configure_hf_runtime, upload_dataset

    configure_hf_runtime()
    config = load_config(CONFIG_NAME, PROJECT / "configs")
    source = config["source"]
    seed = 42
    random.seed(seed)
    log(f"config: {json.dumps(config, indent=2)}")

    # --- vocabulary --------------------------------------------------------- #
    index = load_class_index(source["class_descriptions"])
    positive_mid = resolve_mids([config["positives"]["class"]], index)[config["positives"]["class"]]
    street_mids = set(resolve_mids(config["negatives"]["street_classes"], index).values())
    hard_mids = set(resolve_mids(config["negatives"]["hard_classes"], index).values())
    log(f"waste container = {positive_mid}; {len(street_mids)} street, {len(hard_mids)} hard classes")

    # --- one streaming pass per split --------------------------------------- #
    positives: dict[str, list] = {}
    street_ids: dict[str, set] = {}
    hard_ids: dict[str, set] = {}
    for split in config["positives"]["splits"]:
        log(f"scanning {split} annotations ...")
        scan = scan_boxes(
            source["bbox_csv"][split],
            positive_mid,
            street_mids,
            hard_mids,
            drop_group_of=config["positives"]["drop_group_of"],
        )
        positives[split] = scan.positives
        street, hard = scan.negatives()          # every bin image already removed
        street_ids[split] = street
        hard_ids[split] = hard
        log(
            f"{split}: {len(scan.positives)} with bins, "
            f"{len(street)} street, {len(hard)} hard (bins excluded)"
        )

    # --- choose what to fetch ------------------------------------------------ #
    positive_candidates = [
        Candidate(split, image_id, tuple(boxes), "positive")
        for split, found in positives.items()
        for image_id, boxes in found.items()
        if boxes                               # group-of only images carry none
    ]
    positive_candidates = positive_candidates[: config["positives"]["max_images"]]

    def take(pools: dict[str, set], count: int, kind: str) -> list:
        total = sum(len(v) for v in pools.values())
        chosen = []
        for split, ids in pools.items():
            share = round(count * (len(ids) / total)) if total else 0
            chosen += [Candidate(split, i, (), kind) for i in sample(ids, share, seed)]
        return chosen

    negative_candidates = take(street_ids, config["negatives"]["count"], "street")
    negative_candidates += take(hard_ids, config["negatives"]["hard_negative_count"], "hard")

    log(
        f"fetching {len(positive_candidates)} positives and "
        f"{len(negative_candidates)} negatives "
        f"({len(negative_candidates) / max(1, len(positive_candidates)):.1f}:1 within this subset)"
    )

    # --- attribution: a licence condition, not a nicety ---------------------- #
    attribution: dict[str, dict[str, str]] = {}
    wanted_by_split: dict[str, set] = {}
    for candidate in positive_candidates + negative_candidates:
        wanted_by_split.setdefault(candidate.split, set()).add(candidate.image_id)
    for split, wanted in wanted_by_split.items():
        try:
            attribution |= load_attribution(source["metadata_csv"][split], wanted)
        except Exception as error:  # noqa: BLE001 - a missing CSV must not lose the harvest
            log(f"attribution unavailable for {split}: {error}")

    # --- harvest ------------------------------------------------------------- #
    open_images_pool = WORKING / "pools" / "open_images"
    negatives_pool = WORKING / "pools" / "negatives"
    positive_manifest = harvest(positive_candidates, open_images_pool, config, attribution)
    negative_manifest = harvest(negative_candidates, negatives_pool, config, attribution)

    summary = {
        "open_images": {k: v for k, v in positive_manifest.items() if k not in ("records", "crop_records")},
        "negatives": {k: v for k, v in negative_manifest.items() if k not in ("records", "crop_records")},
    }
    (WORKING / "harvest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"harvest: {json.dumps(summary, indent=2)}")

    # The number the whole subset exists to produce.
    banks = sum(
        count for boxes, count in positive_manifest["bins_per_frame"].items() if int(boxes) >= 4
    )
    log(f"frames with four or more bins: {banks} (the legacy archive has 0)")

    # --- push ---------------------------------------------------------------- #
    if os.environ.get("SBR_SKIP_UPLOAD") == "1":
        log("SBR_SKIP_UPLOAD=1, not uploading")
        return

    sha = upload_dataset(
        repo_id=config.get("hub", {}).get("dataset_repo", "arudaev/smart-bin-detect"),
        local_dir=WORKING / "pools",
        commit_message=(
            f"open_images + negatives: {positive_manifest['images']} bins, "
            f"{negative_manifest['images']} negatives"
        ),
        private=True,
    )
    log(f"pushed. revision: {sha}")
    log(f'record it: PINS["arudaev/smart-bin-detect"] = "{sha}"')


if __name__ == "__main__":
    main()
