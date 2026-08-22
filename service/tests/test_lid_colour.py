"""The lid sampler exists, works, and is deliberately not wired in.

docs/12 P3 (amended 2026-08-22) scored the upper-band sampler at 0.1966 against
a 0.60 floor, on 117 wheelies whose lids were visible in 98% of frames. The
pre-registered rule's third row therefore fires: do not wire it.

That is an easy decision to undo by accident - the function is right there and
`lid_color=None` looks like an oversight rather than a verdict. These tests make
the omission deliberate and noisy, so a future change has to argue with the
probe instead of quietly disagreeing with it.
"""

from __future__ import annotations

import numpy as np

import colour
from pipeline import Pipeline


def _two_tone(lid_rgb, body_rgb, h=120, w=80):
    crop = np.zeros((h, w, 3), np.uint8)
    band = max(1, int(np.ceil(h * colour.LID_BAND_FRACTION)))
    crop[:band] = lid_rgb
    crop[band:] = body_rgb
    return crop


def test_the_sampler_separates_a_lid_from_a_body():
    """On a synthetic bin it works, which is why the 0.1966 is about real pixels."""
    crop = _two_tone((31, 79, 168), (242, 242, 242))
    assert colour.measure_lid_colour(crop)[0] == "blue"
    assert colour.measure_body_colour(crop)[0] == "white"


def test_the_band_is_the_top_of_the_box():
    crop = _two_tone((242, 242, 242), (26, 26, 26))
    assert colour.measure_lid_colour(crop)[0] == "white"
    assert colour.measure_body_colour(crop)[0] == "black"


def test_an_unnameable_lid_is_none_rather_than_a_guess():
    """Past MAX_DELTA_E the honest answer is None, and None never matches a rule."""
    crop = _two_tone((255, 0, 255), (128, 128, 128))
    name, delta = colour.measure_lid_colour(crop)
    assert name is None
    assert delta > colour.MAX_DELTA_E


def test_the_service_still_reports_lid_colour_as_not_measured():
    note = colour.measurement_note()["lid_colour"]
    assert "NOT measured" in note
    assert "0.1966" in note, "the health note must carry the number the decision rests on"


def test_the_pipeline_does_not_populate_lid_colour():
    """The wiring P3 forbids.

    If this test starts failing, P3's third rule was overruled - which is
    allowed, but only on a new measurement and the maintainer's decision, not by
    an edit that makes an omission look like an oversight.
    """
    import inspect

    body = inspect.getsource(Pipeline.run)
    assert "lid_color=None" in body, (
        "pipeline.run no longer passes lid_color=None. docs/12 P3 scored the lid sampler at "
        "0.1966 against a 0.60 floor and its third rule says do not wire it. Overruling that "
        "needs a new measurement, not an edit."
    )
