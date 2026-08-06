"""Tests for the ship gates.

The gates are the reason this project can be free, so two things are tested
here and they pull in opposite directions:

1. The gate *values* live in config, not in source, because the convention is
   that nothing affecting a run is hard-coded. That makes them editable.
2. Precisely because they are editable, the configured values are **pinned
   here**. Loosening a gate is a product decision; it should require changing a
   test that says so, not a one-line YAML edit that rides along with a tuning
   change.
"""

from __future__ import annotations

import pytest

from sbr.config import load_config
from sbr.export.onnx_export import ExportReport, Gates, check_gates

# --------------------------------------------------------------------------- #
# The pinned budgets
# --------------------------------------------------------------------------- #

#: docs/04-ml-pipeline.md § 6 and AGENTS.md's guardrail. Concurrency is the cost
#: ceiling (docs/05-cost-model.md § 3), so latency is the budget that binds.
PINNED_LATENCY_MS = {"validator": 50.0, "identifier": 25.0}

#: int8 may cost at most two points, in whichever metric the role is judged on.
PINNED_ACCURACY_DROP = 0.02


@pytest.mark.parametrize("role", ["validator", "identifier"])
def test_configured_latency_budget_is_the_pinned_one(role):
    assert Gates.for_role(role).max_median_latency_ms == PINNED_LATENCY_MS[role]


@pytest.mark.parametrize("role", ["validator", "identifier"])
def test_configured_accuracy_budget_is_the_pinned_one(role):
    assert Gates.for_role(role).max_accuracy_drop == PINNED_ACCURACY_DROP


@pytest.mark.parametrize("role", ["validator", "identifier"])
def test_each_role_states_its_own_latency_budget(role):
    # default.yaml deliberately has no latency default: a role that forgets to
    # state one must be an error, not a silent inherited number.
    assert "max_median_latency_ms" in load_config(role)["export"]["gates"]


def test_default_config_alone_has_no_latency_budget():
    assert "max_median_latency_ms" not in load_config("default")["export"]["gates"]


def test_missing_gate_config_is_an_error():
    with pytest.raises(ValueError, match="max_median_latency_ms"):
        Gates.from_config("validator", {"export": {"gates": {"max_accuracy_drop": 0.02}}})


def test_unknown_role_is_an_error():
    with pytest.raises(ValueError, match="unknown model role"):
        Gates.from_config("detector", {"export": {"gates": {}}})


# --------------------------------------------------------------------------- #
# check_gates
# --------------------------------------------------------------------------- #


def _report(role: str = "validator", **overrides) -> ExportReport:
    """A report that passes everything, so each test can break exactly one thing."""
    base = dict(
        role=role,
        version=1,
        onnx_path="validator-v1.onnx",
        size_bytes=5_000_000,
        imgsz=448,
        classes=["bin"],
        quantised=True,
        median_latency_ms=40.0,
        latency_hardware="HF Space CPU-basic, 2 vCPU",
    )
    if role == "identifier":
        base |= {
            "imgsz": 320,
            "classes": ["wheelie_small"],
            "top1_fp32": 0.90,
            "top1_int8": 0.89,
            "median_latency_ms": 20.0,   # its budget is 25 ms, not the validator's 50
        }
    else:
        base |= {"map50_fp32": 0.90, "map50_int8": 0.89}
    return ExportReport(**(base | overrides))


@pytest.mark.parametrize("role", ["validator", "identifier"])
def test_a_healthy_artefact_ships(role):
    assert check_gates(_report(role), Gates.for_role(role)).may_ship


def test_latency_over_budget_fails():
    result = check_gates(_report(median_latency_ms=51.0), Gates.for_role("validator"))
    assert not result.may_ship
    assert any("exceeds" in f for f in result.failures)


def test_unmeasured_latency_is_not_a_pass():
    # The hole worth closing: an artefact whose latency nobody measured must not
    # sail through the gate that exists to measure it.
    result = check_gates(_report(median_latency_ms=None), Gates.for_role("validator"))
    assert not result.may_ship
    assert not result.failures
    assert any("has not been measured" in u for u in result.unmeasured)


def test_latency_without_named_hardware_fails():
    # "174 ms" means nothing without "on what". docs/08 § 7.4 is only useful
    # because it names the CPU.
    result = check_gates(_report(latency_hardware=None), Gates.for_role("validator"))
    assert any("naming the hardware" in f for f in result.failures)


def test_unquantised_artefact_fails():
    result = check_gates(_report(quantised=False), Gates.for_role("validator"))
    assert any("not quantised" in f for f in result.failures)


def test_role_and_gates_must_agree():
    # Judging the identifier against the validator's 50 ms budget would pass a
    # model that is twice its budget.
    result = check_gates(_report("identifier"), Gates.for_role("validator"))
    assert any("gates are for role" in f for f in result.failures)


def test_int8_drop_over_budget_fails():
    result = check_gates(
        _report(map50_fp32=0.90, map50_int8=0.87), Gates.for_role("validator")
    )
    assert any("int8 quantisation cost" in f for f in result.failures)


def test_unmeasured_int8_drop_is_not_a_pass():
    result = check_gates(_report(map50_int8=None), Gates.for_role("validator"))
    assert not result.may_ship
    assert any("unmeasured" in u for u in result.unmeasured)


# --------------------------------------------------------------------------- #
# The two roles are judged on different metrics
# --------------------------------------------------------------------------- #


def test_validator_is_judged_on_map_and_identifier_on_top1():
    assert _report("validator").accuracy_metric == "map50"
    assert _report("identifier").accuracy_metric == "top1"


def test_identifier_ignores_map_and_reads_top1():
    # A classifier has no mAP. If check_gates read map50 for the identifier it
    # would report the drop as unmeasured and never judge quantisation at all.
    report = _report("identifier", map50_fp32=0.10, map50_int8=0.99)
    assert report.accuracy_drop == pytest.approx(0.01)
    assert check_gates(report, Gates.for_role("identifier")).may_ship
