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

# Import the predecessor's dataset – resize, rename, remap
python -m sbr.dataset.legacy_import --archive cv_garbage.zip --out data/legacy

# Train on a Kaggle GPU kernel (never locally)
python scripts/dispatch.py push detector --version 1
python scripts/dispatch.py status detector
python scripts/dispatch.py output detector --out artifacts/

# Export + quantise + check ship gates
python -m sbr.export.onnx_export --weights best.pt --calibration data/val --version 1
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
