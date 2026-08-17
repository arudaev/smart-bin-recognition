"""Tests for the taxonomy and the region-pack resolver.

The resolver is the piece most likely to be quietly wrong and most cheaply
tested, so it is tested here in Python and mirrored in TypeScript in
``web/src/domain/``. Both must agree; the docs are the specification.
"""

from __future__ import annotations

import pytest

from sbr.taxonomy import (
    UNKNOWN_STREAM,
    Observation,
    RegionPack,
    Rule,
    load_all_region_packs,
    load_region_pack,
    load_taxonomy,
    region_for_geohash,
)

# --------------------------------------------------------------------------- #
# Canonical taxonomy
# --------------------------------------------------------------------------- #


def test_taxonomy_is_internally_consistent():
    assert load_taxonomy().validate() == []


def test_unknown_is_a_real_stream():
    # 'unknown' is a designed product state, not an error path.
    assert UNKNOWN_STREAM in load_taxonomy().streams


def test_every_referenced_item_is_in_the_closed_vocabulary():
    # This closure is what bounds translation cost. See docs/06-i18n.md § 4.
    taxonomy = load_taxonomy()
    for stream in taxonomy.streams.values():
        for field in (stream.accepted, stream.rejected, stream.common_mistakes):
            assert set(field) <= taxonomy.items, stream.id


def test_detector_classes_are_form_factors_not_streams():
    # The whole portability argument rests on this. If a stream id ever appears
    # in the detector's class list, the model has learnt a jurisdiction.
    taxonomy = load_taxonomy()
    assert set(taxonomy.detector_classes).isdisjoint(taxonomy.streams)


def test_detector_class_order_is_stable():
    # Class order is the ONNX class index. Reordering silently invalidates every
    # deployed model, so it is pinned here.
    assert load_taxonomy().detector_classes[:4] == [
        "wheelie_small",
        "wheelie_large",
        "igloo",
        "underground",
    ]


# --------------------------------------------------------------------------- #
# Region packs
# --------------------------------------------------------------------------- #


def test_all_shipped_packs_validate():
    taxonomy = load_taxonomy()
    for region_id, pack in load_all_region_packs().items():
        assert pack.validate(taxonomy) == [], region_id


def test_deggendorf_pack_is_still_draft():
    """The rules were transcribed from the predecessor's four hard-coded classes,
    not verified against ZAW Donau-Wald, so this must not be served.

    ``status`` is what enforces that, and it is the only thing that does.

    This test used to assert ``not pack.is_publishable`` as well, and passed for
    the wrong reason: one source carried ``"retrieved": null``, so the SOURCING
    bar happened to be unmet. Those are two different properties. The 2026-08-16
    verification pass attached a real URL and retrieval date to every source -
    which is strictly an improvement, and which flipped ``is_publishable`` to
    true - while the rules themselves got *less* trustworthy, because the
    operator's own page contradicts both packaging rules.

    So the assertion is on the property that actually protects a user. A pack can
    be perfectly sourced and still wrong, and this one currently is.
    """
    pack = load_region_pack("de-by-deggendorf")
    assert pack.status == "draft"


def test_deggendorf_sources_are_all_traceable():
    # Every source carries a URL and a retrieval date, which is what
    # is_publishable means and all it means.
    pack = load_region_pack("de-by-deggendorf")
    assert pack.is_publishable
    assert len(pack.sources) >= 4
    for source in pack.sources:
        assert source["url"].startswith("https://"), source
        assert source["retrieved"] == "2026-08-16", source
        # Nobody has signed off on the rules themselves yet, and until somebody
        # has, this pack has no business leaving draft.
        assert source["verified_by"] is None, source


def test_the_contradicted_packaging_rules_are_recorded_as_such():
    """The 2026-08-16 pass found the operator routes packaging to a
    Wertstoffinsel, not to the Gelber Sack these two rules assert.

    They are left in the pack because deleting a disposal rule is the
    maintainer's call. What must not happen is the finding being lost: a
    contradicted rule sitting quietly at confidence 0.95 is precisely the
    product's worst failure mode with a citation stapled to it.
    """
    # Read the document rather than the loaded pack: `notes` is provenance for a
    # human and is deliberately not a RegionPack field, because nothing about
    # resolution may depend on it.
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "data" / "taxonomy" / "regions" / "de-by-deggendorf.json"
    )
    notes = " ".join(json.loads(path.read_text(encoding="utf-8"))["notes"])

    assert "CONTRADICTED" in notes
    for rule_id in ("deg-packaging-sack", "deg-packaging-wheelie"):
        assert rule_id in notes, f"{rule_id} is disputed but the pack does not say so"
    assert "Wertstoffinsel" in notes


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #


@pytest.fixture
def deggendorf() -> RegionPack:
    return load_region_pack("de-by-deggendorf")


def test_blue_lid_wheelie_resolves_to_paper(deggendorf):
    resolution = deggendorf.resolve(
        Observation(form_factor="wheelie_small", lid_color="blue")
    )
    assert resolution.stream == "paper"
    assert resolution.local_name == "Papier / Papiertonne"
    assert resolution.is_known


def test_brown_lid_wheelie_resolves_to_bio(deggendorf):
    assert deggendorf.resolve(
        Observation(form_factor="wheelie_large", lid_color="brown")
    ).stream == "bio"


def test_unmeasured_colour_does_not_resolve(deggendorf):
    # We do not guess on missing evidence: a wheelie bin whose lid colour was
    # not measured is unknown, not "probably residual".
    assert deggendorf.resolve(Observation(form_factor="wheelie_small")).stream == UNKNOWN_STREAM


def test_unknown_form_factor_is_unresolved(deggendorf):
    assert deggendorf.resolve(
        Observation(form_factor="wall_unit", body_color="red")
    ).stream == UNKNOWN_STREAM


def test_more_specific_rule_wins(deggendorf):
    # The generic igloo rule matches on form_factor alone; the green rule also
    # constrains body_color and must therefore win.
    generic = deggendorf.resolve(Observation(form_factor="igloo"))
    specific = deggendorf.resolve(Observation(form_factor="igloo", body_color="green"))

    assert generic.stream == "glass_mixed"
    assert generic.requires_disambiguation
    assert specific.stream == "glass_green"
    assert not specific.requires_disambiguation
    assert specific.confidence > generic.confidence


def test_ambiguous_glass_bank_asks_instead_of_asserting(deggendorf):
    # The predecessor's deck names glass as its hardest case. Rather than guess,
    # a low-confidence generic match must surface a disambiguation prompt.
    resolution = deggendorf.resolve(Observation(form_factor="igloo"))
    assert resolution.requires_disambiguation
    assert set(resolution.disambiguation["options"]) == {
        "glass_clear",
        "glass_green",
        "glass_brown",
    }


def test_resolution_is_deterministic(deggendorf):
    observation = Observation(form_factor="wheelie_small", lid_color="blue")
    results = {deggendorf.resolve(observation) for _ in range(20)}
    assert len(results) == 1


def test_tie_break_prefers_higher_confidence():
    pack = RegionPack(
        region_id="test",
        pack_version="1.0.0",
        taxonomy_version="1.0.0",
        status="draft",
        name="Test",
        country="DE",
        rules=(
            Rule(id="low", match={"form_factor": ["igloo"]}, stream="glass_clear", confidence=0.4),
            Rule(id="high", match={"form_factor": ["igloo"]}, stream="glass_green", confidence=0.9),
        ),
    )
    assert pack.resolve(Observation(form_factor="igloo")).rule_id == "high"


# --------------------------------------------------------------------------- #
# Which jurisdiction a frame is in
# --------------------------------------------------------------------------- #


def _pack(region_id: str, tiles: tuple[str, ...]) -> RegionPack:
    return RegionPack(
        region_id=region_id,
        pack_version="1.0.0",
        taxonomy_version="1.0.0",
        status="draft",
        name=region_id,
        country="DE",
        rules=(),
        geohash_tiles=tiles,
    )


def test_the_pack_loader_reads_the_tiles_it_is_selected_by():
    # geohash_tiles is in the schema and in the Deggendorf pack, and the loader
    # dropped it - so the reference implementation could not answer the one
    # question the inference service has to ask on every frame.
    pack = load_region_pack("de-by-deggendorf")
    assert pack.geohash_tiles == ("u2853", "u2856")
    assert pack.bbox == (12.885, 48.79, 13.035, 48.885)


def test_a_geohash_inside_the_coverage_finds_the_pack():
    packs = load_all_region_packs()
    found = region_for_geohash("u2853x", packs)
    assert found is not None and found.region_id == "de-by-deggendorf"


def test_a_geohash_outside_every_pack_is_none_not_a_guess():
    # The whole guardrail in one assertion. Most of the world has no pack, and
    # the answer there is `unknown` - never a neighbouring pack's rules and never
    # the taxonomy's typical colours.
    assert region_for_geohash("u1q0rz", load_all_region_packs()) is None


@pytest.mark.parametrize("geohash", [None, "", "u28", "u2"])
def test_a_geohash_too_coarse_to_pick_a_jurisdiction_is_none(geohash):
    # Tiles are precision 5. Anything shorter cannot identify a jurisdiction, and
    # matching on a shorter prefix would hand one city's rules to a whole region.
    assert region_for_geohash(geohash, load_all_region_packs()) is None


def test_the_more_specific_pack_wins_where_two_overlap():
    # A city pack inside a state pack must answer for the city.
    packs = {
        "state": _pack("state", ("u2853", "u2856", "u2857", "u2858")),
        "city": _pack("city", ("u2853",)),
    }
    found = region_for_geohash("u2853x", packs)
    assert found is not None and found.region_id == "city"


def test_pack_selection_is_case_insensitive():
    # Geohash alphabets are lower case, but a client that upper-cased one should
    # get its own town's rules rather than silently none.
    packs = load_all_region_packs()
    assert region_for_geohash("U2853X", packs) is region_for_geohash("u2853x", packs)
