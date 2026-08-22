"""Measuring a bin's colour from pixels.

docs/02 § 1 makes colour the second axis of the taxonomy and calls it *measured,
never learnt* - which is what lets a new country ship as a JSON pull request
rather than a retrain. This module is that measurement.

**PROVISIONAL, and deliberately so.** ``docs/12`` probe **P3** is what decides
the method, and P3 has not run. What is implemented here is P3's variant 4 -
centre-weighted sampling inside the box, illuminant-normalised by Shades of Gray
at *p* = 6, assigned in CIELAB by ΔE to the nearest named colour - because
``docs/research/06-colour-measurement.md`` § 3 argues it is the likely winner and
because it is the strongest option that adds **no dependency**. When P3 reports,
this file changes and the note goes with it.

Two things it does **not** do, both on purpose:

- **No SAM.** docs/04 § 1 assumed a mask; research/06 § 3 points out the crop is
  already filled by the object (the validator localised it, and the identifier
  pads by 0.12), so a mask may buy nothing. Adding a segmentation dependency
  before the probe says it is needed would be exactly the mistake docs/12 exists
  to prevent.
- **No lid.** Separating lid from body is unsolved by any method in research/06 -
  a mask gives one object, not parts - and it is explicitly out of scope for P3.
  ``lid_color`` is therefore ``None`` rather than a guess, and the resolver
  treats a missing attribute as *never satisfies a constraint* rather than as a
  wildcard.

Colour is also the axis most likely to be honestly unknown: a bin at dusk in the
rain is not a measurement anybody should bet a disposal rule on. Above
:data:`MAX_DELTA_E` this returns ``None``, and ``None`` propagates to ``unknown``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

#: Where the illuminant estimate comes from. Shades of Gray with p=6 - the
#: Minkowski norm generalising Gray World (p=1) and max-RGB (p=inf) - which
#: research/06 § 2 records as usually beating Gray World at the same trivial cost.
SHADES_OF_GRAY_P = 6.0

#: Fraction of the box sampled, centred. The crop is mostly bin, but the corners
#: are mostly not: a rectangle around a wheelie bin catches sky at the top and
#: pavement at the bottom corners.
CENTRE_FRACTION = 0.5

#: How much of the box, from the top, is treated as lid.
#:
#: **The simplest thing that could work, and deliberately so.** docs/12 P3's lid
#: half says to start with geometry and reach for segmentation only if the
#: measurement shows geometry is not enough - so this is a band, not a mask.
#: A wheelie bin's lid is roughly the top fifth of its silhouette seen from the
#: front and rather more seen from above; 0.22 is inside that range at both
#: angles and is what P3 scored.
LID_BAND_FRACTION = 0.22

#: How much of the lid band's WIDTH is sampled, centred.
#:
#: Narrower than the body's 0.5 because the lid's top corners are where the sky
#: is: a bin photographed from below has its lid edge against bright background
#: on both sides, and those pixels drag a dark lid towards grey.
LID_WIDTH_FRACTION = 0.6

#: Beyond this ΔE from every named colour, the honest answer is that we do not
#: know.
#:
#: **UNMEASURED** - P3's third decision rule is what sets it properly, against
#: hand-labelled ground truth that does not exist yet. It is not arbitrary
#: though: the eleven reference colours are 8.7 ΔE apart at their closest
#: (grey/metal) and about 27 at the median, so a threshold has to sit below the
#: median to mean anything at all. An earlier draft used 32 and accepted a
#: saturated magenta as `metal` at 23.9 - a band wider than the vocabulary it is
#: filtering is not a filter.
MAX_DELTA_E = 20.0


@lru_cache(maxsize=1)
def named_colours(taxonomy_path: Path | None = None) -> dict[str, np.ndarray]:
    """The eleven named colours as CIELAB, from ``waste-streams.json``.

    Read from the taxonomy rather than restated here. The colour vocabulary is
    part of the product's spine and a second copy of it would be one more thing
    that can drift.
    """
    from sbr.taxonomy import TAXONOMY_PATH

    path = taxonomy_path or TAXONOMY_PATH
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        entry["id"]: srgb_to_lab(_hex_to_rgb(entry["hex_ref"]))
        for entry in raw["colors"]
        if entry.get("hex_ref")
    }


def _hex_to_rgb(value: str) -> np.ndarray:
    text = value.lstrip("#")
    return np.array([int(text[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float64) / 255.0


# --------------------------------------------------------------------------- #
# Colour spaces
# --------------------------------------------------------------------------- #

#: sRGB D65 primaries.
_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)
_D65 = np.array([0.95047, 1.00000, 1.08883])


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB in [0, 1] to CIELAB. Accepts a single colour or an (N, 3) block."""
    rgb = np.atleast_2d(np.asarray(rgb, dtype=np.float64))
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = linear @ _RGB_TO_XYZ.T / _D65

    epsilon = 216 / 24389
    kappa = 24389 / 27
    f = np.where(xyz > epsilon, np.cbrt(xyz), (kappa * xyz + 16) / 116)

    lab = np.stack(
        [116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=-1
    )
    return lab[0] if lab.shape[0] == 1 else lab


def delta_e_2000(lab1: np.ndarray, lab2: np.ndarray) -> float:
    """CIEDE2000 colour difference.

    ΔE76 - a plain Euclidean distance in Lab - would be far less code, and for
    eleven well-separated reference colours it would usually pick the same
    neighbour. It is the *threshold* that needs CIEDE2000: :data:`MAX_DELTA_E` is
    a single number applied across the whole colour wheel, and ΔE76's error is
    strongly hue-dependent, so one cut-off would mean quite different things for
    a blue lid and a yellow one.

    Verified against the Sharma et al. reference pairs in ``tests/test_colour.py``.
    """
    l1, a1, b1 = (float(v) for v in lab1)
    l2, a2, b2 = (float(v) for v in lab2)

    c1 = np.hypot(a1, b1)
    c2 = np.hypot(a2, b2)
    c_bar = (c1 + c2) / 2
    g = 0.5 * (1 - np.sqrt(c_bar**7 / (c_bar**7 + 25.0**7))) if c_bar > 0 else 0.5

    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360 if (a2p or b2) else 0.0

    dlp = l2 - l1
    dcp = c2p - c1p

    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dhp_term = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dhp) / 2)

    lp_bar = (l1 + l2) / 2
    cp_bar = (c1p + c2p) / 2

    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hp_bar = (h1p + h2p + 360) / 2
    else:
        hp_bar = (h1p + h2p - 360) / 2

    t = (
        1
        - 0.17 * np.cos(np.radians(hp_bar - 30))
        + 0.24 * np.cos(np.radians(2 * hp_bar))
        + 0.32 * np.cos(np.radians(3 * hp_bar + 6))
        - 0.20 * np.cos(np.radians(4 * hp_bar - 63))
    )

    sl = 1 + (0.015 * (lp_bar - 50) ** 2) / np.sqrt(20 + (lp_bar - 50) ** 2)
    sc = 1 + 0.045 * cp_bar
    sh = 1 + 0.015 * cp_bar * t

    delta_theta = 30 * np.exp(-(((hp_bar - 275) / 25) ** 2))
    rc = 2 * np.sqrt(cp_bar**7 / (cp_bar**7 + 25.0**7))
    rt = -rc * np.sin(np.radians(2 * delta_theta))

    return float(
        np.sqrt(
            (dlp / sl) ** 2
            + (dcp / sc) ** 2
            + (dhp_term / sh) ** 2
            + rt * (dcp / sc) * (dhp_term / sh)
        )
    )


# --------------------------------------------------------------------------- #
# The measurement
# --------------------------------------------------------------------------- #


def estimate_illuminant(frame: np.ndarray, p: float = SHADES_OF_GRAY_P) -> np.ndarray:
    """Per-channel gain that neutralises the scene's illuminant.

    A camera does not record object colour; it records object colour x
    illuminant x white balance x exposure (research/06 § 1). Rain, shade, dusk
    and sodium street lighting all move the measured value, and we need a stable
    assignment to one of a dozen names rather than colorimetric truth - which is
    a much weaker requirement, and what makes a statistical estimator enough.

    **Estimated from the whole frame, never from the crop.** This is the thing
    research/06 § 2 does not say and the tests found: Shades of Gray assumes
    average scene reflectance is neutral, and a crop of a single bin is the exact
    input that assumption fails on. Estimating from the crop makes the bin's own
    colour *become* the illuminant, and normalising it away turns every bin grey -
    which is what the first draft of this module did, and a blue bin measured as
    grey is worse than no normalisation at all.

    A frame is a much better sample of the assumption: it holds road, sky,
    pavement and building alongside the bin. It is still not a guarantee - a frame
    filled edge to edge with one container would fail the same way - and that
    residual is one of the things P3 should look at.
    """
    pixels = np.asarray(frame, dtype=np.float64).reshape(-1, 3)
    if pixels.size == 0:
        return np.ones(3)

    illuminant = (np.mean(pixels**p, axis=0)) ** (1 / p)
    norm = float(np.linalg.norm(illuminant))
    if norm == 0 or not np.isfinite(norm):
        return np.ones(3)
    # Scale so the estimate becomes neutral grey, preserving overall brightness.
    return (norm / np.sqrt(3)) / np.maximum(illuminant, 1e-6)


def apply_illuminant(pixels: np.ndarray, gain: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(pixels, dtype=np.float64) * gain, 0.0, 1.0)


def centre_sample(crop: np.ndarray, fraction: float = CENTRE_FRACTION) -> np.ndarray:
    """The middle of the box, flattened to an (N, 3) block of sRGB in [0, 1]."""
    height, width = crop.shape[:2]
    half = fraction / 2
    y0, y1 = int(height * (0.5 - half)), int(np.ceil(height * (0.5 + half)))
    x0, x1 = int(width * (0.5 - half)), int(np.ceil(width * (0.5 + half)))
    inner = crop[max(0, y0) : max(1, y1), max(0, x0) : max(1, x1)]
    if inner.size == 0:
        inner = crop
    return inner.reshape(-1, 3).astype(np.float64) / 255.0


def measure_body_colour(
    crop: np.ndarray, gain: np.ndarray | None = None
) -> tuple[str | None, float]:
    """Name the body colour of one crop, or admit it is not measurable.

    ``gain`` comes from :func:`estimate_illuminant` over the **whole frame** -
    see that function for why it must not come from the crop. Passing ``None``
    skips normalisation entirely, which is honest but worse: it measures colour
    under whatever light happened to be there.

    Returns ``(name, delta_e)``. ``name`` is ``None`` when nothing is within
    :data:`MAX_DELTA_E`, and ``None`` means the resolver will not match a rule
    constraining colour - which is the correct outcome, not a degraded one.
    """
    if crop is None or crop.size == 0:
        return None, float("inf")

    sample = centre_sample(crop)
    if gain is not None:
        sample = apply_illuminant(sample, gain)
    mean_rgb = sample.mean(axis=0)
    lab = srgb_to_lab(mean_rgb)

    distances = {name: delta_e_2000(lab, ref) for name, ref in named_colours().items()}
    best = min(distances, key=lambda name: distances[name])
    if distances[best] > MAX_DELTA_E:
        return None, distances[best]
    return best, distances[best]


def lid_sample(crop: np.ndarray) -> np.ndarray:
    """The upper band of the box, flattened to (N, 3) sRGB in [0, 1].

    Deliberately the crudest thing that could answer the question. A lid is not
    a region a rectangle can isolate in general - a bin photographed from the
    side puts lid and body in the same rows - and the honest way to find out
    whether that matters is to measure a band and see what it scores, rather
    than to add a segmentation dependency on the strength of an argument.
    """
    height, width = crop.shape[:2]
    y1 = max(1, int(np.ceil(height * LID_BAND_FRACTION)))
    half = LID_WIDTH_FRACTION / 2
    x0, x1 = int(width * (0.5 - half)), int(np.ceil(width * (0.5 + half)))
    band = crop[0:y1, max(0, x0) : max(1, x1)]
    if band.size == 0:
        band = crop[0:y1] if y1 > 0 else crop
    return band.reshape(-1, 3).astype(np.float64) / 255.0


def measure_lid_colour(
    crop: np.ndarray, gain: np.ndarray | None = None
) -> tuple[str | None, float]:
    """Name the lid colour of one crop, or admit it is not measurable.

    **PROVISIONAL, and on a shorter leash than the body.** ``docs/12`` P3's lid
    half decides whether this is wired into the service at all, and it is scored
    on wheelies where a lid is actually visible - a bin photographed square-on
    from the front shows none, and this function cannot tell that from a dark
    lid. It returns a colour for the top band it was given either way; deciding
    whether that band *is* a lid is not something a band can do.

    Same contract as :func:`measure_body_colour`: ``(name, delta_e)``, and
    ``None`` when nothing is within :data:`MAX_DELTA_E`. ``None`` propagates to
    a rule that does not match, which is the designed outcome.
    """
    if crop is None or crop.size == 0:
        return None, float("inf")

    sample = lid_sample(crop)
    if gain is not None:
        sample = apply_illuminant(sample, gain)
    lab = srgb_to_lab(sample.mean(axis=0))

    distances = {name: delta_e_2000(lab, ref) for name, ref in named_colours().items()}
    best = min(distances, key=lambda name: distances[name])
    if distances[best] > MAX_DELTA_E:
        return None, distances[best]
    return best, distances[best]


def measurement_note() -> dict[str, Any]:
    """What ``/health`` says about how colour is being measured.

    Published because the method is provisional. Anybody reading a surprising
    colour needs to be able to see which variant produced it without reading the
    source.
    """
    return {
        "method": (
            "illuminant from the whole frame (shades-of-gray p=6), applied to a "
            "centre-weighted sample inside the box, named by CIEDE2000 in CIELAB"
        ),
        "status": (
            "PROVISIONAL - docs/12 probe P3 ran 2026-08-22 against AGENT labels and did not "
            "close. Body agreement 0.5625 against a ~0.75 rule; the shipped variant (4) is "
            "not the best of the four, and recalibrating the taxonomy's hex_ref would take "
            "the body to 0.9125 leave-one-cluster-out. That is a maintainer decision"
        ),
        "max_delta_e": MAX_DELTA_E,
        "centre_fraction": CENTRE_FRACTION,
        "lid_colour": (
            "NOT measured, and now for a measured reason. P3 scored the upper-band sampler at "
            "0.1966 against a 0.60 floor on 117 wheelies whose lids were visible in 98% of "
            "frames - so this is not a cropping or visibility failure. Recalibrated references "
            "reach only 0.5214. The sampler exists (measure_lid_colour) and is deliberately "
            "NOT wired in: the Deggendorf pack matches wheelies on lid_color, and answering it "
            "right one time in five would be worse than answering unknown"
        ),
        "sam": "not used - P3 has not shown a mask is needed",
    }
