"""Everything the service is allowed to know, and where it learns it.

Two rules, both inherited from ``ml/``:

- **Nothing that affects a run is hard-coded.** In ``ml/`` that means YAML; here
  it means the environment, because a container's configuration is its
  environment and a Cloud Run revision is how it changes.
- **Nothing about the model is here at all.** Class names, input size, layout,
  normalisation and NMS thresholds live in the artefact's sidecar
  (``sbr.export.onnx_export.write_sidecar``). This module says *which* artefact
  to load, never *what it is*.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

#: The service has two vCPUs and the whole cost model is arithmetic about them.
#: Pinning onnxruntime is what makes a measured millisecond mean "one frame on
#: the tier we pay for" rather than "one frame on whatever the scheduler gave us".
DEFAULT_INTRA_OP_THREADS = 2

#: Crops per frame. docs/05 § 7 names capping this as one of the cheap ways to
#: move the concurrency ceiling. Six is what the PRD calls a normal input, so six
#: is the default.
#:
#: **The remainder is NOT deferred to the next frame.** This constant's docstring
#: and docs/05 § 7 both said it was; neither the pipeline nor the client ever
#: implemented it. `pipeline.run` truncates and never revisits, so a box past the
#: cap is drawn with `form_factor: null` and no colour - lowering this trades
#: coverage for cost, and the trade has to be stated wherever the number is.
#: Deferral is buildable and the client's result lock is the natural place for
#: it; docs/12 P8c records what it would take.
DEFAULT_MAX_CROPS = 6

#: How many frames may be inside onnxruntime at the same time.
#:
#: ONE, because the graphs are already pinned to both vCPUs. Two frames running
#: concurrently do not go twice as fast - they contend for the same two cores and
#: each takes roughly twice as long, which is the same total work delivered later
#: and with a worse p95. Measured: admitting frames without this bound dropped
#: throughput from ~16 to ~6.5 frames/second on a 2-vCPU container.
#:
#: This is deliberately NOT the same number as the queue depth the shedder
#: watches. Depth is how many people are waiting, which is what decides the
#: advice; slots are how many the CPU works on, which is what decides throughput.
#: Conflating them is what made the ladder unreachable in the first place.
DEFAULT_INFERENCE_SLOTS = 1


#: onnxruntime's own defaults for the two threading knobs docs/12 probe P8b
#: tests. They are *its* defaults rather than ours on purpose: the probe's
#: baseline has to be the runtime as it ships, or the recovery it measures is
#: against a configuration nobody was running.
#:
#: Both matter here for the same reason. This service holds TWO sessions on TWO
#: cores, and by default each session gets its own intra-op pool and each pool
#: spins while idle - so four threads contend for two cores and the idle model's
#: threads burn the running model's cycles. That is the standing hypothesis for
#: the 15-40 ms per frame that P4 could attribute to neither graph.
DEFAULT_ORT_SPINNING = True
DEFAULT_ORT_SHARED_POOL = False


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _optional_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else None


@dataclass(frozen=True)
class ShedThresholds:
    """Queue depths at which each rung of the degradation ladder engages.

    docs/05 § 3 specifies the ladder; these are where it fires. They are defaults
    rather than constants because the right depth depends on what a frame costs,
    which is what docs/12 probe P4 measures - and a number nobody has measured
    yet does not belong in source pretending to be settled.
    """

    slow: int = 4      # rung 1: tell clients 2 fps
    tap: int = 8       # rung 2: streaming off, tap to scan
    queue: int = 16    # rung 3: a stated wait

    @classmethod
    def from_env(cls) -> ShedThresholds:
        return cls(
            slow=_int("SBR_SHED_SLOW", cls.slow),
            tap=_int("SBR_SHED_TAP", cls.tap),
            queue=_int("SBR_SHED_QUEUE", cls.queue),
        )


@dataclass(frozen=True)
class Settings:
    model_repo: str = "arudaev/smart-bin-detect"
    revision: str = "main"
    validator_version: int = 1
    identifier_version: int = 1

    #: Load artefacts from this directory instead of the Hub. What the tests and
    #: the load test use, and what a deployment with a baked-in model would use.
    artefact_dir: Path | None = None

    intra_op_threads: int = DEFAULT_INTRA_OP_THREADS
    max_crops: int = DEFAULT_MAX_CROPS

    #: Whether onnxruntime's intra-op threads spin while idle. See
    #: DEFAULT_ORT_SPINNING - this is a docs/12 P8b variable, not a tuning knob
    #: somebody should set by feel.
    ort_spinning: bool = DEFAULT_ORT_SPINNING

    #: Whether both sessions share ONE global thread pool instead of getting one
    #: each. Mutually exclusive with `identifier_threads`, because a shared pool
    #: has a single size and a per-session count would then be ignored - two
    #: variables moving while one is being measured.
    ort_shared_pool: bool = DEFAULT_ORT_SHARED_POOL

    #: Intra-op threads for the identifier alone. ``None`` means the same as the
    #: validator, which is what the service has always done.
    identifier_threads: int | None = None

    #: How many frames may be *inside* onnxruntime at once. Distinct from queue
    #: depth, which is how many are waiting - see DEFAULT_INFERENCE_SLOTS.
    inference_slots: int = DEFAULT_INFERENCE_SLOTS

    #: Serve an artefact whose ship gates did not pass. Deliberate friction, in
    #: the same spirit as ``gate.py --allow-unrepresentative-hardware``: it exists
    #: so latency and concurrency can be measured before a model is trained, it is
    #: never the default, and ``/health`` announces it in every reply.
    allow_ungated: bool = False

    #: Run the identifier on exactly this many crops regardless of what the
    #: validator found. TEST ONLY - it makes the cost curve controllable under an
    #: untrained validator, whose box count is arbitrary. Refused unless
    #: ``allow_ungated`` is also set, because on a real artefact it would fabricate
    #: detections.
    force_crops: int | None = None

    shed: ShedThresholds = field(default_factory=ShedThresholds)

    @classmethod
    def from_env(cls) -> Settings:
        directory = os.environ.get("SBR_ARTEFACT_DIR", "").strip()
        allow_ungated = _flag("SBR_ALLOW_UNGATED")
        forced = _int("SBR_FORCE_CROPS", -1)

        if forced >= 0 and not allow_ungated:
            raise ValueError(
                "SBR_FORCE_CROPS fabricates detections and is a measuring tool, not a "
                "serving mode. It requires SBR_ALLOW_UNGATED=1 so that a service running "
                "it can never be mistaken for one answering real questions."
            )

        shared_pool = _flag("SBR_ORT_SHARED_POOL", DEFAULT_ORT_SHARED_POOL)
        identifier_threads = _optional_int("SBR_IDENTIFIER_THREADS")
        if shared_pool and identifier_threads is not None:
            raise ValueError(
                "SBR_ORT_SHARED_POOL and SBR_IDENTIFIER_THREADS cannot both be set. A "
                "shared pool has one size for both sessions, so the per-session count "
                "would be silently ignored - and a probe that moves two variables while "
                "measuring one is not a probe (docs/12 P8b)."
            )

        return cls(
            model_repo=os.environ.get("SBR_MODEL_REPO", cls.model_repo),
            revision=os.environ.get("SBR_MODEL_REVISION", cls.revision),
            validator_version=_int("SBR_VALIDATOR_VERSION", cls.validator_version),
            identifier_version=_int("SBR_IDENTIFIER_VERSION", cls.identifier_version),
            artefact_dir=Path(directory) if directory else None,
            intra_op_threads=_int("SBR_INTRA_OP_THREADS", DEFAULT_INTRA_OP_THREADS),
            max_crops=_int("SBR_MAX_CROPS", DEFAULT_MAX_CROPS),
            ort_spinning=_flag("SBR_ORT_SPINNING", DEFAULT_ORT_SPINNING),
            ort_shared_pool=shared_pool,
            identifier_threads=identifier_threads,
            inference_slots=max(1, _int("SBR_INFERENCE_SLOTS", DEFAULT_INFERENCE_SLOTS)),
            allow_ungated=allow_ungated,
            force_crops=forced if forced >= 0 else None,
            shed=ShedThresholds.from_env(),
        )

    def as_dict(self) -> dict:
        """What ``/health`` reports. Deliberately complete: an operator reading
        this must be able to tell whether the answers are trustworthy."""
        return {
            "model_repo": self.model_repo,
            "revision": self.revision,
            "artefact_dir": str(self.artefact_dir) if self.artefact_dir else None,
            "intra_op_threads": self.intra_op_threads,
            "identifier_threads": self.identifier_threads,
            "ort_spinning": self.ort_spinning,
            "ort_shared_pool": self.ort_shared_pool,
            "inference_slots": self.inference_slots,
            "max_crops": self.max_crops,
            "allow_ungated": self.allow_ungated,
            "force_crops": self.force_crops,
            "shed_thresholds": {
                "slow": self.shed.slow,
                "tap": self.shed.tap,
                "queue": self.shed.queue,
            },
        }
