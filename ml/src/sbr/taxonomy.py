"""Canonical waste-stream taxonomy and region packs.

The taxonomy is the spine of the product: the detector produces observations
(form factor + measured colour), and the taxonomy plus a region pack turns an
observation into an answer. See ``docs/02-waste-taxonomy.md``.

This module is the Python side. A parallel TypeScript implementation of the
*resolver* lives in ``web/src/domain/`` – the two must agree, which is why the
resolution rules are specified in the docs rather than in either codebase.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

# Repo root is four levels up: ml/src/sbr/taxonomy.py -> ml/src/sbr -> ml/src -> ml -> repo
REPO_ROOT = Path(__file__).resolve().parents[3]
TAXONOMY_DIR = REPO_ROOT / "data" / "taxonomy"
TAXONOMY_PATH = TAXONOMY_DIR / "waste-streams.json"
REGIONS_DIR = TAXONOMY_DIR / "regions"

UNKNOWN_STREAM = "unknown"


class TaxonomyError(ValueError):
    """Raised when taxonomy or region-pack data is internally inconsistent."""


@dataclass(frozen=True)
class Stream:
    """A canonical, jurisdiction-independent waste stream."""

    id: str
    family: str
    i18n_key: str
    icon: str
    typical_colors: tuple[str, ...]
    accepted: tuple[str, ...]
    rejected: tuple[str, ...]
    common_mistakes: tuple[str, ...] = ()
    confusable_with: tuple[str, ...] = ()
    note_key: str | None = None


@dataclass(frozen=True)
class FormFactor:
    """A physical bin shape. These are the detector's classes."""

    id: str
    i18n_key: str
    capacity_l: tuple[float, float] | None = None
    note: str = ""


@dataclass(frozen=True)
class Taxonomy:
    """The full canonical ontology."""

    version: str
    updated: str
    streams: dict[str, Stream]
    form_factors: dict[str, FormFactor]
    colors: tuple[str, ...]
    families: tuple[str, ...]
    items: frozenset[str]

    @property
    def detector_classes(self) -> list[str]:
        """Form-factor ids in a stable order – the detector's class list.

        Order is the file order, and it is load-bearing: it becomes the class
        index in the YOLO dataset and in the exported ONNX sidecar. Never
        reorder without retraining.
        """
        return list(self.form_factors)

    def stream(self, stream_id: str) -> Stream:
        try:
            return self.streams[stream_id]
        except KeyError:
            raise TaxonomyError(f"unknown stream id: {stream_id!r}") from None

    def validate(self) -> list[str]:
        """Return a list of referential-integrity problems. Empty means valid."""
        problems: list[str] = []
        families = set(self.families)
        colors = set(self.colors)

        for sid, stream in self.streams.items():
            if stream.family not in families:
                problems.append(f"stream {sid!r}: unknown family {stream.family!r}")

            for color in stream.typical_colors:
                if color not in colors:
                    problems.append(f"stream {sid!r}: unknown colour {color!r}")

            for other in stream.confusable_with:
                if other not in self.streams:
                    problems.append(f"stream {sid!r}: confusable_with unknown stream {other!r}")

            for field_name in ("accepted", "rejected", "common_mistakes"):
                for item in getattr(stream, field_name):
                    if item not in self.items:
                        problems.append(
                            f"stream {sid!r}: {field_name} references item {item!r} "
                            "which is not in the closed vocabulary"
                        )

            # common_mistakes must be a subset of rejected – they are the
            # rejected items worth surfacing prominently, not a separate idea.
            stray = set(stream.common_mistakes) - set(stream.rejected)
            if stray:
                problems.append(
                    f"stream {sid!r}: common_mistakes not in rejected: {sorted(stray)}"
                )

        if UNKNOWN_STREAM not in self.streams:
            problems.append(f"taxonomy must define the {UNKNOWN_STREAM!r} stream")

        return problems


@dataclass(frozen=True)
class Rule:
    """One appearance-to-stream mapping within a region."""

    id: str
    match: dict[str, list[str]]
    stream: str
    confidence: float
    local_name: str | None = None
    requires_disambiguation: bool = False
    disambiguation: dict[str, Any] | None = None

    @property
    def specificity(self) -> int:
        """How many constraints this rule imposes. More specific rules win."""
        return len(self.match)

    def matches(self, observation: Observation) -> bool:
        """True when every constraint is satisfied by the observation.

        An observation attribute of ``None`` (not measured) never satisfies a
        constraint – we do not guess on missing evidence.
        """
        for attribute, allowed in self.match.items():
            value = getattr(observation, attribute, None)
            if value is None or value not in allowed:
                return False
        return True


@dataclass(frozen=True)
class Observation:
    """What the device saw: one detected bin, before interpretation."""

    form_factor: str
    body_color: str | None = None
    lid_color: str | None = None
    aperture_color: str | None = None
    text_hint: str | None = None


@dataclass(frozen=True)
class Resolution:
    """What an observation means in a given region."""

    stream: str
    confidence: float
    local_name: str | None = None
    rule_id: str | None = None
    requires_disambiguation: bool = False
    disambiguation: dict[str, Any] | None = None

    @property
    def is_known(self) -> bool:
        return self.stream != UNKNOWN_STREAM


UNRESOLVED = Resolution(stream=UNKNOWN_STREAM, confidence=0.0)


@dataclass(frozen=True)
class RegionPack:
    """Maps observable appearance onto canonical streams for one jurisdiction."""

    region_id: str
    pack_version: str
    taxonomy_version: str
    status: str
    name: str
    country: str
    rules: tuple[Rule, ...]
    local_names: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    sources: tuple[dict[str, Any], ...] = ()

    @property
    def is_publishable(self) -> bool:
        """A pack may only be served to users if every source is traceable.

        This is the guardrail against the product's worst failure mode: telling
        someone confidently that the wrong thing goes in the wrong bin. See
        ``docs/02-waste-taxonomy.md`` § 4.
        """
        if not self.sources:
            return False
        return all(s.get("url") and s.get("retrieved") for s in self.sources)

    def resolve(self, observation: Observation) -> Resolution:
        """Resolve an observation to a stream. Pure and deterministic.

        Most-specific rule wins; ties broken by confidence, then by file order.
        """
        candidates = [
            (rule, index)
            for index, rule in enumerate(self.rules)
            if rule.matches(observation)
        ]
        if not candidates:
            return UNRESOLVED

        rule, _ = min(
            candidates,
            key=lambda pair: (-pair[0].specificity, -pair[0].confidence, pair[1]),
        )
        return Resolution(
            stream=rule.stream,
            confidence=rule.confidence,
            local_name=rule.local_name or self.local_names.get(rule.stream),
            rule_id=rule.id,
            requires_disambiguation=rule.requires_disambiguation,
            disambiguation=rule.disambiguation,
        )

    def validate(self, taxonomy: Taxonomy) -> list[str]:
        """Return referential-integrity problems against the given taxonomy."""
        problems: list[str] = []
        colors = set(taxonomy.colors)
        forms = set(taxonomy.form_factors)
        seen_ids: set[str] = set()

        pack_major = self.taxonomy_version.split(".")[0]
        tax_major = taxonomy.version.split(".")[0]
        if pack_major != tax_major:
            problems.append(
                f"pack {self.region_id!r}: taxonomy major version mismatch "
                f"(pack {self.taxonomy_version}, taxonomy {taxonomy.version})"
            )

        for rule in self.rules:
            if rule.id in seen_ids:
                problems.append(f"pack {self.region_id!r}: duplicate rule id {rule.id!r}")
            seen_ids.add(rule.id)

            if rule.stream not in taxonomy.streams:
                problems.append(f"rule {rule.id!r}: unknown stream {rule.stream!r}")

            for attribute, allowed in rule.match.items():
                vocabulary = forms if attribute == "form_factor" else colors
                if attribute == "text_hint":
                    continue  # free tokens by design
                for value in allowed:
                    if value not in vocabulary:
                        problems.append(
                            f"rule {rule.id!r}: unknown {attribute} value {value!r}"
                        )

            if rule.requires_disambiguation and not rule.disambiguation:
                problems.append(
                    f"rule {rule.id!r}: requires_disambiguation set without options"
                )

        for stream_id in {**self.local_names, **self.overrides}:
            if stream_id not in taxonomy.streams:
                problems.append(f"pack {self.region_id!r}: unknown stream {stream_id!r}")

        if self.status == "published" and not self.is_publishable:
            problems.append(
                f"pack {self.region_id!r}: status is 'published' but at least one "
                "source lacks a url or retrieval date"
            )

        return problems


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def _tuple(raw: Any) -> tuple[str, ...]:
    return tuple(raw or ())


@lru_cache(maxsize=1)
def load_taxonomy(path: Path | None = None) -> Taxonomy:
    """Load and cache the canonical taxonomy."""
    path = path or TAXONOMY_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))

    streams = {
        entry["id"]: Stream(
            id=entry["id"],
            family=entry["family"],
            i18n_key=entry["i18n_key"],
            icon=entry["icon"],
            typical_colors=_tuple(entry.get("typical_colors")),
            accepted=_tuple(entry.get("accepted")),
            rejected=_tuple(entry.get("rejected")),
            common_mistakes=_tuple(entry.get("common_mistakes")),
            confusable_with=_tuple(entry.get("confusable_with")),
            note_key=entry.get("note_key"),
        )
        for entry in raw["streams"]
    }

    form_factors = {
        entry["id"]: FormFactor(
            id=entry["id"],
            i18n_key=entry["i18n_key"],
            capacity_l=tuple(entry["capacity_l"]) if entry.get("capacity_l") else None,
            note=entry.get("note", ""),
        )
        for entry in raw["form_factors"]
    }

    return Taxonomy(
        version=raw["version"],
        updated=raw["updated"],
        streams=streams,
        form_factors=form_factors,
        colors=tuple(c["id"] for c in raw["colors"]),
        families=tuple(f["id"] for f in raw["families"]),
        items=frozenset(raw["items"]),
    )


def load_region_pack(region_id: str, directory: Path | None = None) -> RegionPack:
    """Load one region pack by id."""
    directory = directory or REGIONS_DIR
    path = directory / f"{region_id}.json"
    if not path.exists():
        raise TaxonomyError(f"no region pack for {region_id!r} at {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    rules = tuple(
        Rule(
            id=entry["id"],
            match=entry["match"],
            stream=entry["stream"],
            confidence=float(entry["confidence"]),
            local_name=entry.get("local_name"),
            requires_disambiguation=bool(entry.get("requires_disambiguation", False)),
            disambiguation=entry.get("disambiguation"),
        )
        for entry in raw["rules"]
    )

    return RegionPack(
        region_id=raw["region_id"],
        pack_version=raw["pack_version"],
        taxonomy_version=raw["taxonomy_version"],
        status=raw["status"],
        name=raw["name"],
        country=raw["country"],
        rules=rules,
        local_names=raw.get("local_names", {}),
        overrides=raw.get("overrides", {}),
        sources=tuple(raw.get("sources", ())),
    )


def load_all_region_packs(directory: Path | None = None) -> dict[str, RegionPack]:
    """Load every region pack on disk, keyed by region id."""
    directory = directory or REGIONS_DIR
    return {
        path.stem: load_region_pack(path.stem, directory)
        for path in sorted(directory.glob("*.json"))
    }
