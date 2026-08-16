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
from pathlib import Path
from typing import Any

from settings import Settings

logger = logging.getLogger("sbr.service")

ROLES = ("validator", "identifier")


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


def open_session(onnx_path: Path, threads: int) -> Any:
    """An onnxruntime session pinned to the service's core count.

    The same pinning as ``sbr.bench.open_session``, and for the same reason: a
    latency number is only comparable to the budget if it was taken on the same
    number of threads the budget was stated for.
    """
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])


def _from_directory(directory: Path, role: str, version: int) -> tuple[Path, dict[str, Any]]:
    sidecar_path = directory / f"{role}-v{version}.json"
    if not sidecar_path.exists():
        raise ArtefactMissingError(f"no sidecar at {sidecar_path}")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    onnx_path = Path(str(sidecar["onnx_path"]))
    if not onnx_path.exists():
        # Sidecars record the path they were written at, which is a Kaggle
        # working directory. Beside the sidecar is where it actually is.
        onnx_path = directory / onnx_path.name
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


def load_artefact(role: str, settings: Settings) -> Artefact:
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

    artefact = Artefact(
        role=role,
        session=open_session(onnx_path, settings.intra_op_threads),
        sidecar=sidecar,
        source=source,
    )
    logger.info(
        "loaded %s v%s from %s: imgsz %d, %d classes, dynamic_batch=%s",
        role, sidecar.get("version"), source, artefact.imgsz,
        len(artefact.classes), artefact.dynamic_batch,
    )
    return artefact
