#!/usr/bin/env python3
"""docs/12 P1 - are the form factors separable from a crop? (Kaggle, GPU, T4)

The adjudication is **finished**: 403 crops, reviewer ``alex``, run with
``--blind``, every verdict ``authored``. This probe asks what that pass was
gating - whether ``wheelie_small`` and ``wheelie_large`` are a distinction a
model can see in a 320 px crop at all, or whether resizing throws the only
signal away.

**Why blind mattered, and why it is upstream of everything here.** The pool
ships a ``form_factor_proposed`` that is a stream -> shape mapping, and against
the finished pass it is **wrong on 116 of 403 crops - 28.8 %** - of which **111
are ``wheelie_small`` where the answer is ``wheelie_large``**. That is precisely
the pair this probe tests. Shown those proposals, a reviewer would have measured
the mapping table and this kernel would have called the classes cleanly
separable.

**The estimator is frozen in docs/12 and was committed before this file was
written.** Nothing here is chosen on the way past: DINOv2-base CLS embeddings, a
logistic-regression probe, ``GroupKFold(5)`` on ``capture_cluster``, a scaler
fitted inside each fold, two variants (with and without relative box area), and
every headline quoted beside its majority-class baseline and its balanced
accuracy.

**Why group-aware.** 403 crops come from 100 capture clusters - one visit to
one bin, reconstructed from EXIF times. A random split puts two photographs of
the same physical bin either side of the line and reports memorisation as
generalisation, which is the predecessor's 95.2 % and the exact mistake this
project exists not to repeat.

**Nothing is uploaded, and nothing is labelled.** This is a measurement.
"""

# ---------------------------------------------------------------------------
# 0. Bundle - injected by dispatch.py
# ---------------------------------------------------------------------------
PROJECT_BUNDLE_B64 = "__SBR_PROJECT_BUNDLE_B64__"
CONFIG_NAME = "__SBR_CONFIG_NAME__"
MODEL_VERSION = "__SBR_MODEL_VERSION__"

import base64  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import zipfile  # noqa: E402

WORKING = pathlib.Path("/kaggle/working")
PROJECT = WORKING / "project"
NAME = "p1-separability"

#: Outside /kaggle/working, which is all kernel output.
SCRATCH = pathlib.Path("/tmp/sbr")

#: Frozen in docs/12 before this file existed. Do not substitute a bigger model
#: because a number disappoints - that is a new probe, not a tuning knob.
DINOV2 = "facebook/dinov2-base"

#: The pair the decision rule reads.
PAIR = ("wheelie_small", "wheelie_large")

#: n=1 in one capture cluster. It cannot be fitted and it cannot be held out, so
#: it is reported and excluded from every fitted number rather than occupying a
#: row that would suggest it was measured.
NOT_EVALUABLE = "street_basket"

FOLDS = 5
SEED = 42


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
    sys.path.insert(0, str(PROJECT / "ml" / "src"))
    log(f"unpacked bundle to {PROJECT}")


def install_dependencies() -> None:
    """``--no-deps`` on transformers so pip cannot decide about torch.

    The Kaggle image ships torch 2.10.0+cu128 and a resolver that swapped it
    would add a second, harder-to-see cause on top of whatever the first one is.
    See ``sbr.utils.gpu``.
    """
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "--no-deps", "transformers>=4.44"]
    )
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q",
         "scikit-learn>=1.4", "huggingface_hub>=1.2.0", "pyyaml", "safetensors"]
    )
    log("dependencies installed (torch left exactly as the image shipped it)")


def toolchain() -> dict:
    versions = {}
    for module in ("torch", "transformers", "sklearn", "numpy", "PIL"):
        try:
            versions[module] = __import__(module).__version__
        except Exception as error:  # noqa: BLE001 - an absent module is a fact
            versions[module] = f"unavailable ({type(error).__name__})"
    return versions


def embed(crops, model, processor, device, batch: int = 32):
    """CLS embeddings for a list of image paths, in order.

    ``AutoImageProcessor`` applies the resize-256 / centre-crop-224 / ImageNet
    normalisation the pre-registration names; it is used rather than hand-rolled
    so the preprocessing is the model's own and can be quoted as such.
    """
    import numpy as np
    import torch
    from PIL import Image

    vectors = []
    for start in range(0, len(crops), batch):
        chunk = crops[start:start + batch]
        images = []
        for path in chunk:
            with Image.open(path) as handle:
                images.append(handle.convert("RGB"))
        inputs = processor(images=images, return_tensors="pt").to(device)
        with torch.no_grad():
            output = model(**inputs)
        # CLS token: position 0 of the last hidden state.
        vectors.append(output.last_hidden_state[:, 0, :].float().cpu().numpy())
        log(f"embedded {min(start + batch, len(crops))}/{len(crops)}")
    return np.vstack(vectors)


def out_of_fold(features, labels, groups):
    """Pooled OOF predictions under GroupKFold, scaler fitted inside each fold.

    Returns ``(predictions, folds)`` where ``folds`` records what each fold
    actually held, because "5 folds" over 17 igloo clusters is a different
    statement from "5 folds" over 65.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler

    predictions = np.empty(len(labels), dtype=object)
    folds = []

    splitter = GroupKFold(n_splits=FOLDS)
    for index, (train, test) in enumerate(splitter.split(features, labels, groups)):
        scaler = StandardScaler().fit(features[train])
        probe = LogisticRegression(
            penalty="l2", C=1.0, solver="lbfgs",
            max_iter=5000, class_weight="balanced", random_state=SEED,
        )
        probe.fit(scaler.transform(features[train]), labels[train])
        predictions[test] = probe.predict(scaler.transform(features[test]))
        folds.append({
            "fold": index,
            "train_crops": int(len(train)),
            "test_crops": int(len(test)),
            "train_clusters": int(len(set(groups[train]))),
            "test_clusters": int(len(set(groups[test]))),
            "test_class_counts": {
                str(k): int(v) for k, v in zip(*np.unique(labels[test], return_counts=True), strict=True)
            },
        })
    return predictions.astype(str), folds


def score(truth, predicted, classes):
    """Accuracy, balanced accuracy, the majority-class baseline, and a confusion.

    The baseline is reported with every headline on purpose. 0.75 pairwise
    accuracy on a 247/115 split is 0.68 of prevalence, and a decision rule that
    reads the raw number alone mistakes imbalance for skill.
    """
    import numpy as np
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix

    truth, predicted = np.asarray(truth), np.asarray(predicted)
    _, counts = np.unique(truth, return_counts=True)
    matrix = confusion_matrix(truth, predicted, labels=classes)
    return {
        "n": int(len(truth)),
        "classes": list(classes),
        "accuracy": float((truth == predicted).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(truth, predicted)),
        "majority_class_baseline": float(counts.max() / counts.sum()),
        "support": {
            str(k): int(v) for k, v in zip(*np.unique(truth, return_counts=True), strict=True)
        },
        # Rows are truth, columns are prediction, both in `classes` order.
        "confusion": matrix.tolist(),
    }


def main() -> None:
    unpack_bundle()
    install_dependencies()

    import numpy as np

    from sbr.config import load_config
    from sbr.dataset.expected import check_crop_composition, crop_counts, expectation_for
    from sbr.dataset.pool import crop_path, layout_of
    from sbr.utils.gpu import require_usable_gpu
    from sbr.utils.hub import configure_hf_runtime, download_dataset, resolve_revision

    configure_hf_runtime()
    config = load_config(CONFIG_NAME, PROJECT / "ml" / "configs")
    repo_id = config["data"]["repo_id"]
    versions = toolchain()
    log(f"toolchain: {json.dumps(versions)}")

    # The GPU BEFORE the pull. A refusal after the data is downloaded costs most
    # of what a failed run costs. See sbr.utils.gpu.
    accelerator = require_usable_gpu("embed the crops")

    revision = resolve_revision(repo_id, config["data"]["revision"], strict=True)
    pool_root = download_dataset(
        repo_id, revision=revision, local_dir=SCRATCH / "pool", strict=True
    )

    # The same contract the training kernel checks, for the same reason: this
    # probe decides a class list, and a class list decided against crops whose
    # labels moved is worse than no decision.
    expectation = expectation_for(repo_id)
    if expectation is None or revision != expectation.revision:
        raise SystemExit(
            f"{repo_id}@{revision[:12]} has no contract describing it. This probe "
            "decides B's class list; it does not run against unasserted labels."
        )
    pools = [p for p in sorted(pool_root.iterdir()) if (p / "manifest.json").exists()]
    manifests = {
        p.name: json.loads((p / "manifest.json").read_text(encoding="utf-8")) for p in pools
    }
    check_crop_composition(
        {name: crop_counts(m) for name, m in manifests.items()}, expectation
    )
    log(f"crop contract holds for {expectation.revision[:12]}")

    # ---------------------------------------------------------------------- #
    # The crops, their labels, their clusters, and their box areas
    # ---------------------------------------------------------------------- #
    from sbr.dataset.expected import ADJUDICATED

    paths, labels, groups, areas = [], [], [], []
    for pool in pools:
        manifest = manifests[pool.name]
        layout = layout_of(manifest)
        clusters = {r["file"]: r.get("capture_cluster", "") for r in manifest["records"]}
        for record in manifest.get("crop_records", []):
            if record.get("adjudication") not in ADJUDICATED:
                continue
            form_factor = record.get("form_factor")
            if not form_factor:
                continue
            paths.append(crop_path(pool, record["file"], layout))
            labels.append(form_factor)
            groups.append(clusters.get(record["frame"], record["frame"]))
            # Relative box area: the signal resizing throws away. bbox_norm is
            # (cx, cy, w, h) normalised, so w*h is the fraction of the frame.
            _, _, width, height = record["bbox_norm"]
            areas.append(float(width) * float(height))

    labels = np.asarray(labels)
    groups = np.asarray(groups)
    areas = np.asarray(areas, dtype=np.float32).reshape(-1, 1)
    log(
        f"{len(paths)} adjudicated crops over {len(set(groups))} capture clusters: "
        f"{json.dumps({str(k): int(v) for k, v in zip(*np.unique(labels, return_counts=True), strict=True)})}"
    )

    # `street_basket` is n=1 in one cluster: it cannot appear in a train fold and
    # a test fold, so it cannot be fitted or evaluated. Recorded, not merged.
    excluded = {
        NOT_EVALUABLE: {
            "crops": int((labels == NOT_EVALUABLE).sum()),
            "clusters": int(len(set(groups[labels == NOT_EVALUABLE]))),
            "why": "n=1 in one capture cluster - cannot be split across folds, so "
                   "it can be neither trained nor evaluated. Dropped from every "
                   "fitted number and RECORDED as a coverage gap, not merged into "
                   "anything on the strength of one photograph",
        }
    }
    keep = labels != NOT_EVALUABLE

    # ---------------------------------------------------------------------- #
    # Embeddings
    # ---------------------------------------------------------------------- #
    from transformers import AutoImageProcessor, AutoModel

    processor = AutoImageProcessor.from_pretrained(DINOV2)
    model = AutoModel.from_pretrained(DINOV2).to(accelerator.device).eval()
    dinov2_revision = getattr(getattr(model, "config", None), "_commit_hash", None)
    log(f"{DINOV2} loaded on {accelerator.device}, revision {dinov2_revision}")

    embeddings = embed(paths, model, processor, accelerator.device)
    log(f"embeddings: {embeddings.shape}")

    # ---------------------------------------------------------------------- #
    # The two variants, and the pairwise question inside each
    # ---------------------------------------------------------------------- #
    variants = {
        "a-embedding": embeddings,
        # One appended feature against 768. The scaler inside each fold is what
        # stops it being drowned, which is why the pre-registration names it.
        "b-embedding-plus-box-area": np.hstack([embeddings, areas]),
    }

    results = {}
    for name, features in variants.items():
        multiclass_classes = sorted(set(labels[keep]))
        predicted, folds = out_of_fold(features[keep], labels[keep], groups[keep])
        multiclass = score(labels[keep], predicted, multiclass_classes)
        multiclass["folds"] = folds

        # The decision rule's number: fitted on the two classes ONLY, so the
        # probe is not helped by having a third, easier class to push mass into.
        pair = np.isin(labels, PAIR)
        pair_predicted, pair_folds = out_of_fold(
            features[pair], labels[pair], groups[pair]
        )
        pairwise = score(labels[pair], pair_predicted, list(PAIR))
        pairwise["folds"] = pair_folds

        results[name] = {"multiclass": multiclass, "pairwise_wheelie": pairwise}
        log(
            f"{name}: pairwise acc {pairwise['accuracy']:.4f} "
            f"(baseline {pairwise['majority_class_baseline']:.4f}, "
            f"balanced {pairwise['balanced_accuracy']:.4f}) · "
            f"3-class acc {multiclass['accuracy']:.4f} "
            f"(balanced {multiclass['balanced_accuracy']:.4f})"
        )

    # ---------------------------------------------------------------------- #
    # What the rule reads. Stated, not applied - the class list is the
    # maintainer's decision and this kernel does not take it.
    # ---------------------------------------------------------------------- #
    without = results["a-embedding"]["pairwise_wheelie"]["accuracy"]
    with_area = results["b-embedding-plus-box-area"]["pairwise_wheelie"]["accuracy"]
    log(
        f"docs/12 P1 reads: embedding alone {without:.4f}, with box area "
        f"{with_area:.4f}, threshold 0.75. Which row fires is written down in the "
        "write-up; the CLASS LIST is the maintainer's decision and this kernel "
        "does not take it."
    )

    report = {
        "probe": "P1",
        "pre_registered": "docs/12 P1, amended and frozen 2026-08-21 before this ran",
        "hardware": {
            "accelerator": accelerator.name,
            "capability": accelerator.capability,
            "where": "Kaggle GPU kernel",
        },
        "toolchain": versions,
        "representation": {
            "model": DINOV2,
            "revision": dinov2_revision,
            "features": "CLS token, last hidden state",
            "dim": int(embeddings.shape[1]),
            "preprocessing": "AutoImageProcessor: resize 256, centre-crop 224, "
                             "ImageNet mean/std",
            "fine_tuned": False,
        },
        "estimator": {
            "probe": "LogisticRegression(l2, C=1.0, lbfgs, max_iter=5000, "
                     "class_weight=balanced, random_state=42)",
            "cv": f"GroupKFold(n_splits={FOLDS}) on capture_cluster",
            "scaling": "StandardScaler fitted INSIDE each fold",
            "aggregation": "out-of-fold predictions pooled across folds",
        },
        "dataset": {
            "repo_id": repo_id,
            "revision": revision,
            "crops": len(paths),
            "clusters": int(len(set(groups))),
            "class_counts": {
                str(k): int(v) for k, v in zip(*np.unique(labels, return_counts=True), strict=True)
            },
            "cluster_counts": {
                str(c): int(len(set(groups[labels == c]))) for c in sorted(set(labels))
            },
        },
        "excluded_from_every_fitted_number": excluded,
        "decision_rule_reads": {
            "pairwise_wheelie_accuracy_embedding_only": without,
            "pairwise_wheelie_accuracy_with_box_area": with_area,
            "threshold": 0.75,
        },
        "results": results,
    }
    out = WORKING / f"{NAME}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"wrote {out}")
    log(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
