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
from sbr.export.onnx_export import (
    ExportReport,
    Gates,
    Targets,
    batched_role,
    check_gates,
    check_targets,
)

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


# --------------------------------------------------------------------------- #
# Targets - reported, never gating
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("validator", {"min_recall_heldout_city", "min_precision_on_negatives"}),
        ("identifier", {"min_formfactor_acc_heldout_city"}),
    ],
)
def test_each_role_states_the_targets_docs_04_7_promises(role, expected):
    assert set(Targets.for_role(role).values) == expected


def test_a_missed_target_does_not_block_shipping():
    # The distinction that makes targets useful: a gate is arithmetic the free
    # tier depends on, a target is how good the model is. Missing one is a
    # result to act on, not a reason to refuse the only model that exists.
    targets = Targets.for_role("validator")
    result = check_targets({"min_recall_heldout_city": 0.10}, targets)
    assert result.missed["min_recall_heldout_city"] == (0.10, 0.97)
    assert check_gates(_report("validator"), Gates.for_role("validator")).may_ship


def test_an_unmeasured_target_is_unmeasurable_not_met():
    # Silently skipping the held-out-city target is how the generalisation
    # question gets quietly dropped. It has to show up as missing evidence.
    result = check_targets({"min_recall_heldout_city": None}, Targets.for_role("validator"))
    assert "min_recall_heldout_city" in result.unmeasurable
    assert not result.met


def test_a_target_absent_from_the_measurements_is_also_unmeasurable():
    result = check_targets({}, Targets.for_role("identifier"))
    assert result.unmeasurable == ["min_formfactor_acc_heldout_city"]


def test_a_met_target_is_reported_with_its_value():
    result = check_targets({"min_precision_on_negatives": 0.99}, Targets.for_role("validator"))
    assert result.met["min_precision_on_negatives"] == 0.99


# --------------------------------------------------------------------------- #
# The batch axis - a service requirement, not an optimisation
# --------------------------------------------------------------------------- #


def test_only_the_identifier_gets_a_dynamic_batch_axis():
    """docs/01 § 4 makes batching the crops through ONE call a requirement.

    A graph exported with a fixed batch of 1 cannot do it, and the failure is
    silent: the graph loads, serves, and quietly costs *n* sequential calls per
    frame - which at six bins is the difference between the cost model docs/05
    § 3 states and three times it. The validator stays static because it sees
    exactly one frame, every time.
    """
    assert batched_role("identifier") is True
    assert batched_role("validator") is False


def test_the_sidecar_tells_the_service_whether_it_may_batch():
    # Read, never assumed. The service falls back to sequential when this is
    # false, and says so, rather than crashing on a shape it guessed.
    import json
    import tempfile
    from pathlib import Path

    from sbr.export.onnx_export import sidecar_path, write_sidecar

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        write_sidecar(_report("identifier"), out, Gates.for_role("identifier"))
        payload = json.loads(sidecar_path(out, "identifier", 1).read_text(encoding="utf-8"))
    assert payload["dynamic_batch"] is True


def test_identifier_ignores_map_and_reads_top1():
    # A classifier has no mAP. If check_gates read map50 for the identifier it
    # would report the drop as unmeasured and never judge quantisation at all.
    report = _report("identifier", map50_fp32=0.10, map50_int8=0.99)
    assert report.accuracy_drop == pytest.approx(0.01)
    assert check_gates(report, Gates.for_role("identifier")).may_ship
