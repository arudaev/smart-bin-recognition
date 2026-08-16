# ml/ – dataset, training, export

Python side of Smart Bin Recognition. Prepares the dataset, dispatches training
to a free Kaggle GPU kernel, and exports an ONNX model small enough to run in a
browser on an old phone.

Full design: [`docs/04-ml-pipeline.md`](../docs/04-ml-pipeline.md).

## Install

```bash
pip install -e ".[dev]"           # local work: taxonomy, tests, dispatch
pip install -e ".[dev,train,export]"   # only if you also need ultralytics/onnx locally
```

## Commands

```bash
# Validate the taxonomy and every region pack. Runs in CI.
python scripts/validate_taxonomy.py --skip-locales

# Tests
python -m pytest tests/ -q

# Check the archive against ml/configs/legacy_archive.yaml, then import
python scripts/inventory_legacy.py --archive-dir cv_garbage
python -m sbr.dataset.legacy_import --archive-dir cv_garbage --out data/legacy/pool

# The human pass – form factors for the legacy crops
python scripts/adjudicate.py --pool data/legacy/pool

# Publish a subset and pin the revision it prints
python scripts/push_dataset.py --pool data/legacy/pool --subset legacy

# Train on a Kaggle kernel (never locally)
python scripts/dispatch.py push validator --version 1
python scripts/dispatch.py status validator
python scripts/dispatch.py output validator --out artifacts/

# Ship gate: p50 measured on the 2-vCPU bench Space, then check_gates
python scripts/gate.py --role validator --version 1
```

## What the pieces do

| Module | Job |
|---|---|
| `sbr/taxonomy.py` | Load the ontology and region packs; **the resolver**. Mirrored in TypeScript in `web/src/domain/` – both must agree. |
| `sbr/config.py` | YAML `_defaults_` deep merge, plus the guard that refuses local training. |
| `sbr/dataset/legacy_import.py` | 2.15 GB of full-res phone JPEGs and four German class names → resized, ASCII-named, form-factor-labelled. |
| `sbr/dataset/prepare.py` | Group-aware and region-holdout splits, so eval numbers mean something. |
| `sbr/export/onnx_export.py` | ONNX → int8, and the four gates that decide whether it ships. |
| `sbr/escalation/schema.py` | The stage-3 VLM contract: canonical vocabulary only, citation mandatory. |
| `sbr/utils/hub.py` | HF token resolution, dataset download, artefact upload. |

## Two things worth knowing before you change anything

**Detector class order is the ONNX class index.** It comes from
`data/taxonomy/waste-streams.json` → `form_factors`, in file order. Reordering it
silently invalidates every deployed model. A test pins it.

**Training does not run locally.** `sbr.config.assert_cloud()` raises unless it
is on Kaggle or `SBR_ALLOW_LOCAL=1` is set. This exists because the predecessor's
notebook could not reproduce its own model and nobody noticed until submission.
