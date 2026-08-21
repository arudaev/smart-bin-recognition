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
import hashlib
import json
import logging
import random
import re
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

    #: Which split the accuracy pair above was measured on.
    #:
    #: A number without its split is not evidence, and the sidecar is what the
    #: service and docs/11 both read. It matters most in the case that actually
    #: happens: when no export variant is eligible, the honest record is the
    #: `val` drop that was measured and missed - reporting it as *unmeasured*
    #: would understate the evidence, and reporting it without saying `val`
    #: would imply a `test` confirmation nobody is entitled to.
    accuracy_split: str | None = None

    # Latency, and the machine it was measured on. Both or neither.
    median_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    latency_hardware: str | None = None

    #: Was that machine the deployment target? ``sbr.bench.Hardware.representative``.
    #:
    #: **This is what makes "a proxy does not close the latency gate" a rule
    #: rather than a sentence.** Every document in this project says it; until
    #: 2026-08-21 nothing enforced it. `check_gates` required only that the
    #: hardware be *named*, so a Kaggle kernel's number - free, x86, and
    #: explicitly `representative: false` - could carry an artefact to
    #: `may_ship: true`. The budget is stated *on service CPU*, and a number
    #: from somewhere else does not answer it.
    #:
    #: ``None`` means nobody recorded it, which is treated as "not established"
    #: rather than assumed either way.
    latency_representative: bool | None = None

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
    elif not report.latency_representative:
        # UNMEASURED, not a failure, and the distinction is the whole point: the
        # graph may well be fast enough, and nobody has measured it where the
        # budget is stated. `unmeasured` says "the evidence is still missing",
        # which is exactly true, and it blocks may_ship just as firmly.
        unmeasured.append(
            f"median latency for the {report.role} was measured on "
            f"{report.latency_hardware!r}, which is not the service. It read "
            f"{report.median_latency_ms:.1f} ms against a "
            f"{gates.max_median_latency_ms:.0f} ms budget, and that is a proxy "
            "figure - the budget is stated on service CPU. A controlled host is "
            "what closes this"
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


# --------------------------------------------------------------------------- #
# Quantisation - the knobs onnxruntime's own guidance actually turns
# --------------------------------------------------------------------------- #

#: Where the detection head starts in a YOLO11 ONNX graph. Node names look like
#: ``/model.23/cv2.0/cv2.0.0/conv/Conv``. It is a *setting* rather than a
#: constant because it is architecture-specific and must be verified against the
#: graph in hand - see :func:`head_node_names`, which refuses to guess.
DEFAULT_HEAD_PREFIX = "/model.23/"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class QuantSettings:
    """How a graph is quantised. **The defaults are what shipped v1.**

    Every field here corresponds to something onnxruntime's quantisation
    guidance says to turn when accuracy collapses, and the reason they exist as
    settings rather than as literals is docs/12 P9: the v1 validator lost 0.727
    mAP to int8 and the cause could not be isolated without moving one of them
    at a time.

    Two are worth calling out because they are the documented first suspects on
    x86 CPU. ``activation_type``/``weight_type`` default to **U8S8**, which is
    what v1 used; onnxruntime names **S8S8 the normal CPU choice** and describes
    a large U8S8 loss as a symptom of *activation saturation* on x86, whose
    remedies are ``reduce_range`` or U8U8.
    """

    activation_type: str = "u8"
    weight_type: str = "s8"
    reduce_range: bool = False
    per_channel: bool = True
    calibrate_method: str = "minmax"
    #: onnxruntime's ``quant_pre_process`` - symbolic shape inference and
    #: constant folding before quantisation. Off in v1, and its guidance says
    #: this alone can account for accuracy loss.
    preprocess: bool = False
    #: How a calibration image is fitted to the square input. **v1 stretched.**
    #: ``model.val()`` and ``service/pipeline.py`` both *letterbox*, so a
    #: stretched calibration set measures ranges on a geometry that never occurs
    #: at inference, and never on the 114-grey bars a real frame carries.
    calibration_fit: str = "stretch"
    #: Leave the detection head in fp32. Box regression outputs are wide-range
    #: and are the standard suspect when a detector survives classification
    #: quantisation and loses its boxes.
    exclude_head: bool = False
    head_prefix: str = DEFAULT_HEAD_PREFIX
    #: Further module prefixes to leave in fp32, for docs/12 P10. P9 showed the
    #: head causes the collapse; it did not show nothing else matters, and the
    #: head-fp32 graph still carries 619 QDQ nodes and still loses 0.0252. Each
    #: prefix must match at least one node or the export refuses - a variant
    #: named "model.10 in fp32" that excluded nothing would measure the wrong
    #: thing under the right label, which is the failure `head_node_names`
    #: already exists to prevent.
    exclude_prefixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, allowed in (
            ("activation_type", {"u8", "s8"}),
            ("weight_type", {"u8", "s8"}),
            ("calibrate_method", {"minmax", "entropy", "percentile"}),
            ("calibration_fit", {"stretch", "letterbox"}),
        ):
            value = getattr(self, field_name)
            if value not in allowed:
                raise ValueError(f"{field_name}={value!r}; expected one of {sorted(allowed)}")

    @property
    def format(self) -> str:
        """``"u8s8"`` and friends - the pair onnxruntime's guidance talks about."""
        return f"{self.activation_type}{self.weight_type}"

    @property
    def departures(self) -> tuple[str, ...]:
        """Which fields differ from the shipped defaults.

        docs/12 P9's tie-break prefers the *simpler* configuration when two
        variants are within measurement noise, and "simpler" has to mean
        something countable rather than something argued.
        """
        default = QuantSettings()
        return tuple(
            name for name in self.__dataclass_fields__
            if getattr(self, name) != getattr(default, name)
        )

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class CalibrationSet:
    """The exact images a quantisation was calibrated on, and their fingerprint.

    Recorded rather than described because describing it is how docs/12 P9 came
    to assert the wrong thing twice. The set was written up as "``val``, which is
    92 % background"; ``val`` is 91.46 % background but the 200 files
    :func:`quantise` actually saw were **149 background and 51 positive, all of
    them legacy or negatives, with no Open Images frame at all** - because the
    selection was ``sorted(...)[:200]`` over names of the form ``<pool>__<file>``
    and ``open_images__`` sorts after ``negatives__``.

    So the ordered list and its hash travel with every number derived from it.
    """

    images: tuple[Path, ...]
    strategy: str
    split: str
    seed: int
    #: ``None`` where the layout carries no labels - a classification tree has
    #: no background frames to count, and reporting 0 would be a claim rather
    #: than an absence.
    positives: int | None
    background: int | None
    sources: dict[str, int]

    @property
    def sha256(self) -> str:
        """Fingerprint of the ordered *names*, not the pixels.

        Names, because the question this answers is "was this the same set of
        frames in the same order", and the pixels behind a pinned dataset
        revision cannot change without the pin changing.
        """
        joined = "\n".join(path.name for path in self.images)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "split": self.split,
            "seed": self.seed,
            "count": len(self.images),
            "positives": self.positives,
            "background": self.background,
            "background_fraction": (
                round(self.background / len(self.images), 4)
                if self.background is not None and self.images else None
            ),
            "sources": dict(sorted(self.sources.items())),
            "sha256": self.sha256,
        }

    def manifest(self) -> dict[str, Any]:
        """The summary **and the complete ordered list**.

        Separate from :meth:`as_dict` so a result file can carry each set once
        and have every row reference it by hash, rather than repeating 200
        filenames a dozen times. The list itself is not optional: docs/12 P9
        promises that the exact frames behind a number are recorded, and an
        earlier version kept only the hash and the first five names - which
        fingerprints a set without ever saying what is in it.
        """
        return self.as_dict() | {"images": [path.name for path in self.images]}


def _source_of(image: Path) -> str:
    """Which pool a tree filename came from. ``prepare._qualified`` writes
    ``<pool>__<file>``, and that prefix is the only provenance the flat tree
    carries."""
    name = image.name
    return name.split("__", 1)[0] if "__" in name else "unknown"


def _is_positive(labels_dir: Path, image: Path) -> bool:
    """A frame with at least one box. An empty label file is a background frame
    on purpose - the negative corpus ships them empty rather than absent, because
    YOLO drops an image whose label file is missing."""
    label = labels_dir / f"{image.stem}.txt"
    return label.exists() and bool(label.read_text(encoding="utf-8").strip())


def calibration_frames(
    tree: Path,
    split: str,
    limit: int,
    *,
    strategy: str = "first_lexicographic",
    seed: int = 42,
) -> CalibrationSet:
    """Choose the images a static quantisation calibrates on.

    Three strategies, and the first is a bug that is kept deliberately:

    ``first_lexicographic``
        What v1 did - ``sorted(...)[:limit]``. Systematic, not random: on the
        pinned tree it yields 51 legacy frames, 149 negatives and **zero Open
        Images frames**. It is retained so docs/12 P9 can *reproduce* the failure
        rather than assert a cause for it.
    ``stratified``
        Proportional across pools, sampled with ``seed``. The representative
        sample the first one was mistaken for.
    ``positive_enriched``
        Half frames with boxes, half without. Whether the activation ranges want
        to see more bins than the corpus contains is a question, not an answer.
    """
    # The two roles have two tree shapes and the layout is read off disk rather
    # than assumed: the validator gets `images/<split>` beside `labels/<split>`
    # from `build_yolo_tree`, the identifier a flat `<split>/<class>/` from
    # `build_classification_tree`, which carries no label files at all.
    images_dir, labels_dir = tree / "images" / split, tree / "labels" / split
    if not images_dir.is_dir():
        images_dir, labels_dir = tree / split, None
    if not images_dir.is_dir():
        raise FileNotFoundError(f"no {split} split under {tree}")

    frames = sorted(p for p in images_dir.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
    if not frames:
        raise FileNotFoundError(f"no calibration images in {images_dir}")

    rng = random.Random(seed)
    if strategy == "first_lexicographic":
        chosen = frames[:limit]
    elif strategy == "stratified":
        chosen = _stratified(frames, limit, rng)
    elif strategy == "positive_enriched":
        if labels_dir is None:
            raise ValueError(
                "positive_enriched needs label files to know which frames hold a "
                f"box, and {tree}/{split} carries none"
            )
        chosen = _positive_enriched(frames, labels_dir, limit, rng)
    else:
        raise ValueError(
            f"unknown calibration strategy {strategy!r}; expected one of "
            "first_lexicographic, stratified, positive_enriched"
        )

    positives = (
        sum(1 for image in chosen if _is_positive(labels_dir, image))
        if labels_dir is not None else None
    )
    sources: dict[str, int] = {}
    for image in chosen:
        sources[_source_of(image)] = sources.get(_source_of(image), 0) + 1

    return CalibrationSet(
        images=tuple(chosen),
        strategy=strategy,
        split=split,
        seed=seed,
        positives=positives,
        background=None if positives is None else len(chosen) - positives,
        sources=sources,
    )


def _stratified(frames: list[Path], limit: int, rng: random.Random) -> list[Path]:
    """Proportional across pools, largest-remainder, then sorted for stability."""
    groups: dict[str, list[Path]] = {}
    for frame in frames:
        groups.setdefault(_source_of(frame), []).append(frame)

    total = len(frames)
    exact = {name: len(members) * limit / total for name, members in groups.items()}
    quota = {name: int(value) for name, value in exact.items()}
    # Hand the rounding remainder to the largest fractions, deterministically.
    remainder = limit - sum(quota.values())
    for name, _ in sorted(exact.items(), key=lambda item: (-(item[1] % 1), item[0]))[:remainder]:
        quota[name] += 1

    chosen: list[Path] = []
    for name in sorted(groups):
        members = sorted(groups[name])
        take = min(quota.get(name, 0), len(members))
        chosen.extend(rng.sample(members, take))
    return sorted(chosen)


def _positive_enriched(
    frames: list[Path], labels_dir: Path, limit: int, rng: random.Random
) -> list[Path]:
    """Half with boxes, half without - or as close as the split allows."""
    positives = sorted(f for f in frames if _is_positive(labels_dir, f))
    background = sorted(f for f in frames if f not in set(positives))

    want = limit // 2
    take_positive = min(want, len(positives))
    take_background = min(limit - take_positive, len(background))
    chosen = rng.sample(positives, take_positive) + rng.sample(background, take_background)
    return sorted(chosen)


def head_node_names(onnx_path: Path, prefix: str = DEFAULT_HEAD_PREFIX) -> list[str]:
    """Nodes belonging to the detection head, by an **explicitly given** prefix.

    Deliberately not inferred. An earlier draft of this took "every node whose
    name does not match ``/model.<i>/``" to be head plumbing; on the real v1
    graph that sweeps in a large number of generated nodes that have nothing to
    do with the head, and the resulting variant would have been reported as
    "head excluded" while excluding something else entirely.

    Raises rather than returning an empty list, so ``exclude_head=True`` can
    never quietly quantise the whole graph and report itself as the head-excluded
    variant. The error names the prefixes the graph *does* carry.
    """
    import onnx

    model = onnx.load(str(onnx_path))
    names = [node.name for node in model.graph.node if prefix in node.name]
    if not names:
        present = sorted(
            {match.group(0) for node in model.graph.node
             if (match := re.match(r"/model\.\d+/", node.name))},
            key=lambda item: int(item.split(".")[1].rstrip("/")),
        )
        raise ValueError(
            f"no node in {onnx_path.name} carries the prefix {prefix!r}, so "
            "'leave the head in fp32' would have quantised everything and said "
            f"otherwise. Prefixes this graph does carry: {present[-4:] or 'none'}"
        )
    return names


def nodes_matching(onnx_path: Path, prefixes: tuple[str, ...]) -> list[str]:
    """Every node under any of ``prefixes``. Refuses a prefix that matches none.

    The same discipline as :func:`head_node_names` and for the same reason: an
    exclusion list that silently comes back empty produces a graph quantised
    everywhere, reported under the name of the thing it did not exclude.
    """
    import onnx

    model = onnx.load(str(onnx_path))
    names: list[str] = []
    for prefix in prefixes:
        matched = [node.name for node in model.graph.node if prefix in node.name]
        if not matched:
            present = sorted(
                {match.group(0) for node in model.graph.node
                 if (match := re.match(r"/model\.\d+/", node.name))},
                key=lambda item: int(item.split(".")[1].rstrip("/")),
            )
            raise ValueError(
                f"prefix {prefix!r} matches no node in {onnx_path.name}, so excluding "
                f"it would exclude nothing. Prefixes this graph carries: {present}"
            )
        names.extend(matched)
    return sorted(set(names))


def quant_boundary(onnx_path: Path, prefix: str = DEFAULT_HEAD_PREFIX) -> dict[str, int]:
    """Where the QDQ pairs actually landed, counted inside and outside the head.

    The point of an exclusion list is a *boundary*, and a boundary that is
    assumed rather than looked at is how a variant comes to measure something
    other than its name. Reported beside every quantised row.
    """
    import onnx

    model = onnx.load(str(onnx_path))
    inside = outside = 0
    for node in model.graph.node:
        if node.op_type not in {"QuantizeLinear", "DequantizeLinear"}:
            continue
        if prefix in node.name:
            inside += 1
        else:
            outside += 1
    return {
        "qdq_nodes_in_head": inside,
        "qdq_nodes_outside_head": outside,
        "total_nodes": len(model.graph.node),
    }


def _quant_type(name: str) -> Any:
    from onnxruntime.quantization import QuantType

    return {"u8": QuantType.QUInt8, "s8": QuantType.QInt8}[name]


def _calibrate_method(name: str) -> Any:
    from onnxruntime.quantization import CalibrationMethod

    return {
        "minmax": CalibrationMethod.MinMax,
        "entropy": CalibrationMethod.Entropy,
        "percentile": CalibrationMethod.Percentile,
    }[name]


def _fit(handle: Any, imgsz: int, how: str) -> Any:
    """Fit one calibration image to the square input, stretched or letterboxed.

    The letterbox arm mirrors ``service/pipeline.py:letterbox`` - aspect
    preserved, padded with the usual YOLO 114-grey - because the ranges being
    measured are the ranges the service will actually feed the graph.
    """
    import numpy as np
    from PIL import Image

    frame = handle.convert("RGB")
    if how == "stretch":
        return np.asarray(frame.resize((imgsz, imgsz), Image.Resampling.BILINEAR), dtype=np.uint8)

    width, height = frame.size
    scale = min(imgsz / width, imgsz / height)
    new_w, new_h = max(1, round(width * scale)), max(1, round(height * scale))
    resized = np.asarray(frame.resize((new_w, new_h), Image.Resampling.BILINEAR), dtype=np.uint8)
    canvas = np.full((imgsz, imgsz, 3), 114, dtype=np.uint8)
    pad_x, pad_y = (imgsz - new_w) // 2, (imgsz - new_h) // 2
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    return canvas


def quantise(
    fp32_path: Path,
    calibration: CalibrationSet,
    out_path: Path,
    imgsz: int,
    settings: QuantSettings | None = None,
) -> Path:
    """Static int8 quantisation, calibrated on a **named, hashed** set of images.

    Static, not dynamic: dynamic quantisation is measurably worse on
    convolutional backbones because the activation ranges vary enormously
    between the backbone and the head.

    ``calibration`` is a :class:`CalibrationSet` rather than a directory, so the
    caller states which frames it chose and the choice travels into the sidecar
    and the probe record. A directory plus a limit is what produced v1's
    silently unrepresentative sample.
    """
    import numpy as np
    from onnxruntime.quantization import CalibrationDataReader, QuantFormat, quantize_static
    from PIL import Image

    settings = settings or QuantSettings()
    images = list(calibration.images)
    if not images:
        raise FileNotFoundError("the calibration set is empty")
    logger.info(
        "calibrating on %d images (%s, %s, %d positive / %d background, sha %s)",
        len(images), calibration.strategy, calibration.split,
        calibration.positives, calibration.background, calibration.sha256[:12],
    )

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
                frame = _fit(handle, imgsz, settings.calibration_fit)
            array = np.asarray(frame, dtype=np.float32).transpose(2, 0, 1) / 255.0
            return {"images": array[None, ...]}

    out_path.parent.mkdir(parents=True, exist_ok=True)

    source = fp32_path
    if settings.preprocess:
        from onnxruntime.quantization.shape_inference import quant_pre_process

        source = out_path.parent / f"{fp32_path.stem}-preprocessed.onnx"
        quant_pre_process(str(fp32_path), str(source))
        logger.info("pre-processed the graph before quantising")

    exclude = head_node_names(source, settings.head_prefix) if settings.exclude_head else []
    if settings.exclude_prefixes:
        exclude = sorted(set(exclude) | set(nodes_matching(source, settings.exclude_prefixes)))
    if exclude:
        logger.info(
            "leaving %d nodes in fp32 (head=%s, prefixes=%s)",
            len(exclude),
            settings.head_prefix if settings.exclude_head else None,
            list(settings.exclude_prefixes) or None,
        )

    quantize_static(
        model_input=str(source),
        model_output=str(out_path),
        calibration_data_reader=_Reader(),
        quant_format=QuantFormat.QDQ,
        activation_type=_quant_type(settings.activation_type),
        weight_type=_quant_type(settings.weight_type),
        per_channel=settings.per_channel,
        reduce_range=settings.reduce_range,
        calibrate_method=_calibrate_method(settings.calibrate_method),
        nodes_to_exclude=exclude or None,
    )
    logger.info(
        "quantised %s: %.2f MB -> %.2f MB",
        settings.format, fp32_path.stat().st_size / 1e6, out_path.stat().st_size / 1e6,
    )
    return out_path


def quantisation_error(
    fp32_path: Path,
    int8_path: Path,
    calibration: CalibrationSet,
    imgsz: int,
    *,
    fit: str = "stretch",
    frames: int = 8,
    lowest: int = 15,
) -> dict[str, Any]:
    """Which *tensor* loses the signal, using onnxruntime's own QDQ debugger.

    Nine variants can say that something helps without ever saying what was
    wrong. onnxruntime ships the tool for that - it runs the float and the
    quantised graph over the same inputs, matches their activations, and scores
    each one.

    **The score is SQNR in decibels, and higher is better.** onnxruntime computes
    ``20 * log10(||x|| / ||x - y||)``: a tensor the quantisation preserved has a
    large ratio and therefore a large number, and the damaged ones are at the
    *bottom*. This is worth stating twice because the first version of this
    function sorted descending and reported the result as "the worst tensors",
    which named the eight best-preserved tensors in the graph as the suspects.
    The rows below are sorted **ascending**, and the key is ``lowest_sqnr_db``
    rather than anything that could be read as an error magnitude.

    Best effort by construction: it returns an ``error`` key rather than raising
    if the debug API is unavailable or the graphs will not match up. A probe that
    died in its diagnostics would lose the measurements it had already made.
    """
    try:
        import numpy as np
        from onnxruntime.quantization import CalibrationDataReader
        from onnxruntime.quantization.qdq_loss_debug import (
            collect_activations,
            compute_activation_error,
            create_activation_matching,
            modify_model_output_intermediate_tensors,
        )
        from PIL import Image
    except Exception as error:  # noqa: BLE001 - an absent debug API is a fact
        return {"error": f"qdq_loss_debug unavailable: {type(error).__name__}: {error}"}

    images = list(calibration.images)[:frames]

    # A real CalibrationDataReader subclass: collect_activations iterates the
    # reader, and the base class provides __iter__/__next__ on top of get_next.
    class _Reader(CalibrationDataReader):
        def __init__(self) -> None:
            self._iter = iter(images)

        def get_next(self) -> dict | None:
            path = next(self._iter, None)
            if path is None:
                return None
            with Image.open(path) as handle:
                frame = _fit(handle, imgsz, fit)
            array = np.asarray(frame, dtype=np.float32).transpose(2, 0, 1) / 255.0
            return {"images": array[None, ...]}

    try:
        augmented = int8_path.parent / f"{fp32_path.stem}-augmented.onnx"
        modify_model_output_intermediate_tensors(str(fp32_path), str(augmented))
        float_activations = collect_activations(str(augmented), _Reader())

        augmented_int8 = int8_path.parent / f"{int8_path.stem}-augmented.onnx"
        modify_model_output_intermediate_tensors(str(int8_path), str(augmented_int8))
        int8_activations = collect_activations(str(augmented_int8), _Reader())

        matched = create_activation_matching(int8_activations, float_activations)
        errors = compute_activation_error(matched)
    except Exception as error:  # noqa: BLE001 - a diagnostic must not sink the probe
        return {"error": f"{type(error).__name__}: {error}"}

    ranked = sorted(
        (
            {
                "tensor": name,
                # onnxruntime's own names, kept verbatim so a reader can go back
                # to the source. Both are SQNR in dB: HIGHER IS BETTER.
                "qdq_sqnr_db": float(value["qdq_err"]),
                "xmodel_sqnr_db": float(value.get("xmodel_err", float("nan"))),
            }
            for name, value in errors.items()
        ),
        key=lambda row: row["qdq_sqnr_db"],
    )
    return {
        "frames": len(images),
        "tensors_compared": len(ranked),
        "units": "SQNR in dB, higher is better; these are the LOWEST",
        "lowest_sqnr_db": ranked[:lowest],
    }


def convert_fp16(fp32_path: Path, out_path: Path) -> Path:
    """Half precision, **for information only**.

    onnxruntime's CPU runtime does not broadly support fp16 operations - it is a
    GPU optimisation, and on CPU the ops are wrapped in casts or fall back
    entirely. This service runs on CPU, so an fp16 graph is not a shipping
    option here however it scores; it bounds what the weights are capable of,
    which is worth knowing when the int8 rows are bad.

    ``keep_io_types`` leaves the graph's inputs and outputs fp32, so the same
    harness can score it without knowing it is different.
    """
    import onnx
    from onnxconverter_common import float16

    out_path.parent.mkdir(parents=True, exist_ok=True)
    converted = float16.convert_float_to_float16(onnx.load(str(fp32_path)), keep_io_types=True)
    onnx.save(converted, str(out_path))
    logger.info(
        "fp16: %.2f MB -> %.2f MB (INFORMATIONAL - the CPU EP does not broadly support fp16)",
        fp32_path.stat().st_size / 1e6, out_path.stat().st_size / 1e6,
    )
    return out_path


def score_onnx(
    onnx_path: Path,
    *,
    role: str,
    data: Path | str,
    imgsz: int,
    split: str = "test",
) -> tuple[float | None, str | None]:
    """Score any ONNX graph and return ``(value, error)`` - never both.

    Split out from :func:`evaluate_int8` because docs/12 P9 runs a dozen graphs
    and needs to know *why* one of them produced no number. A failed load is a
    valid diagnostic result; a row that reports a number it did not measure is
    not. Exactly one of the two is ever non-``None``.

    Scored through ultralytics deliberately: the fp32 reference came from
    ``model.val()``, and two metrics computed by two implementations are not
    comparable to two decimal places, which is the resolution the 0.02 gate
    needs.
    """
    from ultralytics import YOLO

    task = "classify" if role == "identifier" else "detect"
    try:
        metrics = YOLO(str(onnx_path), task=task).val(
            data=str(data), imgsz=imgsz, split=split, verbose=False
        )
    except Exception as error:  # noqa: BLE001 - any failure here means "unmeasured"
        return None, f"{type(error).__name__}: {error}"

    value = float(metrics.top1) if task == "classify" else float(metrics.box.map50)
    return value, None


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

    Returns ``None`` if the quantised graph could not be scored, which leaves
    the gate **unmeasured** rather than passed. That is the honest verdict and
    :class:`GateResult` already distinguishes it from a failure.
    """
    value, error = score_onnx(onnx_path, role=role, data=data, imgsz=imgsz, split=split)
    if error is not None:
        logger.error(
            "could not score the int8 graph (%s). The int8 accuracy gate stays "
            "UNMEASURED, so this artefact cannot ship until it is scored.", error,
        )
        return None
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
    parser.add_argument("--tree", type=Path, required=True, help="the split tree to calibrate from")
    parser.add_argument("--calibration-split", default="train")
    parser.add_argument(
        "--calibration-strategy",
        choices=["first_lexicographic", "stratified", "positive_enriched"],
        default="stratified",
    )
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
    calibration = calibration_frames(
        args.tree,
        args.calibration_split,
        int(config["export"]["calibration_images"]),
        strategy=args.calibration_strategy,
        seed=int(config["project"]["seed"]),
    )
    int8 = quantise(
        fp32,
        calibration,
        args.out / f"{args.role}-v{args.version}.onnx",
        imgsz=imgsz,
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
