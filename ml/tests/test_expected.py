"""The dataset composition contract.

PR #5 fixed how a background image is counted and tested it against synthetic
pools. Nothing asserted the *actual* numbers, so a pool that silently changed
would still have produced a training run - which is the failure mode that cost a
GPU hour on 2026-08-16, when a pool that is 92 % background reported
``background_images: 0`` and training started anyway.

These tests cover the arithmetic and the agreement with the pin. The assertion
against the real Hub is `ml/scripts/preflight_dataset.py`, which needs a network
and therefore cannot live here.
"""

from __future__ import annotations

import pytest

from sbr.dataset.expected import (
    ADJUDICATED,
    EXPECTED,
    CompositionDriftError,
    check_composition,
    check_crop_composition,
    check_manifest_counts,
    crop_counts,
    expectation_for,
)
from sbr.utils.hub import PINS

DETECT = "arudaev/smart-bin-detect"


@pytest.fixture
def expected():
    return EXPECTED[DETECT]


def composition_of(expected, **overrides) -> dict:
    """What ``build_yolo_tree`` writes, for a pool matching the contract."""
    payload = {
        "per_pool": {name: pool.frames for name, pool in expected.pools.items()},
        "background_images": expected.background_frames,
        "positives": expected.positive_frames,
        "classes": ["bin"],
    }
    return payload | overrides


# --------------------------------------------------------------------------- #
# The numbers themselves
# --------------------------------------------------------------------------- #


def test_the_contract_is_the_dataset_card(expected):
    # 370 + 1 110 + 17 474 = 18 954, of which 1 480 are positive. These are the
    # numbers docs/07, docs/11 and the dataset card all quote.
    assert expected.total_frames == 18_954
    assert expected.background_frames == 17_474
    assert expected.positive_frames == 1_480
    assert expected.total_boxes == 403 + 1936


def test_both_negative_ratios_are_reported_and_labelled(expected):
    """Two numbers are in circulation and both are correct.

    15.7:1 is within the Open Images subset; 11.8:1 is against every positive
    frame. AGENTS.md requires saying which, so the code that produces them names
    them rather than returning a bare float.
    """
    ratios = expected.ratios()
    assert ratios["within_the_open_images_subset"] == pytest.approx(15.7, abs=0.1)
    assert ratios["against_all_positives"] == pytest.approx(11.8, abs=0.1)


def test_the_contract_is_pinned_to_the_revision_the_kernels_resolve():
    # If these drift apart, the contract describes data no run will ever see -
    # which is worse than no contract, because it passes.
    assert EXPECTED[DETECT].revision == PINS[DETECT]


def test_the_identifier_contract_landed_with_its_pin():
    """It waited for a composition somebody had actually produced.

    Until 2026-08-21 this asserted the *absence* of a contract, because the
    adjudicated crops did not exist and describing them would have been
    inventing evidence. They exist now, so the contract does - and it is pinned
    to the same revision the kernels resolve, or it describes data no run will
    ever see, which is worse than no contract because it passes.
    """
    identify = "arudaev/smart-bin-identify"
    expectation = expectation_for(identify)
    assert expectation is not None
    assert expectation.revision == PINS[identify] != ""


def test_an_unknown_repo_has_no_contract():
    assert expectation_for("someone/else") is None


# --------------------------------------------------------------------------- #
# The refusal
# --------------------------------------------------------------------------- #


def test_a_matching_pool_passes(expected):
    check_composition(composition_of(expected), expected)


def test_a_lost_subset_is_named(expected):
    broken = composition_of(expected)
    del broken["per_pool"]["negatives"]
    with pytest.raises(CompositionDriftError, match="negatives"):
        check_composition(broken, expected)


def test_the_2026_08_16_failure_would_now_stop_the_run(expected):
    """The exact shape of it: 17 474 negatives in per_pool, and zero background.

    That run reported it, trained anyway, and the number was only read once the
    kernel had already died of something else.
    """
    with pytest.raises(CompositionDriftError, match="background_images"):
        check_composition(
            composition_of(expected, background_images=0, positives=18_954), expected
        )


def test_every_disagreement_is_reported_at_once(expected):
    # A check that stops at the first difference makes somebody dispatch again
    # to discover the second.
    broken = composition_of(expected, background_images=0, positives=1)
    broken["per_pool"]["legacy"] = 12
    with pytest.raises(CompositionDriftError) as raised:
        check_composition(broken, expected)

    message = str(raised.value)
    assert "legacy" in message and "background_images" in message and "positives" in message


def test_a_subset_nobody_wrote_a_contract_for_is_drift(expected):
    # New data is not free: it changes what the model trains on, and the run
    # that first sees it should not be the one that discovers it.
    broken = composition_of(expected)
    broken["per_pool"]["video_deggendorf"] = 500
    with pytest.raises(CompositionDriftError, match="video_deggendorf"):
        check_composition(broken, expected)


# --------------------------------------------------------------------------- #
# The manifest check - stronger, because it sees boxes
# --------------------------------------------------------------------------- #


def test_manifest_counts_match_the_contract(expected):
    check_manifest_counts(
        {name: (pool.frames, pool.boxes) for name, pool in expected.pools.items()}, expected
    )


def test_boxes_are_checked_too_not_only_frames(expected):
    """composition.json does not record box counts, so this is the only place a
    pool that kept its frames and lost its labels would be caught."""
    counts = {name: (pool.frames, pool.boxes) for name, pool in expected.pools.items()}
    counts["legacy"] = (370, 12)
    with pytest.raises(CompositionDriftError, match="12 boxes, expected 403"):
        check_manifest_counts(counts, expected)


# --------------------------------------------------------------------------- #
# The identifier's crops, and the labels on them
# --------------------------------------------------------------------------- #

IDENTIFY = "arudaev/smart-bin-identify"


def crop(file: str, state: str, form_factor: str | None) -> dict:
    return {"file": file, "adjudication": state, "form_factor": form_factor}


@pytest.fixture
def identify():
    return EXPECTED[IDENTIFY]


@pytest.fixture
def as_pinned():
    """The 403 crops exactly as the human pass left them."""
    records = (
        [crop(f"s{i}.jpg", "authored", "wheelie_small") for i in range(247)]
        + [crop(f"l{i}.jpg", "authored", "wheelie_large") for i in range(115)]
        + [crop(f"g{i}.jpg", "authored", "igloo") for i in range(40)]
        + [crop("b0.jpg", "authored", "street_basket")]
    )
    return {"crop_records": records}


def test_the_counts_agree_with_the_contract(identify, as_pinned):
    check_crop_composition({"legacy": crop_counts(as_pinned)}, identify)


def test_a_pending_crop_is_named_rather_than_counted(identify):
    manifest = {"crop_records": [crop("a.jpg", "pending", "wheelie_small")]}
    counts = crop_counts(manifest)
    assert counts.pending == 1
    assert counts.adjudicated == 0
    # The pool's stream -> shape guess sits in `form_factor` on a pending crop.
    # Counting it would let the guess satisfy a contract about the human pass.
    assert counts.by_form_factor == {}


def test_a_rejection_is_a_decision_and_not_outstanding_work(identify):
    counts = crop_counts({"crop_records": [crop("a.jpg", "rejected", None)]})
    assert (counts.rejected, counts.pending, counts.adjudicated) == (1, 0, 0)


def test_labels_can_drift_while_every_total_holds(identify, as_pinned):
    """The reason this contract exists at all.

    403 crops stay 403 crops, 403 adjudicated stay 403 adjudicated, and eleven
    wheelies change size. Totals see nothing; the identifier trains on the
    difference.
    """
    for record in as_pinned["crop_records"][:11]:
        record["form_factor"] = "wheelie_large"

    counts = crop_counts(as_pinned)
    assert counts.crops == 403 and counts.adjudicated == 403

    with pytest.raises(CompositionDriftError) as raised:
        check_crop_composition({"legacy": counts}, identify)
    assert "labels changed" in str(raised.value)
    assert "wheelie_small" in str(raised.value)


def test_a_half_applied_decision_file_stops_the_run(identify, as_pinned):
    as_pinned["crop_records"][0]["adjudication"] = "pending"
    with pytest.raises(CompositionDriftError) as raised:
        check_crop_composition({"legacy": crop_counts(as_pinned)}, identify)
    assert "still pending adjudication" in str(raised.value)


def test_street_basket_is_asserted_because_it_exists(identify):
    """Its n=1 keeps it out of a class list, not out of the contract.

    An id with one photograph is a coverage gap to record, not a fact to forget:
    if it silently became two, or zero, that is a change to the human pass and
    the pin should have moved.
    """
    assert identify.pools["legacy"].crops_by_form_factor["street_basket"] == 1


def test_the_two_definitions_of_adjudicated_are_the_same_one():
    # Stated twice, in the contract and in the builder. The day they disagree,
    # the contract passes over crops build_classification_tree skips.
    from sbr.dataset.prepare import ADJUDICATED as BUILDER

    assert ADJUDICATED == frozenset(BUILDER)
