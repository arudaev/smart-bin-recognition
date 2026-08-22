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
        # The deployment target. A proxy measurement is its own test below.
        latency_representative=True,
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


def test_unquantised_artefact_fails_for_a_role_with_no_fp32_profile():
    """The identifier has no fp32 profile, so fp32 is still refused outright.

    P11 measured int8 costing the identifier 0.0000 top-1, so it has nothing to
    gain from fp32 and would only pay the concurrency. Absence of a profile is
    the decision, and it is enforced.
    """
    result = check_gates(_report("identifier", quantised=False), Gates.for_role("identifier"))
    assert any("no fp32 profile" in f for f in result.failures)


def test_an_unquantised_validator_is_judged_against_its_fp32_profile():
    """docs/12 P13: the format selects a profile; the measured latency decides.

    24.6 ms is what P13 measured on Cascade Lake at 448. It is inside the same
    50 ms budget int8 is judged against, which is the whole finding - the old
    gate refused this artefact while asserting a reason that was never true.

    Note `accuracy_onnx`, not `map50_int8`. An earlier version of this test
    passed `map50_int8=map50_fp32` to get a zero drop, which is a fabrication:
    an fp32 artefact has no int8 measurement and never will. That fabrication
    made the test pass while the REAL artefact stayed `may_ship: false`, which
    is the exact failure `test_the_real_fp32_sidecar_is_still_blocked_on_its_score`
    below now pins.
    """
    result = check_gates(
        _report(quantised=False, median_latency_ms=24.6, map50_fp32=0.7524, accuracy_onnx=0.7519),
        Gates.for_role("validator"),
    )
    assert result.failures == []
    assert result.may_ship is True


def test_the_real_fp32_sidecar_is_still_blocked_on_its_own_score():
    """The artefact on disk, not a fabricated one.

    `artifacts/local/validator-v1.json` carries `map50_fp32: 0.7524` copied from
    the PyTorch training run - its own provenance says "not measured here" - and
    no score for the exported graph. So even with the fp32 profile and P13's
    latency it must NOT ship, and the reason must name the missing eval rather
    than talk about int8.
    """
    result = check_gates(
        _report(
            quantised=False,
            median_latency_ms=24.605,
            latency_representative=True,
            map50_fp32=0.7524,
            map50_int8=None,
            accuracy_onnx=None,
        ),
        Gates.for_role("validator"),
    )
    assert result.may_ship is False
    assert result.failures == []
    assert any("has not been scored" in u for u in result.unmeasured)
    assert not any("int8" in u for u in result.unmeasured), (
        "asking an fp32 artefact what int8 cost it is the bug this branch fixes"
    )


def test_an_fp32_export_that_lost_accuracy_still_fails():
    """Export is a transformation. A graph that degraded in the box fails here."""
    result = check_gates(
        _report(quantised=False, median_latency_ms=24.6, map50_fp32=0.7524, accuracy_onnx=0.70),
        Gates.for_role("validator"),
    )
    assert any("quantisation cost" in f or "0.05" in f for f in result.failures)
    assert result.may_ship is False


def test_an_unquantised_validator_that_is_genuinely_slow_still_fails():
    """The gate did not become a waiver. It became a measurement."""
    result = check_gates(
        _report(quantised=False, median_latency_ms=61.0, map50_fp32=0.7524, map50_int8=0.7524),
        Gates.for_role("validator"),
    )
    assert any("exceeds the 50 ms budget" in f for f in result.failures)


def test_a_format_profile_may_not_loosen_accuracy():
    """The one thing the split must never enable.

    A per-format LATENCY budget is the point. A per-format ACCURACY budget would
    let a format buy its way past the gate that exists to stop a
    confidently-wrong model shipping, which is this product's worst failure.
    """
    with pytest.raises(ValueError, match="never accuracy"):
        Gates.from_config(
            "validator",
            {
                "export": {
                    "gates": {
                        "max_median_latency_ms": 50,
                        "max_accuracy_drop": 0.02,
                        "fp32": {"max_accuracy_drop": 0.75},
                    }
                }
            },
        )


def test_the_validator_fp32_profile_carries_what_the_format_costs():
    """5 concurrent scanners become 4. A gate that hides that is a gate lying."""
    profile = Gates.for_role("validator").fp32_profile
    assert profile is not None
    assert profile.max_accuracy_drop == PINNED_ACCURACY_DROP
    assert profile.concurrent_scanners_at_1_bin == 4
    assert "P13" in profile.measured_by


def test_the_identifier_has_no_fp32_profile():
    assert Gates.for_role("identifier").fp32_profile is None


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


def test_a_proxy_latency_does_not_close_the_gate():
    """Every document in this project says a proxy does not close it. Until
    2026-08-21 nothing enforced that.

    `check_gates` required only that the hardware be NAMED, so a Kaggle
    kernel's figure - free, x86, explicitly `representative: false` - could
    carry an artefact to may_ship. The budget is stated on service CPU, and a
    number from somewhere else does not answer it.
    """
    result = check_gates(
        _report(
            median_latency_ms=34.4,
            latency_hardware="Kaggle CPU kernel, 2 of 4 vCPU [PROXY, not the service]",
            latency_representative=False,
        ),
        Gates.for_role("validator"),
    )
    assert not result.may_ship
    # UNMEASURED, not a failure: 34.4 ms may well be fine, and nobody has
    # measured it where the budget is stated. The evidence is missing, which is
    # a different statement from the model being too slow.
    assert not result.failures
    assert any("not the service" in u for u in result.unmeasured)


def test_an_unrecorded_representativeness_is_not_assumed_either_way():
    result = check_gates(
        _report(latency_representative=None), Gates.for_role("validator")
    )
    assert not result.may_ship
    assert any("not the service" in u for u in result.unmeasured)
