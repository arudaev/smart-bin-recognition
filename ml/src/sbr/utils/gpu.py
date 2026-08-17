"""Is this GPU actually usable by this build of torch?

``torch.cuda.is_available()`` answers a narrower question than it looks like it
answers. It reports whether a CUDA device and driver are present. It does **not**
report whether the installed torch carries compiled kernels for that device's
compute capability, and when it does not, the failure arrives later - at the
first tensor move, thirty lines into somebody else's library:

    torch.AcceleratorError: CUDA error: no kernel image is available for
    execution on the device

**This cost the project its first training run.** On 2026-08-16 a validator
kernel pulled the pinned pool, built the dataset, wrote ``args.yaml`` and then
died with no weights and no log. Reproduced on 2026-08-17 with a one-epoch smoke
kernel, which said what the original could not:

    torch 2.10.0+cu128, cuda available: True
    Tesla P100-PCIE-16GB with CUDA capability sm_60 is not compatible with the
    current PyTorch installation.
    The current PyTorch install supports CUDA capabilities sm_70 sm_75 sm_80
    sm_86 sm_90 sm_100 sm_120.

Kaggle hands out **P100 (sm_60)** as well as T4 (sm_75), and torch 2.10 dropped
sm_60.

**The first explanation for that was wrong, and the correction is the reason
this module exists rather than a one-line pip change.** It looked like the
kernels were pulling the bad torch in themselves - ``pip install ultralytics``
does resolve a torch wheel - so the installs were changed to ``--no-deps``. The
next run reported *the same torch*. A rung that installs **nothing at all**
(``ml/kaggle/smoke_gpu``) then settled it:

    "installed_anything": false,
    "torch_packages_as_shipped": ["torch==2.10.0+cu128", ...]
    "accelerator": {"capability": "sm_60", "usable": false}

**The image ships a torch that cannot use the GPU the platform allocates.**
Nothing in this repository caused it and nothing in this repository fixes it.
What is fixable is the *symptom*: a run that discovers this at the first tensor
move, deep inside somebody else's library, produces no weights and - as on
2026-08-16 - no log either.

So this module turns it into a sentence, in seconds, before any data is pulled:
a training kernel refuses (:func:`require_usable_gpu`) and a diagnostic one
reports and continues on the CPU (:func:`inspect_accelerator`). The remedy
itself is a **T4 rather than a P100**, which is Kaggle's allocation to make and
has no field in the kernel metadata schema - so it is retry-until, and the check
below is what makes "retry" a decision rather than an hour.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Accelerator:
    """What torch can actually run on, as distinct from what is plugged in."""

    available: bool
    name: str | None = None
    capability: str | None = None
    supported: tuple[str, ...] = ()
    torch_version: str | None = None

    @property
    def usable(self) -> bool:
        """Present **and** compiled for. ``is_available()`` only answers the first.

        An empty architecture list means torch could not report one, which is
        treated as usable: refusing on missing evidence would send a perfectly
        good run to the CPU.
        """
        if not self.available:
            return False
        if not self.supported or self.capability is None:
            return True
        return self.capability in self.supported

    @property
    def device(self) -> int | str:
        """What to hand Ultralytics: ``0`` for a usable GPU, else ``"cpu"``."""
        return 0 if self.usable else "cpu"

    def describe(self) -> str:
        if not self.available:
            return f"no CUDA device (torch {self.torch_version})"
        detail = f"{self.name}, capability {self.capability}, torch {self.torch_version}"
        if self.usable:
            return f"{detail} - usable"
        return (
            f"{detail} - NOT USABLE: this torch was built for "
            f"{' '.join(self.supported) or 'nothing this reports'}, which does not "
            f"include {self.capability}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "usable": self.usable,
            "name": self.name,
            "capability": self.capability,
            "supported": list(self.supported),
            "torch_version": self.torch_version,
        }


def inspect_accelerator() -> Accelerator:
    """Describe the accelerator without raising, whatever state torch is in."""
    try:
        import torch
    except Exception as error:  # noqa: BLE001 - no torch is a describable state
        logger.warning("torch is not importable: %s", error)
        return Accelerator(available=False)

    version = getattr(torch, "__version__", None)
    try:
        if not torch.cuda.is_available():
            return Accelerator(available=False, torch_version=version)

        major, minor = torch.cuda.get_device_capability(0)
        # get_arch_list() returns entries like 'sm_75'; older torch may not have it.
        supported = tuple(
            entry for entry in (torch.cuda.get_arch_list() or ()) if entry.startswith("sm_")
        )
        return Accelerator(
            available=True,
            name=torch.cuda.get_device_name(0),
            capability=f"sm_{major}{minor}",
            supported=supported,
            torch_version=version,
        )
    except Exception as error:  # noqa: BLE001 - a broken CUDA stack is not a GPU
        logger.warning("CUDA present but not interrogable (%s); treating as absent", error)
        return Accelerator(available=False, torch_version=version)


def require_usable_gpu(what_for: str = "train") -> Accelerator:
    """Stop now, with the reason, rather than at the first tensor move.

    A training kernel that silently fell back to CPU would burn its wall clock
    and produce a model hours late; one that crashed inside Ultralytics produces
    the 2026-08-16 failure again. Neither is acceptable, so this raises here,
    where the message can say what is wrong and what to do about it.
    """
    accelerator = inspect_accelerator()
    logger.info("accelerator: %s", accelerator.describe())

    if accelerator.usable:
        return accelerator

    raise SystemExit(
        f"refusing to {what_for}: {accelerator.describe()}.\n"
        "Measured on Kaggle 2026-08-18: the image ships torch 2.10.0+cu128, which "
        "dropped sm_60, and the platform allocates P100 (sm_60) as well as T4 "
        "(sm_75). Nothing in this repository caused that and nothing in it fixes "
        "it - the remedy is a run that lands on a T4, and the kernel metadata "
        "schema has no field to ask for one.\n"
        "Re-dispatch. This is the failure that produced a run with no weights and "
        "no log on 2026-08-16; refusing here costs seconds instead of an hour."
    )
