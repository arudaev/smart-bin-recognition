"""Loading a model, and refusing to load one that has not earned its way here.

This module is the last thing standing between an unproven artefact and a user,
and it is the reason the whole gate apparatus in ``ml/`` is worth having. A
sidecar records a verdict (``sbr.export.onnx_export.check_gates``); if that
verdict is not *may ship*, the service does not serve it. Not a warning, not a
degraded mode - a refusal at load time, before the port is open.

**Everything about the model comes from the sidecar.** Class names and their
order - which *is* the ONNX class index - input size, input name, layout,
normalisation, NMS thresholds, and whether the graph accepts a batch. Swapping a
model is publishing a new revision; it is never a code change here. There is a
test asserting that no form-factor name appears anywhere in this package, in the
same spirit as the web client's ``discipline.test.ts``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from settings import Settings

logger = logging.getLogger("sbr.service")

ROLES = ("validator", "identifier")

#: Whether this process has already created onnxruntime's global thread pools,
#: and at what size. They are **process-wide and immutable**: a second call
#: raises ``FAIL: Global thread pools have already been created, cannot replace
#: them``, which - since the service opens the validator and then the identifier
#: - means an unguarded implementation crashes at startup on the second session
#: and never on the first. Found by running it, not by reading it.
_GLOBAL_POOL: tuple[int, int] | None = None


class UngatedArtefactError(RuntimeError):
    """Raised when an artefact's sidecar does not say it may ship."""


class ArtefactMissingError(RuntimeError):
    """Raised when an artefact could not be found at all.

    Distinct from :class:`UngatedArtefactError` on purpose: "there is no
    identifier yet" is an expected state of this project today and the service
    runs perfectly well in it, answering *where* a bin is and declining to say
    *which*. "There is an identifier and it failed its gates" is not expected and
    must never be silently equivalent.
    """


@dataclass(frozen=True)
class Artefact:
    """An open session, the sidecar describing it, and how it got here."""

    role: str
    session: Any
    sidecar: dict[str, Any]
    source: str

    # -- everything below is read, never assumed ---------------------------- #

    @property
    def imgsz(self) -> int:
        return int(self.sidecar["imgsz"])

    @property
    def input_name(self) -> str:
        return str(self.sidecar.get("input_name", "images"))

    @property
    def classes(self) -> list[str]:
        """Class names in ONNX index order. Reordering these silently
        invalidates every deployed model, which is why they travel with it."""
        return list(self.sidecar.get("classes", []))

    @property
    def dynamic_batch(self) -> bool:
        # Absent in sidecars written before 2026-08-16, and every one of those
        # was exported with dynamic=False. Absence means no.
        return bool(self.sidecar.get("dynamic_batch", False))

    @property
    def normalisation(self) -> dict[str, Any]:
        return dict(self.sidecar.get("normalisation") or {"scale": 1 / 255.0})

    @property
    def nms(self) -> dict[str, Any]:
        return dict(self.sidecar.get("nms") or {})

    @property
    def may_ship(self) -> bool:
        return bool((self.sidecar.get("gate_result") or {}).get("may_ship"))

    def health(self) -> dict[str, Any]:
        """What ``/health`` says about this artefact.

        The gate verdict and the target result both ride along. An operator
        looking at a bad answer needs to be able to see, without leaving the
        endpoint, whether the model was allowed to be here and how good it
        claimed to be.
        """
        return {
            "role": self.role,
            "version": self.sidecar.get("version"),
            "onnx": Path(str(self.sidecar.get("onnx_path", ""))).name,
            "imgsz": self.imgsz,
            "classes": len(self.classes),
            "quantised": self.sidecar.get("quantised"),
            "dynamic_batch": self.dynamic_batch,
            "source": self.source,
            "gate_result": self.sidecar.get("gate_result"),
            "target_result": self.sidecar.get("target_result"),
            "latency_hardware": self.sidecar.get("latency_hardware"),
        }


def open_session(
    onnx_path: Path, threads: int, *, spinning: bool = True, shared_pool: bool = False
) -> Any:
    """An onnxruntime session pinned to the service's core count.

    The same pinning as ``sbr.bench.open_session``, and for the same reason: a
    latency number is only comparable to the budget if it was taken on the same
    number of threads the budget was stated for.

    ``spinning`` and ``shared_pool`` are the two variables docs/12 probe P8b
    tests, and both default to onnxruntime's own behaviour so that the probe's
    baseline is the runtime as it ships. What they change:

    - **spinning.** Intra-op threads spin while waiting for work. With one model
      that is free; with two sessions on two cores it means the idle model's
      threads burn the running model's cycles.
    - **shared_pool.** By default each session builds its own intra-op pool, so
      this service runs four threads on two cores. One global pool is what makes
      the two sessions share rather than compete - and it makes per-session
      thread counts meaningless, which is why ``Settings`` refuses to combine it
      with ``SBR_IDENTIFIER_THREADS``.

    A runtime too old for the global-pool API falls back to per-session pools and
    **says so**, rather than silently measuring the configuration it was asked to
    move away from.
    """
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    if not spinning:
        # The documented spelling; an unknown key is ignored rather than raising,
        # so this is logged at the call site where the setting is known.
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")

    if shared_pool and _use_global_pool(ort, threads):
        options.use_per_session_threads = False

    return ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])


def _use_global_pool(ort: Any, threads: int) -> bool:
    """Create the process-wide thread pools once. Returns whether to opt in.

    Once, because onnxruntime's global pools cannot be replaced: the second call
    raises. The service opens two sessions, so the naive version works for the
    validator and takes the process down on the identifier - a failure that is
    invisible to any test that opens one session, which is every test that used
    to exist here.
    """
    global _GLOBAL_POOL

    setter = getattr(ort, "set_global_thread_pool_sizes", None)
    if setter is None:
        logger.warning(
            "SBR_ORT_SHARED_POOL is set but onnxruntime %s exposes no global thread "
            "pool API - falling back to per-session pools. Any P8b number from this "
            "process describes the DEFAULT configuration, not the one asked for.",
            ort.__version__,
        )
        return False

    if _GLOBAL_POOL is None:
        setter(threads, 1)
        _GLOBAL_POOL = (threads, 1)
        logger.info("created the global onnxruntime thread pool: %d intra, 1 inter", threads)
    elif _GLOBAL_POOL != (threads, 1):
        # Both sessions share one pool, so the first sizing is the only sizing.
        # Saying so is the difference between a measurement and a guess about a
        # measurement - Settings refuses the combination that would cause this,
        # so reaching here means something else set it.
        logger.warning(
            "the global thread pool already exists at %s; this session asked for "
            "%d intra and gets the existing pool. A shared pool has ONE size.",
            _GLOBAL_POOL, threads,
        )
    return True


def _from_directory(directory: Path, role: str, version: int) -> tuple[Path, dict[str, Any]]:
    sidecar_path = directory / f"{role}-v{version}.json"
    if not sidecar_path.exists():
        raise ArtefactMissingError(f"no sidecar at {sidecar_path}")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    recorded = str(sidecar["onnx_path"])
    onnx_path = Path(recorded)
    if not onnx_path.exists():
        # Sidecars record the path they were written at, which is a Kaggle
        # working directory. Beside the sidecar is where it actually is.
        #
        # Backslashes are normalised first: a sidecar written on Windows records
        # `artifacts\p8\...\validator-probe.onnx`, which on Linux is a single
        # filename containing backslashes rather than a path - so `.name` returns
        # the whole string and the fallback looks for a file whose name is a
        # path. The container then exits at startup with ArtefactMissingError,
        # which reads exactly like a missing artefact and is not one.
        onnx_path = directory / PurePosixPath(recorded.replace("\\", "/")).name
    if not onnx_path.exists():
        raise ArtefactMissingError(f"sidecar at {sidecar_path} but no graph at {onnx_path}")
    return onnx_path, sidecar


def _from_hub(settings: Settings, role: str, version: int) -> tuple[Path, dict[str, Any]]:
    from huggingface_hub import hf_hub_download

    token = os.environ.get("HF_TOKEN")
    try:
        sidecar_local = hf_hub_download(
            settings.model_repo,
            f"v{version}/{role}-v{version}.json",
            revision=settings.revision,
            token=token,
        )
    except Exception as error:  # noqa: BLE001 - an untrained role is a normal state
        raise ArtefactMissingError(
            f"no {role} v{version} in {settings.model_repo}@{settings.revision} "
            f"({type(error).__name__})"
        ) from error

    sidecar = json.loads(Path(sidecar_local).read_text(encoding="utf-8"))
    onnx_local = hf_hub_download(
        settings.model_repo,
        f"v{version}/{Path(str(sidecar['onnx_path'])).name}",
        revision=settings.revision,
        token=token,
    )
    return Path(onnx_local), sidecar


def artefact_exists(role: str, settings: Settings) -> bool:
    """Is there a sidecar for this role? Answered WITHOUT opening a session.

    The service needs this before it opens anything, because whether two
    graphs will be loaded decides whether they should share a thread pool -
    and onnxruntime's global pools cannot be created after the first session
    that opts out of per-session threads. On the Hub path this warms the same
    cache ``load_artefact`` then reads, so it costs one request and no more.
    """
    version = settings.validator_version if role == "validator" else settings.identifier_version
    try:
        if settings.artefact_dir:
            _from_directory(settings.artefact_dir, role, version)
        else:
            _from_hub(settings, role, version)
    except ArtefactMissingError:
        return False
    except Exception as error:  # noqa: BLE001 - unreachable Hub is not 'absent'
        logger.warning("could not tell whether a %s exists (%s); assuming it does not", role, error)
        return False
    return True


def load_artefact(
    role: str, settings: Settings, *, shared_pool: bool | None = None
) -> Artefact:
    """Fetch, verify and open one artefact.

    Raises :class:`ArtefactMissingError` when there is nothing to load and
    :class:`UngatedArtefactError` when what was loaded has not passed its gates.
    """
    if role not in ROLES:
        raise ValueError(f"unknown model role {role!r}; expected one of {ROLES}")

    version = settings.validator_version if role == "validator" else settings.identifier_version

    if settings.artefact_dir:
        onnx_path, sidecar = _from_directory(settings.artefact_dir, role, version)
        source = f"{settings.artefact_dir}"
    else:
        onnx_path, sidecar = _from_hub(settings, role, version)
        source = f"{settings.model_repo}@{settings.revision}"

    verdict = sidecar.get("gate_result") or {}
    if not verdict.get("may_ship"):
        detail = "; ".join(verdict.get("failures") or []) or None
        pending = "; ".join(verdict.get("unmeasured") or []) or None
        message = (
            f"{role} v{version} from {source} has not passed its ship gates and will not "
            f"be served. failures: {detail or 'none'}. unmeasured: {pending or 'none'}."
        )
        if not settings.allow_ungated:
            raise UngatedArtefactError(
                message
                + " An ungated model reaching users is the failure the gates exist to"
                " prevent. Set SBR_ALLOW_UNGATED=1 only to measure latency or"
                " concurrency, never to answer a real question."
            )
        logger.warning("SERVING AN UNGATED ARTEFACT: %s", message)
        source += " [UNGATED]"

    # The identifier may be given fewer threads than the validator: it is the
    # smaller graph and it is the one that runs n times per frame, so it is where
    # a per-session count is worth testing at all (docs/12 P8b).
    threads = settings.intra_op_threads
    if role == "identifier" and settings.identifier_threads is not None:
        threads = settings.identifier_threads

    artefact = Artefact(
        role=role,
        session=open_session(
            onnx_path,
            threads,
            spinning=settings.ort_spinning,
            # Decided by the caller, which is the only place that knows how many
            # graphs there will be. See settings.DEFAULT_ORT_SHARED_POOL.
            shared_pool=bool(settings.ort_shared_pool if shared_pool is None else shared_pool),
        ),
        sidecar=sidecar,
        source=source,
    )
    logger.info(
        "loaded %s v%s from %s: imgsz %d, %d classes, dynamic_batch=%s, "
        "threads=%d, spinning=%s, shared_pool=%s",
        role, sidecar.get("version"), source, artefact.imgsz,
        len(artefact.classes), artefact.dynamic_batch,
        threads, settings.ort_spinning,
        bool(settings.ort_shared_pool if shared_pool is None else shared_pool),
    )
    return artefact
