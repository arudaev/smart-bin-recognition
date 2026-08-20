"""Tests for the quantisation knobs and the calibration set behind docs/12 P9.

The validator's first trained artefact lost **0.727 mAP** to int8 and could not
ship. Two of the three explanations written down in advance turned out to rest on
a misreading of what the exporter actually does, so the things asserted here are
the things that misled:

- the calibration set was described as "``val``, which is 92 % background". The
  *split* is 91.46 % background; the 200 files ``quantise`` saw were a
  lexicographic prefix - **149 background and 51 positive, with no Open Images
  frame at all** - because tree filenames are ``<pool>__<file>`` and
  ``open_images__`` sorts after ``negatives__``;
- "leave the head in fp32" was nearly implemented as "every node not matching
  ``/model.<i>/``", which on the real graph is not the head.

Neither is a subtle bug. Both would have produced a variant that measured
something other than its own name, and both are cheap to pin.
"""

from __future__ import annotations

import pytest

from sbr.export.onnx_export import (
    DEFAULT_HEAD_PREFIX,
    CalibrationSet,
    QuantSettings,
    calibration_frames,
)

# --------------------------------------------------------------------------- #
# The defaults are what shipped
# --------------------------------------------------------------------------- #


def test_the_defaults_are_the_settings_v1_shipped_with():
    """A knob whose default changed behaviour would silently invalidate the
    0.025 measurement P9 exists to explain."""
    settings = QuantSettings()
    assert settings.activation_type == "u8"      # QuantType.QUInt8
    assert settings.weight_type == "s8"          # QuantType.QInt8
    assert settings.per_channel is True
    assert settings.reduce_range is False
    assert settings.calibrate_method == "minmax"
    assert settings.preprocess is False
    assert settings.calibration_fit == "stretch"
    assert settings.exclude_head is False
    assert settings.departures == ()


def test_the_shipped_format_is_the_one_onnxruntime_warns_about():
    # U8S8 on x86 is the documented saturation case, and S8S8 is the normal CPU
    # choice. That v1 used the warned-about pair is the first thing P9 tests.
    assert QuantSettings().format == "u8s8"
    assert QuantSettings(activation_type="s8").format == "s8s8"


def test_departures_counts_what_a_variant_changed():
    # docs/12 P9's tie-break prefers the simpler configuration when two variants
    # are within noise, so "simpler" has to be countable rather than arguable.
    assert QuantSettings(activation_type="s8").departures == ("activation_type",)
    assert set(QuantSettings(reduce_range=True, per_channel=False).departures) == {
        "reduce_range", "per_channel",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("activation_type", "f32"),
        ("weight_type", "int4"),
        ("calibrate_method", "kl"),
        ("calibration_fit", "crop"),
    ],
)
def test_an_unknown_setting_is_refused_at_construction(field, value):
    # A typo that reached quantize_static would surface as an opaque failure
    # inside onnxruntime, hours into a probe.
    with pytest.raises(ValueError, match=field):
        QuantSettings(**{field: value})


# --------------------------------------------------------------------------- #
# The calibration set
# --------------------------------------------------------------------------- #


def _detection_tree(root, split="val", *, legacy=51, negatives=149, open_images=100):
    """A tree shaped like `build_yolo_tree`'s output, with the real name scheme.

    The proportions are the ones that matter: enough `legacy__` and
    `negatives__` frames to fill 200 before a single `open_images__` frame is
    reached, which is precisely what happened on the pinned dataset.
    """
    from PIL import Image

    images, labels = root / "images" / split, root / "labels" / split
    images.mkdir(parents=True)
    labels.mkdir(parents=True)

    for pool, count, boxed in (
        ("legacy", legacy, True),
        ("negatives", negatives, False),
        ("open_images", open_images, True),
    ):
        for index in range(count):
            name = f"{pool}__{index:05d}"
            Image.new("RGB", (32, 24), (index % 255, 0, 0)).save(images / f"{name}.jpg")
            (labels / f"{name}.txt").write_text(
                "0 0.5 0.5 0.2 0.2\n" if boxed else "", encoding="utf-8"
            )
    return root


def test_first_lexicographic_reproduces_the_sample_v1_actually_used(tmp_path):
    """The historical bug, pinned so P9 can reproduce rather than assert it.

    51 legacy + 149 negatives = 200, and `open_images__` never gets a look in.
    This is the finding that replaced "the calibration set is 92 % background".
    """
    tree = _detection_tree(tmp_path)
    calibration = calibration_frames(tree, "val", 200, strategy="first_lexicographic")

    assert len(calibration.images) == 200
    assert calibration.sources == {"legacy": 51, "negatives": 149}
    assert "open_images" not in calibration.sources
    assert (calibration.positives, calibration.background) == (51, 149)
    assert calibration.as_dict()["background_fraction"] == 0.745


def test_stratified_reaches_every_pool(tmp_path):
    # The whole point of the alternative: the ranges are measured over frames
    # that resemble the ones the model is scored on.
    tree = _detection_tree(tmp_path)
    calibration = calibration_frames(tree, "val", 200, strategy="stratified", seed=42)

    assert len(calibration.images) == 200
    assert set(calibration.sources) == {"legacy", "negatives", "open_images"}
    assert calibration.sources["open_images"] > 0


def test_positive_enriched_is_half_boxes(tmp_path):
    tree = _detection_tree(tmp_path)
    calibration = calibration_frames(tree, "val", 200, strategy="positive_enriched", seed=42)

    assert calibration.positives == 100
    assert calibration.background == 100


def test_a_seed_makes_the_set_reproducible_and_the_hash_stable(tmp_path):
    """The ordered list and its hash are part of any number derived from it.

    Two runs of the same strategy and seed must produce the same fingerprint, or
    a P9 row cannot be re-run against the set that produced it.
    """
    tree = _detection_tree(tmp_path)
    first = calibration_frames(tree, "val", 200, strategy="stratified", seed=42)
    again = calibration_frames(tree, "val", 200, strategy="stratified", seed=42)
    other = calibration_frames(tree, "val", 200, strategy="stratified", seed=7)

    assert first.sha256 == again.sha256
    assert first.sha256 != other.sha256
    assert len(first.sha256) == 64


def test_the_hash_is_order_sensitive(tmp_path):
    # "the same frames in the same order" is the question it answers; a set hash
    # would call two different calibrations identical.
    tree = _detection_tree(tmp_path, legacy=4, negatives=4, open_images=0)
    chosen = calibration_frames(tree, "val", 8, strategy="first_lexicographic")
    reversed_set = CalibrationSet(
        images=tuple(reversed(chosen.images)),
        strategy=chosen.strategy,
        split=chosen.split,
        seed=chosen.seed,
        positives=chosen.positives,
        background=chosen.background,
        sources=chosen.sources,
    )
    assert reversed_set.sha256 != chosen.sha256


def test_a_classification_tree_reports_no_positive_count(tmp_path):
    """The identifier's tree carries no labels, so there is nothing to count.

    Reporting 0 background would be a claim rather than an absence, and this
    module's whole job today is not making claims it cannot support.
    """
    from PIL import Image

    for klass in ("igloo", "wheelie_small"):
        directory = tmp_path / "val" / klass
        directory.mkdir(parents=True)
        for index in range(5):
            Image.new("RGB", (16, 16)).save(directory / f"{klass}__{index}.jpg")

    calibration = calibration_frames(tmp_path, "val", 10, strategy="stratified")
    assert len(calibration.images) == 10
    assert calibration.positives is None
    assert calibration.background is None
    assert calibration.as_dict()["background_fraction"] is None


def test_positive_enrichment_refuses_a_tree_with_no_labels(tmp_path):
    from PIL import Image

    directory = tmp_path / "val" / "igloo"
    directory.mkdir(parents=True)
    Image.new("RGB", (16, 16)).save(directory / "a.jpg")

    with pytest.raises(ValueError, match="carries none"):
        calibration_frames(tmp_path, "val", 2, strategy="positive_enriched")


def test_an_unknown_strategy_is_refused(tmp_path):
    tree = _detection_tree(tmp_path, legacy=2, negatives=2, open_images=2)
    with pytest.raises(ValueError, match="unknown calibration strategy"):
        calibration_frames(tree, "val", 2, strategy="random")


# --------------------------------------------------------------------------- #
# The head boundary - looked at, never assumed
# --------------------------------------------------------------------------- #

onnx = pytest.importorskip("onnx", reason="the export extra is not installed")


def _graph(*node_names):
    """A minimal ONNX graph whose node names are the only thing under test."""
    from onnx import TensorProto, helper

    nodes = [
        helper.make_node("Relu", ["x"], [f"y{index}"], name=name)
        for index, name in enumerate(node_names)
    ]
    graph = helper.make_graph(
        nodes,
        "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
        [helper.make_tensor_value_info("y0", TensorProto.FLOAT, [1])],
    )
    return helper.make_model(graph)


def test_the_head_is_found_by_the_prefix_it_is_given(tmp_path):
    from sbr.export.onnx_export import head_node_names

    path = tmp_path / "m.onnx"
    onnx.save(
        _graph(
            "/model.9/conv/Conv",
            "/model.23/cv2.0/cv2.0.0/conv/Conv",
            "/model.23/cv3.1/Sigmoid",
            "/Concat_4",
        ),
        str(path),
    )
    assert head_node_names(path, DEFAULT_HEAD_PREFIX) == [
        "/model.23/cv2.0/cv2.0.0/conv/Conv",
        "/model.23/cv3.1/Sigmoid",
    ]


def test_an_unmatched_head_prefix_raises_rather_than_excluding_nothing(tmp_path):
    """The failure mode this replaces: `exclude_head=True` quietly quantising the
    whole graph and the row still being labelled "head in fp32".

    An earlier draft inferred the head as "every node not matching
    `/model.<i>/`", which on the real v1 graph is a large set of generated nodes
    that are not the head at all.
    """
    from sbr.export.onnx_export import head_node_names

    path = tmp_path / "m.onnx"
    onnx.save(_graph("/model.9/conv/Conv", "/model.16/Add", "/Concat_4"), str(path))

    with pytest.raises(ValueError, match="would have quantised everything"):
        head_node_names(path, "/model.23/")
