"""The pipeline, against a stub session.

What is checked is the shape discipline and the decisions - how many calls at
what batch, which crops get taken, what happens when there is no pack, what
happens when there is no identifier. A real ONNX graph would make these slower to
run and no more convincing; decoding a real graph's output is what the end-to-end
run against the container is for.
"""

from __future__ import annotations

import numpy as np
import pytest

from artefacts import Artefact
from conftest import FakeSession, sidecar
from pipeline import Box, Pipeline, crop_for, decode_detections, decode_jpeg, letterbox, softmax
from settings import Settings
from wire import DetectRequest

FORM_FACTORS = ["wheelie_small", "wheelie_large", "igloo"]

#: The real identifier.yaml values, except min_box_px: the fixture frame is
#: 320x240 and its synthetic boxes are ~48 px, so the shipped 64 would filter
#: every one of them and quietly turn these into tests of nothing.
CONFIG = {
    "data": {"crops": {"padding": 0.12, "min_box_px": 8}},
    "inference": {"unknown_threshold": 0.55},
}


def artefact(role: str, outputs=None, **kwargs) -> Artefact:
    return Artefact(
        role=role,
        session=FakeSession(outputs),
        sidecar=sidecar(role, **kwargs),
        source="test",
    )


def one_box_head(boxes: int = 1, size: int = 448):
    """A validator head emitting `boxes` confident detections."""

    def outputs(_array):
        anchors = max(boxes, 1)
        raw = np.zeros((1, 5, anchors), dtype=np.float32)
        for i in range(boxes):
            raw[0, 0, i] = size * (0.2 + 0.1 * i)   # cx
            raw[0, 1, i] = size * 0.5               # cy
            raw[0, 2, i] = size * 0.15              # w
            raw[0, 3, i] = size * 0.4               # h
            raw[0, 4, i] = 0.95                     # score
        return raw

    return outputs


def classifier_head(classes: int = 3, confidence: float = 0.9):
    def outputs(array):
        batch = array.shape[0]
        raw = np.full((batch, classes), (1 - confidence) / (classes - 1), dtype=np.float32)
        raw[:, 0] = confidence
        return raw

    return outputs


def pipeline(*, boxes=1, identifier=True, confidence=0.9, **settings_kwargs) -> Pipeline:
    return Pipeline(
        artefact("validator", one_box_head(boxes)),
        artefact("identifier", classifier_head(confidence=confidence), classes=FORM_FACTORS)
        if identifier
        else None,
        Settings(**settings_kwargs),
        CONFIG,
    )


# --------------------------------------------------------------------------- #
# Pre-processing
# --------------------------------------------------------------------------- #


def test_letterbox_preserves_aspect_ratio():
    # A stretched bin is a differently-shaped object, and shape is the entire
    # content of the form-factor classes.
    frame = np.zeros((240, 480, 3), dtype=np.uint8)
    image, scale, (pad_x, pad_y) = letterbox(frame, 448)
    assert image.shape == (448, 448, 3)
    assert scale == pytest.approx(448 / 480)
    assert pad_y > 0 and pad_x == 0


def test_decode_jpeg_rejects_anything_undecodable():
    with pytest.raises(ValueError, match="not a decodable image"):
        decode_jpeg(b"this is not a jpeg")


def test_decode_jpeg_reads_a_real_frame(jpeg):
    frame = decode_jpeg(jpeg)
    assert frame.shape == (240, 320, 3)
    assert frame.dtype == np.uint8


def test_softmax_leaves_an_already_normalised_head_alone():
    # Ultralytics classify heads emit probabilities. Applying softmax to a
    # probability vector flattens it and would push everything under the unknown
    # threshold - so the whole model would answer "I don't know", always.
    probabilities = np.array([[0.9, 0.05, 0.05]], dtype=np.float32)
    assert np.allclose(softmax(probabilities), probabilities)


def test_softmax_normalises_raw_logits():
    rows = softmax(np.array([[4.0, 1.0, -2.0]], dtype=np.float32))
    assert rows.sum() == pytest.approx(1.0)
    assert rows[0, 0] > rows[0, 1] > rows[0, 2]


def test_crops_are_padded_and_clipped_to_the_frame():
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    # A box flush against the edge: padding must not wrap or go negative.
    crop = crop_for(frame, Box(0, 0, 40, 40, 0.9), padding=0.5)
    assert crop.shape[0] > 0 and crop.shape[1] > 0


def test_nms_collapses_duplicate_boxes():
    raw = np.zeros((1, 5, 2), dtype=np.float32)
    for i in range(2):
        raw[0, :, i] = [100, 100, 50, 50, 0.9]      # the same box twice
    boxes = decode_detections(raw, 1.0, (0, 0), (448, 448), 0.35, 0.45, channels=5)
    assert len(boxes) == 1


def test_a_head_of_an_unexpected_shape_raises_rather_than_transposing_garbage():
    # A transposed head produces plausible boxes in the wrong places, which is a
    # far worse failure than an exception.
    with pytest.raises(ValueError, match="no axis of"):
        decode_detections(
            np.zeros((1, 7, 3), dtype=np.float32), 1.0, (0, 0), (448, 448), 0.35, 0.45, channels=5
        )


# --------------------------------------------------------------------------- #
# The crop batch - a service requirement, not an optimisation
# --------------------------------------------------------------------------- #


def test_crops_go_through_the_identifier_in_one_call(jpeg):
    engine = pipeline(boxes=6)
    engine.run(DetectRequest(seq=1), jpeg)

    calls = engine.identifier.session.calls
    assert len(calls) == 1
    assert calls[0][0] == 6


def test_a_static_graph_falls_back_to_sequential_and_says_so(jpeg, caplog):
    """The fallback exists, and it is loud.

    A graph exported with a fixed batch of one loads and serves perfectly well;
    without the warning the service would simply cost three times what docs/05
    § 3 prices at six bins, and nothing would say why.
    """
    engine = Pipeline(
        artefact("validator", one_box_head(3)),
        artefact("identifier", classifier_head(), classes=FORM_FACTORS, dynamic_batch=False),
        Settings(),
        CONFIG,
    )
    assert engine.batching is False
    assert any("SEQUENTIALLY" in record.message for record in caplog.records)

    engine.run(DetectRequest(seq=1), jpeg)
    assert len(engine.identifier.session.calls) == 3
    assert all(shape[0] == 1 for shape in engine.identifier.session.calls)


def test_crops_are_capped_so_one_frame_cannot_cost_unboundedly(jpeg):
    # docs/05 § 3 names capping crops per frame as one of the two cheap ways to
    # move the concurrency ceiling.
    engine = pipeline(boxes=12, max_crops=4)
    engine.run(DetectRequest(seq=1), jpeg)
    assert engine.identifier.session.calls[0][0] == 4


def test_a_box_over_the_cap_is_still_reported(jpeg):
    """Reported, not dropped. A bin the user can see must appear on screen even
    if the service declined to spend 25 ms identifying it."""
    engine = pipeline(boxes=8, max_crops=3)
    response = engine.run(DetectRequest(seq=1), jpeg)

    assert len(response.detections) == 8
    assert sum(1 for d in response.detections if d.form_factor) == 3
    assert all(d.form_factor is None for d in response.detections[3:])


# --------------------------------------------------------------------------- #
# The guardrail
# --------------------------------------------------------------------------- #


def test_no_pack_means_no_stream(jpeg):
    """The product's worst failure, in one assertion.

    Most of the world has no region pack. The answer there is `unknown`, which is
    a designed state with a UI - never a neighbouring city's rules and never the
    taxonomy's typical colours.
    """
    engine = pipeline()
    response = engine.run(DetectRequest(seq=1, geohash6="u1q0rz"), jpeg)

    assert response.region_id is None
    assert all(d.stream is None for d in response.detections)


def test_a_pack_that_covers_the_frame_resolves(jpeg):
    engine = pipeline()
    response = engine.run(DetectRequest(seq=1, geohash6="u2853x"), jpeg)

    assert response.region_id == "de-by-deggendorf"
    # The pack is genuinely status: draft, and the wire says so, so a client that
    # did not bundle the pack still cannot present this as authoritative.
    assert response.pack_status == "draft"


def test_the_resolver_is_the_one_from_sbr(jpeg):
    # Not re-implemented here. A third copy of the rules deciding what may be
    # thrown where is the worst possible place for drift.
    import pipeline as module

    source = (module.__file__ or "").replace("\\", "/")
    text = open(source, encoding="utf-8").read()
    assert "from sbr.taxonomy import" in text


# --------------------------------------------------------------------------- #
# No identifier - the state this project is actually in today
# --------------------------------------------------------------------------- #


def test_without_an_identifier_the_service_still_says_where(jpeg):
    engine = pipeline(identifier=False)
    response = engine.run(DetectRequest(seq=1, geohash6="u2853x"), jpeg)

    assert len(response.detections) == 1
    assert response.detections[0].validator_conf > 0.9
    assert response.detections[0].form_factor is None
    assert response.detections[0].stream is None


def test_a_missing_identifier_is_not_reported_as_novelty(jpeg):
    """`unknown_type` means the identifier was asked and declined.

    No identifier at all is not a disagreement. Reporting it as one would fill
    the collection queue with frames that prove nothing about anything.
    """
    engine = pipeline(identifier=False)
    response = engine.run(DetectRequest(seq=1, geohash6="u2853x"), jpeg)
    assert response.detections[0].novelty == "none"


def test_an_identifier_that_declines_is_novelty(jpeg):
    engine = pipeline(confidence=0.3)   # under the 0.55 unknown threshold
    response = engine.run(DetectRequest(seq=1, geohash6="u2853x"), jpeg)

    assert response.detections[0].form_factor is None
    assert response.detections[0].novelty == "unknown_type"


def test_an_uncovered_location_is_novelty_regardless_of_confidence(jpeg):
    engine = pipeline(confidence=0.99)
    response = engine.run(DetectRequest(seq=1, geohash6="u1q0rz"), jpeg)
    assert response.detections[0].novelty == "new_region"


# --------------------------------------------------------------------------- #
# Privacy
# --------------------------------------------------------------------------- #


def test_running_a_frame_writes_nothing_to_disk(jpeg, tmp_path, monkeypatch):
    """docs/03 § 4: frames are processed in memory and discarded.

    The consent lifecycle is not built, so there is nothing that could make
    retention lawful here - and a service that retained "just until the flow
    exists" is exactly what that paragraph was written to prevent.
    """
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))

    pipeline().run(DetectRequest(seq=1, geohash6="u2853x"), jpeg)

    assert set(tmp_path.rglob("*")) == before


def test_the_lid_colour_is_not_guessed(jpeg):
    # Lid/body separation is unsolved by any method in research/06 and is
    # explicitly out of scope for P3. None, not a guess.
    response = pipeline().run(DetectRequest(seq=1, geohash6="u2853x"), jpeg)
    assert all(d.lid_color is None for d in response.detections)
