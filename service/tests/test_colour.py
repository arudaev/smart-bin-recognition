"""Colour measurement.

The method is provisional pending docs/12 probe P3, so what is tested here is
not "does it get the right answer on real bins" - nothing can answer that until
P3's hand-labelled ground truth exists. What is tested is that the arithmetic is
right, that the illuminant normalisation does the thing it claims, and that the
honest failure - *I cannot tell* - actually happens instead of a wrong name.
"""

from __future__ import annotations

import numpy as np
import pytest

from colour import (
    MAX_DELTA_E,
    apply_illuminant,
    delta_e_2000,
    estimate_illuminant,
    measure_body_colour,
    named_colours,
    srgb_to_lab,
)

# --------------------------------------------------------------------------- #
# CIEDE2000, against the published reference pairs
# --------------------------------------------------------------------------- #

#: From Sharma, Wu and Dalal's supplementary test data - the standard set used to
#: verify a CIEDE2000 implementation, and specifically chosen to exercise the
#: hue-rotation term and the discontinuity around 0/360 degrees where naive
#: implementations quietly disagree.
SHARMA_PAIRS = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize(("lab1", "lab2", "expected"), SHARMA_PAIRS)
def test_ciede2000_matches_the_reference_implementation(lab1, lab2, expected):
    assert delta_e_2000(np.array(lab1), np.array(lab2)) == pytest.approx(expected, abs=1e-4)


def test_delta_e_is_zero_for_identical_colours():
    lab = srgb_to_lab(np.array([0.2, 0.4, 0.6]))
    assert delta_e_2000(lab, lab) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# sRGB to CIELAB
# --------------------------------------------------------------------------- #


def test_white_is_l100_and_neutral():
    lab = srgb_to_lab(np.array([1.0, 1.0, 1.0]))
    assert lab[0] == pytest.approx(100.0, abs=1e-3)
    assert lab[1] == pytest.approx(0.0, abs=1e-2)
    assert lab[2] == pytest.approx(0.0, abs=1e-2)


def test_black_is_l0():
    assert srgb_to_lab(np.array([0.0, 0.0, 0.0]))[0] == pytest.approx(0.0, abs=1e-6)


def test_mid_grey_is_neutral_and_not_mid_lightness():
    # sRGB 0.5 is L* ~53.4, not 50 - the transfer function is not linear, and an
    # implementation that skipped it would put every grey bin in the wrong place.
    lab = srgb_to_lab(np.array([0.5, 0.5, 0.5]))
    assert lab[0] == pytest.approx(53.389, abs=0.01)
    assert abs(lab[1]) < 0.01 and abs(lab[2]) < 0.01


# --------------------------------------------------------------------------- #
# The named vocabulary
# --------------------------------------------------------------------------- #


def test_the_colour_names_come_from_the_taxonomy():
    # Never restated here. The vocabulary is part of the product's spine and a
    # second copy is one more thing that can drift.
    names = named_colours()
    assert {"blue", "green", "brown", "black", "grey", "yellow", "orange", "red"} <= set(names)


def test_every_named_colour_measures_as_itself():
    """The sanity floor: a flat patch of a reference colour must come back as it."""
    for name, lab in named_colours().items():
        if name in {"transparent", "metal"}:
            # Neither is a surface colour in the sense a single ΔE can capture:
            # transparent has no reflectance of its own and metal is defined by
            # its specularity. They stay in the vocabulary because packs match on
            # them; measuring them from a mean pixel is a separate problem.
            continue
        patch = _lab_to_srgb_patch(lab)
        measured, distance = measure_body_colour(patch)
        assert measured == name, f"{name} measured as {measured} (dE {distance:.1f})"


def test_estimating_the_illuminant_from_the_crop_would_destroy_the_measurement():
    """The bug the first draft of this module shipped with.

    Shades of Gray assumes average scene reflectance is neutral. A crop of a
    single bin is precisely the input that fails on: the bin's own colour becomes
    the illuminant estimate, and normalising it away turns every bin grey. A blue
    bin measured as grey is worse than no normalisation at all, so the illuminant
    is estimated from the frame and this test pins the reason.
    """
    blue = _lab_to_srgb_patch(named_colours()["blue"])
    from_the_crop = estimate_illuminant(blue.astype(np.float64) / 255.0)

    wrong, _ = measure_body_colour(blue, from_the_crop)
    right, _ = measure_body_colour(blue)
    assert wrong != "blue"
    assert right == "blue"


def test_a_colour_far_from_every_name_is_admitted_as_unknown():
    """`None` is the designed answer, not a fallback.

    A bin at dusk in the rain is not a measurement anybody should bet a disposal
    rule on, and `None` propagates to a rule that cannot match - which is exactly
    what the resolver does with a missing attribute.
    """
    # A saturated magenta. Its nearest name is `metal` at ΔE 23.9, which is how
    # the 32 the first draft used got caught: a band wider than the vocabulary it
    # filters is not a filter.
    patch = np.full((40, 40, 3), (255, 0, 200), dtype=np.uint8)
    measured, distance = measure_body_colour(patch)
    assert measured is None
    assert distance > MAX_DELTA_E


def test_the_unknown_band_is_narrower_than_the_vocabulary_it_filters():
    """A threshold above the typical gap between two names cannot separate them.

    The eleven references sit about 27 ΔE apart at the median. If the band were
    wider than that, every measurement would land on something and `unknown`
    would never happen - which is the state that feeds the improvement loop.
    """
    import itertools

    references = named_colours()
    gaps = sorted(
        delta_e_2000(references[a], references[b])
        for a, b in itertools.combinations(references, 2)
    )
    assert MAX_DELTA_E < gaps[len(gaps) // 2]


def test_an_empty_crop_is_unknown_rather_than_a_crash():
    measured, _ = measure_body_colour(np.zeros((0, 0, 3), dtype=np.uint8))
    assert measured is None


# --------------------------------------------------------------------------- #
# Illuminant normalisation
# --------------------------------------------------------------------------- #


def test_the_illuminant_estimate_pulls_a_colour_cast_back_out():
    """The whole point of research/06 § 1: a camera records colour x illuminant.

    A varied scene under a warm light reads warm. Corrected, the channels should
    be far closer together than they were.
    """
    rng = np.random.default_rng(0)
    scene = rng.random((4000, 3))            # varied reflectance: the assumption holds
    lit = np.clip(scene * np.array([1.25, 1.0, 0.75]), 0, 1)   # a warm light

    before = np.ptp(lit.mean(axis=0))
    after = np.ptp(apply_illuminant(lit, estimate_illuminant(lit)).mean(axis=0))
    assert after < before


def test_normalisation_is_a_no_op_on_black():
    # A zero illuminant estimate must not divide by zero and must not invent
    # colour out of an underexposed frame.
    black = np.zeros((100, 3))
    assert np.allclose(estimate_illuminant(black), np.ones(3))
    assert np.allclose(apply_illuminant(black, estimate_illuminant(black)), black)


def _lab_to_srgb_patch(lab: np.ndarray, size: int = 40) -> np.ndarray:
    """Round-trip a reference Lab back to an sRGB patch, via search.

    Inverting CIELAB properly would be another forty lines of code to get wrong.
    The reference colours came from hex in the first place, so finding the hex
    whose Lab this is costs one lookup over the vocabulary the test already has.
    """
    import json
    from pathlib import Path

    from sbr.taxonomy import TAXONOMY_PATH

    raw = json.loads(Path(TAXONOMY_PATH).read_text(encoding="utf-8"))
    for entry in raw["colors"]:
        candidate = srgb_to_lab(
            np.array([int(entry["hex_ref"].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]) / 255.0
        )
        if np.allclose(candidate, lab):
            rgb = [int(entry["hex_ref"].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
            return np.full((size, size, 3), rgb, dtype=np.uint8)
    raise AssertionError("reference colour not found in the taxonomy")
