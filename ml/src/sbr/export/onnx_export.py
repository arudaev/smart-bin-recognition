"""Export a trained model to ONNX int8, and refuse to ship it if it is unfit.

The four gates in :func:`check_gates` are the reason this project can be free.
A model that fails any of them does not reach the service – the build fails
instead. See ``docs/04-ml-pipeline.md`` § 6 and ``docs/05-cost-model.md`` § 3.

NMS is deliberately *excluded* from the graph: it runs as postprocess in the
inference service. Keeping it out of the graph keeps the export portable across
runtimes and costs ~30 lines either way.

**Two roles, two accuracy metrics.** The validator is a one-class detector and
is judged on mAP@0.5; the identifier is a classifier over crops and is judged on
top-1. The int8 budget – two points – is the same for both.

**Who measures what.** The training kernel measures accuracy, fp32 *and* int8
(:func:`evaluate_int8`), because it is the only place holding both the artefact
and the split. ``ml/scripts/gate.py`` measures latency, because that is the only
thing a training kernel cannot measure. Between them every gate has an owner –
which was not true until 2026-08-16, when int8 accuracy had none and
:attr:`GateResult.may_ship` was consequently unreachable.

**Latency is never guessed.** A model whose latency has not been measured on the
service CPU is *unmeasured*, not *passing*: see :class:`GateResult`. The Kaggle
kernel cannot measure it (it has a GPU and a different CPU), so it exports and
uploads with latency pending, and ``ml/scripts/gate.py`` decides shipping once
the 2-vCPU bench has spoken.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROLES = ("validator", "identifier")

#: Which accuracy metric each role is judged on. Not a tuning knob – it follows
#: from the architecture (detector vs classifier), so it lives in source.
ACCURACY_METRIC = {"validator": "map50", "identifier": "top1"}


@dataclass(frozen=True)
class Gates:
    """The ship gates, as configured. Loaded from ``ml/configs/<role>.yaml``.

    Hard-coding these would put a product decision in source where a tuning
    change could quietly ride along with it. They live in config, and
    ``ml/tests/test_export_gates.py`` pins the configured values – so loosening
    a gate fails CI rather than shipping.
    """

    role: str
    max_median_latency_ms: float
    max_accuracy_drop: float

    @classmethod
    def from_config(cls, role: str, config: dict[str, Any]) -> Gates:
        if role not in ROLES:
            raise ValueError(f"unknown model role {role!r}; expected one of {ROLES}")
        gates = config.get("export", {}).get("gates", {})
        missing = {"max_median_latency_ms", "max_accuracy_drop"} - set(gates)
        if missing:
            raise ValueError(
                f"config for role {role!r} is missing export.gates: {sorted(missing)}"
            )
        return cls(
            role=role,
            max_median_latency_ms=float(gates["max_median_latency_ms"]),
            max_accuracy_drop=float(gates["max_accuracy_drop"]),
        )

    @classmethod
    def for_role(cls, role: str) -> Gates:
        """Load the gates for a role from ``ml/configs/``."""
        from sbr.config import load_config

        return cls.from_config(role, load_config(role))


@dataclass(frozen=True)
class Targets:
    """The accuracy targets from ``docs/04-ml-pipeline.md`` § 7. **Reported,
    never gating.**

    The distinction from :class:`Gates` is deliberate and is a product decision.
    A gate is arithmetic the free tier depends on: miss it and the service costs
    money, so the build fails. A target is how good the model is: miss it and
    the answer is to write the number down and go and fix it, not to refuse to
    ship the only model that exists.

    They were unread until 2026-08-16 – ``Gates.from_config`` looks only at
    ``export.gates`` – which meant a fast but useless model produced a sidecar
    indistinguishable from a good one.
    """

    role: str
    values: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_config(cls, role: str, config: dict[str, Any]) -> Targets:
        raw = config.get("export", {}).get("targets", {}) or {}
        return cls(role=role, values={k: float(v) for k, v in raw.items()})

    @classmethod
    def for_role(cls, role: str) -> Targets:
        from sbr.config import load_config

        return cls.from_config(role, load_config(role))


@dataclass(frozen=True)
class TargetResult:
    """Which targets were met, missed, or could not be measured at all.

    ``unmeasurable`` is the row that matters most today: the held-out-city
    targets need a second `region_id`, and no subset of the pinned dataset has
    one (docs/04 § 5). Reporting them as *missing evidence* rather than omitting
    them is what stops the generalisation question being quietly dropped.
    """

    met: dict[str, float] = field(default_factory=dict)
    missed: dict[str, tuple[float, float]] = field(default_factory=dict)
    unmeasurable: list[str] = field(default_factory=list)

    def log(self) -> None:
        for name, value in self.met.items():
            logger.info("target met: %s = %.4f", name, value)
        for name, (value, target) in self.missed.items():
            logger.warning("TARGET MISSED: %s = %.4f, target %.4f", name, value, target)
        for name in self.unmeasurable:
            logger.warning("TARGET UNMEASURABLE: %s - no measurement exists for it", name)


def check_targets(measured: dict[str, float | None], targets: Targets) -> TargetResult:
    """Compare measurements against the role's targets.

    ``measured`` is keyed by target name, so the caller states which measurement
    answers which target rather than this module guessing from a metric name.
    A key that is absent or ``None`` is *unmeasurable*, never a pass.
    """
    result = TargetResult()
    for name, target in sorted(targets.values.items()):
        value = measured.get(name)
        if value is None:
            result.unmeasurable.append(name)
        elif value >= target:
            result.met[name] = value
        else:
            result.missed[name] = (value, target)
    return result


@dataclass
class ExportReport:
    """Everything the service and the ship gate need to know about an artefact."""

    role: str                      # "validator" | "identifier"
    version: int
    onnx_path: str
    size_bytes: int
    imgsz: int
    classes: list[str]
    quantised: bool = False

    # Accuracy, per role: mAP@0.5 for the validator, top-1 for the identifier.
    map50_fp32: float | None = None
    map50_int8: float | None = None
    top1_fp32: float | None = None
    top1_int8: float | None = None

    # Latency, and the machine it was measured on. Both or neither.
    median_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    latency_hardware: str | None = None

    #: Measurements answering ``export.targets``, keyed by target name. A target
    #: with no key here is reported *unmeasurable* rather than skipped – see
    #: :class:`TargetResult`.
    targets_measured: dict[str, float | None] = field(default_factory=dict)

    @property
    def accuracy_metric(self) -> str:
        return ACCURACY_METRIC.get(self.role, "map50")

    @property
    def accuracy_pair(self) -> tuple[float | None, float | None]:
        """(fp32, int8) for whichever metric this role is judged on."""
        if self.accuracy_metric == "top1":
            return self.top1_fp32, self.top1_int8
        return self.map50_fp32, self.map50_int8

    @property
    def accuracy_drop(self) -> float | None:
        fp32, int8 = self.accuracy_pair
        if fp32 is None or int8 is None:
            return None
        return fp32 - int8


@dataclass(frozen=True)
class GateResult:
    """The verdict. ``failures`` is measured and over budget; ``unmeasured`` is
    not yet judgeable.

    The distinction matters because the two are acted on differently: a failure
    is a result and stops the build, while an unmeasured gate means the evidence
    is still missing. Neither is permission to ship – only :attr:`may_ship` is.
    """

    failures: list[str] = field(default_factory=list)
    unmeasured: list[str] = field(default_factory=list)

    @property
    def may_ship(self) -> bool:
        return not self.failures and not self.unmeasured

    def log(self) -> None:
        for failure in self.failures:
            logger.error("SHIP GATE FAILED: %s", failure)
        for pending in self.unmeasured:
            logger.warning("SHIP GATE UNMEASURED: %s", pending)


def check_gates(report: ExportReport, gates: Gates) -> GateResult:
    """Apply the four ship gates.

    Model size is deliberately *not* gated: inference is server-side, so the
    artefact ships once to one machine. Latency is gated instead, because
    concurrency is what actually costs money (docs/05-cost-model.md § 3).
    """
    failures: list[str] = []
    unmeasured: list[str] = []

    # 1. The role must be one this pipeline knows how to judge.
    if report.role not in ROLES:
        failures.append(f"unknown model role {report.role!r}; expected one of {ROLES}")
    elif report.role != gates.role:
        failures.append(
            f"gates are for role {gates.role!r} but the artefact is {report.role!r}"
        )

    # 2. Median latency on the service CPU.
    if report.median_latency_ms is None:
        unmeasured.append(
            f"median latency for the {report.role} has not been measured on the "
            "service CPU – run ml/scripts/gate.py against the bench"
        )
    elif not report.latency_hardware:
        failures.append(
            "median latency was recorded without naming the hardware it was "
            "measured on; an unattributed latency number is not evidence"
        )
    elif report.median_latency_ms > gates.max_median_latency_ms:
        failures.append(
            f"median latency {report.median_latency_ms:.1f} ms exceeds the "
            f"{gates.max_median_latency_ms:.0f} ms budget for the {report.role} "
            f"(measured on {report.latency_hardware})"
        )

    # 3. What int8 quantisation cost, in the metric this role is judged on.
    drop = report.accuracy_drop
    if drop is None:
        unmeasured.append(
            f"int8 {report.accuracy_metric} drop for the {report.role} is unmeasured "
            f"(need both fp32 and int8 {report.accuracy_metric})"
        )
    elif drop > gates.max_accuracy_drop:
        failures.append(
            f"int8 quantisation cost {drop:.3f} {report.accuracy_metric} "
            f"(max {gates.max_accuracy_drop})"
        )

    # 4. It must actually be quantised.
    if not report.quantised:
        failures.append("artefact is not quantised – it will not meet the latency budget")

    return GateResult(failures=failures, unmeasured=unmeasured)


def batched_role(role: str) -> bool:
    """Whether this role's graph must accept a batch of more than one.

    The identifier runs **per crop**, and a frame can hold several bins – the
    PRD calls a bank of six a normal input. ``docs/01-architecture.md`` § 4 makes
    pushing those crops through *one* ONNX call a service requirement rather than
    an optimisation, and a graph exported with a fixed batch of 1 simply cannot
    do it. So the identifier gets a dynamic batch axis and the validator does
    not: the validator sees exactly one frame, every time, and a static shape is
    the faster and more predictable export.
    """
    return role == "identifier"


def export_onnx(weights: Path, out_dir: Path, imgsz: int, opset: int, role: str) -> Path:
    """Export ``best.pt`` to ONNX. Returns the fp32 ONNX path.

    ``role`` decides whether the batch axis is dynamic – see :func:`batched_role`.
    It is a required argument rather than a flag with a default because getting it
    wrong is silent: a static identifier graph loads, serves, and quietly forces
    the service back to *n* sequential calls.
    """
    from ultralytics import YOLO  # imported lazily – the web CI does not have it

    out_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(weights))

    options: dict[str, Any] = {
        "format": "onnx",
        "imgsz": imgsz,
        "opset": opset,
        "simplify": True,
        "dynamic": batched_role(role),
        "half": False,
    }
    # `nms` is a detection argument. The identifier is a classifier and has no
    # boxes to suppress, so passing it there is at best ignored and at worst an
    # error, depending on the ultralytics version.
    if role == "validator":
        options["nms"] = False   # postprocess runs in the service

    exported = model.export(**options)
    exported = Path(exported)
    target = out_dir / "model-fp32.onnx"
    target.write_bytes(exported.read_bytes())
    logger.info("exported fp32 ONNX: %.2f MB", target.stat().st_size / 1e6)
    return target


def quantise(
    fp32_path: Path,
    calibration_dir: Path,
    out_path: Path,
    imgsz: int,
    calibration_images: int,
) -> Path:
    """Static int8 quantisation, calibrated on real images.

    Static, not dynamic: dynamic quantisation is measurably worse on
    convolutional backbones because the activation ranges vary enormously
    between the backbone and the head.
    """
    import numpy as np
    from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
    from PIL import Image

    images = sorted(
        p for p in calibration_dir.rglob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )[:calibration_images]
    if not images:
        raise FileNotFoundError(f"no calibration images in {calibration_dir}")
    logger.info("calibrating on %d images from %s", len(images), calibration_dir)

    class _Reader(CalibrationDataReader):
        def __init__(self) -> None:
            self._iter = iter(images)

        def get_next(self) -> dict | None:
            path = next(self._iter, None)
            if path is None:
                return None
            # Not rebound onto the `with` target: that is an ImageFile, and
            # convert() returns an Image, so reusing the name is a type error.
            with Image.open(path) as handle:
                frame = handle.convert("RGB").resize((imgsz, imgsz), Image.Resampling.BILINEAR)
                array = np.asarray(frame, dtype=np.float32).transpose(2, 0, 1) / 255.0
            return {"images": array[None, ...]}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    quantize_static(
        model_input=str(fp32_path),
        model_output=str(out_path),
        calibration_data_reader=_Reader(),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
    )
    logger.info(
        "quantised: %.2f MB -> %.2f MB",
        fp32_path.stat().st_size / 1e6,
        out_path.stat().st_size / 1e6,
    )
    return out_path


def evaluate_int8(
    onnx_path: Path,
    *,
    role: str,
    data: Path | str,
    imgsz: int,
    split: str = "test",
) -> float | None:
    """Score the **quantised** graph, in the metric this role is judged on.

    Gate 3 compares fp32 against int8, so somebody has to measure int8. It has
    to be here rather than in ``ml/scripts/gate.py``: the training kernel is the
    only place that holds both the artefact and the split the fp32 number came
    from, and a drop computed against a *different* split is not a drop.

    Scored through ultralytics for the same reason – the fp32 number came from
    ``model.val()``, and two metrics computed by two implementations are not
    comparable to two decimal places, which is the resolution the 0.02 gate
    needs.

    Returns ``None`` if the quantised graph could not be scored, which leaves
    the gate **unmeasured** rather than passed. That is the honest verdict and
    :class:`GateResult` already distinguishes it from a failure.
    """
    from ultralytics import YOLO

    task = "classify" if role == "identifier" else "detect"
    try:
        metrics = YOLO(str(onnx_path), task=task).val(
            data=str(data), imgsz=imgsz, split=split, verbose=False
        )
    except Exception as error:  # noqa: BLE001 – any failure here means "unmeasured"
        logger.error(
            "could not score the int8 graph (%s: %s). The int8 accuracy gate "
            "stays UNMEASURED, so this artefact cannot ship until it is scored.",
            type(error).__name__, error,
        )
        return None

    value = float(metrics.top1) if task == "classify" else float(metrics.box.map50)
    logger.info("int8 %s on %s = %.4f", ACCURACY_METRIC[role], split, value)
    return value


def sidecar_path(out_dir: Path, role: str, version: int) -> Path:
    return out_dir / f"{role}-v{version}.json"


def write_sidecar(report: ExportReport, out_dir: Path, gates: Gates | None = None) -> Path:
    """Write the JSON sidecar the inference service and the gate script read.

    Nothing about the model is hard-coded in the service – class names, input
    shape and normalisation all come from here, so a model swap needs no code
    change. The gate verdict rides along so that an artefact can never be
    promoted without its evidence.
    """
    gates = gates or Gates.for_role(report.role)
    result = check_gates(report, gates)

    # Targets ride along beside the gates and never affect `may_ship`. Their
    # value is that docs/11 can be generated from the sidecar rather than typed.
    targets = Targets.for_role(report.role)
    target_result = check_targets(report.targets_measured, targets)

    payload = asdict(report) | {
        "accuracy_metric": report.accuracy_metric,
        "accuracy_drop": report.accuracy_drop,
        "normalisation": {"scale": 1 / 255.0, "mean": [0, 0, 0], "std": [1, 1, 1]},
        "input_name": "images",
        "layout": "NCHW",
        # Whether the service may push several crops through one call. Read, not
        # assumed: a graph exported with a fixed batch of 1 loads and serves
        # perfectly well, and would silently cost n sequential calls per frame.
        "dynamic_batch": batched_role(report.role),
        "nms": {"in_graph": False, "iou": 0.45, "score": 0.35},
        "gates": asdict(gates),
        "gate_result": {
            "failures": result.failures,
            "unmeasured": result.unmeasured,
            "may_ship": result.may_ship,
        },
        "targets": targets.values,
        "target_result": {
            "met": target_result.met,
            "missed": {k: {"value": v, "target": t} for k, (v, t) in target_result.missed.items()},
            "unmeasurable": target_result.unmeasurable,
        },
    }

    path = sidecar_path(out_dir, report.role, report.version)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_sidecar(path: Path) -> ExportReport:
    """Rebuild an :class:`ExportReport` from a sidecar written earlier."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = {f for f in ExportReport.__dataclass_fields__}
    return ExportReport(**{k: v for k, v in raw.items() if k in fields})


def main() -> None:
    from sbr.config import load_config
    from sbr.taxonomy import load_taxonomy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--map50-fp32", type=float, default=None)
    parser.add_argument("--map50-int8", type=float, default=None)
    parser.add_argument("--top1-fp32", type=float, default=None)
    parser.add_argument("--top1-int8", type=float, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = load_config(args.role)
    gates = Gates.from_config(args.role, config)
    imgsz = int(config["export"]["imgsz"])

    fp32 = export_onnx(
        args.weights, args.out, imgsz=imgsz, opset=int(config["export"]["opset"]), role=args.role
    )
    int8 = quantise(
        fp32,
        args.calibration,
        args.out / f"{args.role}-v{args.version}.onnx",
        imgsz=imgsz,
        calibration_images=int(config["export"]["calibration_images"]),
    )

    classes = ["bin"] if args.role == "validator" else load_taxonomy().detector_classes
    report = ExportReport(
        role=args.role,
        version=args.version,
        onnx_path=str(int8),
        size_bytes=int8.stat().st_size,
        imgsz=imgsz,
        classes=classes,
        quantised=True,
        map50_fp32=args.map50_fp32,
        map50_int8=args.map50_int8,
        top1_fp32=args.top1_fp32,
        top1_int8=args.top1_int8,
    )
    sidecar = write_sidecar(report, args.out, gates)
    logger.info("wrote %s", sidecar)

    result = check_gates(report, gates)
    result.log()
    if result.failures:
        raise SystemExit(1)
    if result.unmeasured:
        logger.info(
            "export complete; latency is still unmeasured. Run "
            "`python ml/scripts/gate.py --role %s --version %d` to decide shipping.",
            args.role, args.version,
        )
        return
    logger.info("all ship gates passed: %s", int8)


if __name__ == "__main__":
    main()
