"""Whether `hardware()` tells the truth about the box it is running on.

A number in this project is only worth what its hardware label is worth, and
`check_gates` reads `representative` to decide whether a latency figure may
close a gate at all. A host misdetection is therefore not cosmetic: it can let a
proxy measurement decide a ship gate.

These cover the one that actually happened - `Path("/kaggle")` is
absolute-from-the-drive-root on Windows, so a local kaggle directory at the
drive root made
every local run claim Kaggle silicon.
"""

from __future__ import annotations

import sbr.bench as bench


def test_kaggle_env_var_is_authoritative(monkeypatch):
    monkeypatch.setenv("KAGGLE_KERNEL_RUN_TYPE", "Interactive")
    assert bench._on_kaggle() is True


def test_kaggle_path_is_not_trusted_off_linux(monkeypatch):
    """The bug: a Windows box with a kaggle directory at the drive root is not Kaggle."""
    monkeypatch.delenv("KAGGLE_KERNEL_RUN_TYPE", raising=False)
    monkeypatch.setattr(bench.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bench.Path, "exists", lambda self: True)
    assert bench._on_kaggle() is False


def test_kaggle_path_is_trusted_on_linux(monkeypatch):
    monkeypatch.delenv("KAGGLE_KERNEL_RUN_TYPE", raising=False)
    monkeypatch.setattr(bench.platform, "system", lambda: "Linux")
    monkeypatch.setattr(bench.Path, "exists", lambda self: True)
    assert bench._on_kaggle() is True


def test_a_plain_local_box_is_not_representative(monkeypatch):
    """No SPACE_ID, no Kaggle, no SBR_SERVICE_HOST - it is somebody's laptop.

    `representative: False` is what stops `check_gates` from closing a latency
    gate on it, so this is the assertion that keeps the gate honest.
    """
    for var in ("SPACE_ID", "KAGGLE_KERNEL_RUN_TYPE", "SBR_SERVICE_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(bench, "_on_kaggle", lambda: False)

    hw = bench.hardware()
    assert hw.representative is False
    assert "Kaggle" not in hw.where
    assert "[PROXY, not the service]" in hw.label


def test_declaring_the_service_host_makes_it_representative(monkeypatch):
    for var in ("SPACE_ID", "KAGGLE_KERNEL_RUN_TYPE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(bench, "_on_kaggle", lambda: False)
    monkeypatch.setenv("SBR_SERVICE_HOST", "GCE n2-standard-4, Cascade Lake")

    hw = bench.hardware()
    assert hw.representative is True
    assert hw.where == "GCE n2-standard-4, Cascade Lake"
    assert "PROXY" not in hw.label
