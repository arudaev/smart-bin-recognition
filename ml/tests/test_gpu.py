"""Whether torch can actually use the GPU it says is available.

`torch.cuda.is_available()` answers "is there a device", not "was this torch
compiled for it", and the gap between those two questions cost this project its
first training run. `sbr.utils.gpu` is the check that closes it; these are the
cases it has to get right, written from the log of the run that failed.
"""

from __future__ import annotations

import pytest

from sbr.utils.gpu import Accelerator, require_usable_gpu

#: Verbatim from the 2026-08-17 smoke kernel, which reproduced the failure.
P100 = Accelerator(
    available=True,
    name="Tesla P100-PCIE-16GB",
    capability="sm_60",
    supported=("sm_70", "sm_75", "sm_80", "sm_86", "sm_90", "sm_100", "sm_120"),
    torch_version="2.10.0+cu128",
)

T4 = Accelerator(
    available=True,
    name="Tesla T4",
    capability="sm_75",
    supported=("sm_70", "sm_75", "sm_80", "sm_86"),
    torch_version="2.6.0+cu124",
)


def test_a_present_but_uncompiled_gpu_is_not_usable():
    """The exact 2026-08-16 shape: available, and unusable.

    Ultralytics would have taken this device, moved the model to it, and raised
    `no kernel image is available for execution on the device` - after pulling
    the pool, building the dataset and writing args.yaml.
    """
    assert P100.available is True
    assert P100.usable is False
    assert P100.device == "cpu"


def test_a_matching_gpu_is_usable():
    assert T4.usable is True
    assert T4.device == 0


def test_no_device_is_not_usable():
    absent = Accelerator(available=False, torch_version="2.6.0")
    assert absent.usable is False
    assert absent.device == "cpu"


def test_an_unreported_architecture_list_does_not_condemn_a_good_gpu():
    # Refusing on missing evidence would send a perfectly good run to the CPU.
    # Older torch does not always expose get_arch_list().
    quiet = Accelerator(available=True, name="A100", capability="sm_80", supported=())
    assert quiet.usable is True


def test_the_description_names_the_mismatch_not_just_the_failure():
    described = P100.describe()
    assert "sm_60" in described
    assert "sm_70" in described
    assert "NOT USABLE" in described


def test_requiring_a_gpu_fails_loudly_and_says_what_to_do(monkeypatch):
    """The message has to carry the remedy, and the remedy is not in this repo.

    Somebody reading this a year from now will not have the log. They need to be
    told that the image ships the incompatible torch, and that a T4 is something to
    ASK for rather than wait for - the mistake an earlier draft of this work made.
    """
    import sbr.utils.gpu as gpu

    monkeypatch.setattr(gpu, "inspect_accelerator", lambda: P100)
    with pytest.raises(SystemExit) as raised:
        require_usable_gpu("train the validator")

    message = str(raised.value)
    assert "train the validator" in message
    assert "T4" in message and "P100" in message
    assert "machine_shape" in message and "NvidiaTeslaT4" in message
    assert "2026-08-16" in message


def test_requiring_a_gpu_returns_it_when_it_is_fine(monkeypatch):
    import sbr.utils.gpu as gpu

    monkeypatch.setattr(gpu, "inspect_accelerator", lambda: T4)
    assert require_usable_gpu().device == 0


def test_the_report_is_json_serialisable():
    # It rides in the kernel's output file, which is how a run that failed is
    # distinguishable from one that never started.
    import json

    assert json.loads(json.dumps(P100.as_dict()))["usable"] is False
