#!/usr/bin/env python3
"""Export a trained checkpoint to ONNX locally, for exercising the service.

    python ml/scripts/export_local.py --role validator --version 1 --out artifacts/local

**Exporting is not training.** ``sbr.config.assert_cloud`` guards *training*
because a laptop cannot reproduce a GPU run; a graph conversion is
deterministic and has no such problem. This exists so the service can be pointed
at a real model, on a real frame, without a Cloud Run deployment.

**What it produces is deliberately not a shippable artefact**, and the sidecar
says so rather than leaving it to be inferred:

- it is **fp32**, so ``check_gates`` fails on *"artefact is not quantised"*;
- it carries **no latency measurement**, because this machine is not the
  service;
- the accuracy it records is the one measured elsewhere, on a named split,
  under the pinned runtime - it is **copied evidence, not a local measurement**,
  and every field says which.

An int8 export needs a calibration set drawn from the pinned pool, which is
37 913 files. That is what the Kaggle kernels are for; a local int8 graph
calibrated from some other set would be a different model wearing the same
version number.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.config import load_config  # noqa: E402
from sbr.export.onnx_export import (  # noqa: E402
    ExportReport,
    Gates,
    check_gates,
    export_onnx,
    write_sidecar,
)
from sbr.taxonomy import load_taxonomy  # noqa: E402
from sbr.utils.hub import configure_hf_runtime, load_hf_token  # noqa: E402

logger = logging.getLogger("export-local")

#: Measured elsewhere and copied in with its provenance. Never recomputed here:
#: this machine has neither the split nor the standing to produce these.
MEASURED = {
    "validator": {
        "map50_fp32": 0.7524389678079388,
        "accuracy_split": "test",
        "where": "Kaggle T4 training run, 2026-08-18; docs/11",
    },
}


def fetch_weights(repo: str, version: int, into: Path) -> Path:
    from huggingface_hub import hf_hub_download

    configure_hf_runtime()
    path = hf_hub_download(
        repo_id=repo,
        filename=f"v{version}/best.pt",
        local_dir=str(into),
        token=load_hf_token(),
    )
    return Path(path)


def class_list(role: str, weights: Path, config: dict) -> list[str]:
    """The class order the SERVED graph actually has.

    **Not the config's order, and this is a real trap rather than a hypothetical
    one.** Ultralytics builds a classification dataset from directory names, so
    the identifier's head is indexed **alphabetically over the classes that had
    crops** - `["igloo", "wheelie_large", "wheelie_small"]` - while
    `identifier.yaml` lists them as `["wheelie_small", "wheelie_large",
    "igloo"]`. A sidecar carrying the config's order would relabel every
    prediction: an igloo would be served as a small wheelie.

    So it is read back from the checkpoint, exactly as the training kernel does.
    The form-factor ids are canonical and permanent; their position in this
    particular head is incidental, and the sidecar is what the service trusts.

    The validator is a single class and has no such problem.
    """
    if role == "validator":
        return ["bin"]

    try:
        from ultralytics import YOLO

        names = YOLO(str(weights)).names
        return [names[index] for index in sorted(names)]
    except Exception as error:  # noqa: BLE001 - fall back, but say so loudly
        logger.warning(
            "could not read the class order from %s (%s); falling back to the "
            "config, which may not match the head",
            weights, type(error).__name__,
        )

    data = config.get("data", {})
    if data.get("classes_from_taxonomy"):
        return load_taxonomy().detector_classes
    return list(data["classes"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--role", choices=["validator", "identifier"], required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts/local"))
    parser.add_argument("--weights", type=Path, default=None, help="skip the download")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = load_config(args.role, ML_ROOT / "configs")
    args.out.mkdir(parents=True, exist_ok=True)

    weights = args.weights or fetch_weights(
        config["hub"]["model_repo"], args.version, args.out / "weights"
    )
    logger.info("weights: %s", weights)

    imgsz = int(config["export"]["imgsz"])
    fp32 = export_onnx(
        weights, args.out, imgsz=imgsz, opset=int(config["export"]["opset"]), role=args.role
    )

    # The served name, so `artefacts.py` finds it by the same convention the
    # Kaggle kernels use.
    served = args.out / f"{args.role}-v{args.version}.onnx"
    if fp32.resolve() != served.resolve():
        served.write_bytes(fp32.read_bytes())

    classes = class_list(args.role, weights, config)

    measured = MEASURED.get(args.role, {})
    report = ExportReport(
        role=args.role,
        version=args.version,
        onnx_path=served.name,
        size_bytes=served.stat().st_size,
        imgsz=imgsz,
        classes=classes,
        # FALSE, and that is the honest value. The service's gate will refuse
        # this artefact for exactly that reason, which is the gate working.
        quantised=False,
        map50_fp32=measured.get("map50_fp32"),
        top1_fp32=measured.get("top1_fp32"),
        accuracy_split=measured.get("accuracy_split"),
        median_latency_ms=None,
    )
    sidecar = write_sidecar(report, args.out, Gates.from_config(args.role, config))

    # Say where the numbers came from, inside the file somebody will read.
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["provenance"] = {
        "exported_by": "ml/scripts/export_local.py - a LOCAL export, not a kernel",
        "quantised": False,
        "why_not_quantised": (
            "an int8 export needs a calibration set from the pinned pool "
            "(37 913 files). A locally calibrated graph would be a different "
            "model wearing the same version number"
        ),
        "accuracy_measured_where": measured.get("where"),
        "accuracy_is": "copied from the run that measured it, not measured here",
        "latency_measured": False,
        "may_ship": False,
        "use": "exercising the service and the capture pipeline against real "
               "pixels. Not a deployment artefact",
    }
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    result = check_gates(report, Gates.from_config(args.role, config))
    result.log()
    logger.info(
        "wrote %s and %s. may_ship=%s - run the service with SBR_ALLOW_UNGATED=1 "
        "and SBR_ARTEFACT_DIR=%s",
        served.name, sidecar.name, result.may_ship, args.out,
    )


if __name__ == "__main__":
    main()
