"""Tests for the human pass.

The tool itself is small; what is tested is the discipline around it. An
adjudication record is a person's judgement, and the two ways to lose it are to
overwrite it and to let something unadjudicated pass for adjudicated.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from sbr.dataset.prepare import ADJUDICATED

ML_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("adjudicate", ML_ROOT / "scripts" / "adjudicate.py")
adjudicate = importlib.util.module_from_spec(_spec)
sys.modules["adjudicate"] = adjudicate
_spec.loader.exec_module(adjudicate)

Review = adjudicate.Review
apply_decisions = adjudicate.apply_decisions


@pytest.fixture
def pool(archive: Path, expectations: dict, tmp_path: Path) -> Path:
    from sbr.dataset.legacy_import import import_legacy

    out = tmp_path / "pool"
    import_legacy(archive, out, config=expectations)
    return out


@pytest.fixture
def review(pool: Path) -> adjudicate.Review:
    return Review(pool, reviewer="tester")


def test_the_queue_holds_every_crop(review, pool):
    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    assert len(review.queue) == len(manifest["crop_records"])


def test_the_queue_is_ordered_by_cluster_so_alike_bins_are_adjacent(review):
    clusters = [c["_cluster"] for c in review.queue]
    assert clusters == sorted(clusters)


def test_a_decision_is_recorded_with_who_and_when(review):
    first = review.queue[0]["file"]
    review.record(first, "confirmed", "wheelie_small")
    entry = review.decisions[first]
    assert entry["reviewer"] == "tester"
    assert entry["decided"]
    assert entry["form_factor"] == "wheelie_small"


def test_a_decision_survives_a_restart(review, pool):
    first = review.queue[0]["file"]
    review.record(first, "confirmed", "wheelie_small")

    resumed = Review(pool, reviewer="tester")
    assert resumed.decisions[first]["form_factor"] == "wheelie_small"
    assert resumed.state()["done"] == 1


def test_an_invented_form_factor_is_refused(review):
    with pytest.raises(ValueError, match="not a form factor"):
        review.record(review.queue[0]["file"], "confirmed", "wheelie_enormous")


def test_rejecting_a_crop_records_no_form_factor(review):
    first = review.queue[0]["file"]
    review.record(first, "rejected", None)
    assert review.decisions[first]["form_factor"] is None


def test_applying_to_a_cluster_covers_its_siblings(review):
    target = review.queue[0]["file"]
    siblings = review.cluster_of(target)
    assert len(siblings) >= 1
    for file in siblings:
        review.record(file, "confirmed", "wheelie_small")
    assert all(f in review.decisions for f in siblings)


def test_a_cluster_never_spans_two_legacy_classes(review):
    for crop in review.queue:
        classes = {
            c["legacy_class"] for c in review.queue if c["file"] in review.cluster_of(crop["file"])
        }
        assert len(classes) == 1


# --------------------------------------------------------------------------- #
# Folding decisions back
# --------------------------------------------------------------------------- #


def test_apply_marks_crops_human_labelled(review, pool):
    for crop in review.queue:
        review.record(crop["file"], "confirmed", "wheelie_small")

    summary = apply_decisions(pool)
    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    assert summary["still_pending"] == 0
    # Some of these are corrections rather than confirmations - wheelie_small on
    # a Glas crop is not the pre-fill - and both are adjudicated.
    assert {c["adjudication"] for c in manifest["crop_records"]} <= ADJUDICATED
    assert {c["label_origin"] for c in manifest["crop_records"]} == {"human"}
    assert all(c["adjudicated_by"] == "tester" for c in manifest["crop_records"])


def test_apply_leaves_undecided_crops_pending(review, pool):
    review.record(review.queue[0]["file"], "confirmed", "wheelie_small")
    summary = apply_decisions(pool)
    assert summary["applied"] == 1
    assert summary["still_pending"] == len(review.queue) - 1

    manifest = json.loads((pool / "manifest.json").read_text(encoding="utf-8"))
    pending = [c for c in manifest["crop_records"] if c["adjudication"] == "pending"]
    assert all(c["form_factor"] is None for c in pending)


def test_apply_without_decisions_stops(pool):
    with pytest.raises(SystemExit, match="nothing to apply"):
        apply_decisions(pool)


def test_applied_crops_then_reach_the_identifier_tree(review, pool, tmp_path):
    from sbr.dataset.prepare import build_classification_tree

    for crop in review.queue:
        review.record(crop["file"], "confirmed", "igloo")
    apply_decisions(pool)

    out = tmp_path / "cls"
    build_classification_tree(
        pool, out, {"data": {"classes_from_taxonomy": True, "require_adjudication": True}}
    )
    assert list(out.glob("*/igloo/*.jpg"))


def test_a_correction_is_distinguishable_from_a_confirmation(review):
    # The pre-fill's accuracy is worth knowing: if most decisions are
    # corrections, the proposal is not helping and should change.
    crop = review.queue[0]
    other = next(f for f in review.classes if f != crop["form_factor_proposed"])
    review.record(crop["file"], "corrected", other)
    assert review.decisions[crop["file"]]["adjudication"] == "corrected"
    assert review.decisions[crop["file"]]["proposed"] == crop["form_factor_proposed"]


def test_the_verdict_is_derived_not_taken_on_trust(review):
    # A caller claiming "confirmed" while picking something other than the
    # pre-fill would make the proposal look better than it is.
    crop = review.queue[0]
    other = next(f for f in review.classes if f != crop["form_factor_proposed"])
    review.record(crop["file"], "confirmed", other)
    assert review.decisions[crop["file"]]["adjudication"] == "corrected"

    review.record(crop["file"], "corrected", crop["form_factor_proposed"])
    assert review.decisions[crop["file"]]["adjudication"] == "confirmed"


def test_an_unknown_verdict_is_refused(review):
    with pytest.raises(ValueError, match="not a verdict"):
        review.record(review.queue[0]["file"], "probably", "igloo")


# --------------------------------------------------------------------------- #
# Blind mode - required for the docs/12 P1 pilot
# --------------------------------------------------------------------------- #


@pytest.fixture
def blind_review(pool: Path) -> adjudicate.Review:
    return Review(pool, reviewer="tester", blind=True)


def test_blind_mode_withholds_the_proposal_from_the_reviewer(blind_review):
    """P1 measures whether `wheelie_small` and `wheelie_large` are separable.

    The pool ships proposals derived from the legacy waste STREAM, and on the
    real 403 crops that mapping is **wrong on 28.8 %** - 111 of 116 errors being
    `wheelie_small` where the answer is `wheelie_large`, which is precisely the
    pair the pilot exists to test. The UI shows the proposal and binds Enter to
    accept it. A pilot run that way would measure the mapping table.
    """
    state = blind_review.state()
    assert state["blind"] is True
    for crop in state["queue"]:
        assert crop["proposed"] is None
        assert crop["candidates"] == []


def test_a_blind_decision_is_authored_not_confirmed(blind_review):
    # Nothing was proposed, so nothing was confirmed. A blind decision is
    # evidence in a way a confirmation is not, and the record has to say which.
    crop = blind_review.queue[0]
    blind_review.record(crop["file"], "confirmed", "igloo")
    decision = blind_review.decisions[crop["file"]]
    assert decision["adjudication"] == "authored"
    assert decision["proposed"] is None
    assert decision["form_factor"] == "igloo"


def test_blind_mode_still_refuses_an_invented_form_factor(blind_review):
    with pytest.raises(ValueError, match="not a form factor"):
        blind_review.record(blind_review.queue[0]["file"], "confirmed", "skip")


def test_sighted_mode_is_unchanged_by_the_blind_option(review):
    # The default must keep behaving exactly as before: blind is opt-in.
    assert review.state()["blind"] is False
    crop = review.queue[0]
    review.record(crop["file"], "confirmed", crop["form_factor_proposed"])
    assert review.decisions[crop["file"]]["adjudication"] == "confirmed"
