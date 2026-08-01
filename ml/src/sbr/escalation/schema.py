"""Contract for stage-3 VLM escalation.

Escalation is the **only** paid path in the system, so its contract is narrow on
purpose:

* The response must be strict JSON over the canonical vocabulary. Free-text
  disposal advice is rejected at parse time – a model must not invent rules.
* A municipal source citation is mandatory. If the model cannot point at the
  jurisdiction's own published guidance, the answer is not usable.
* The output never reaches a user as fact. It becomes a ``pending`` registry
  entry and a labelled-data candidate, both of which pass through moderation.

The runtime handler lives in ``web/api/escalate.ts``; this module is the
authority on the shape, and the place to change it.

See ``docs/04-ml-pipeline.md`` § 6 and ``docs/03-registry-geo-trust.md`` § 6.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sbr.taxonomy import Taxonomy, load_taxonomy

#: Coarse enough to pick a jurisdiction, not a household. ~1.2 km cells.
ESCALATION_GEOHASH_PRECISION = 6

#: Uploaded stills are downscaled on-device before they ever leave the phone.
MAX_IMAGE_EDGE_PX = 512


class EscalationRejectedError(ValueError):
    """The model's response did not satisfy the contract."""


@dataclass(frozen=True)
class EscalationRequest:
    """What the device sends. Deliberately minimal."""

    image_b64: str
    geohash6: str
    form_factor_guess: str | None = None
    body_color: str | None = None
    lid_color: str | None = None
    region_id: str | None = None
    locale: str = "en"

    def redacted(self) -> dict[str, Any]:
        """Loggable form – never log the image."""
        return {
            "geohash6": self.geohash6,
            "form_factor_guess": self.form_factor_guess,
            "body_color": self.body_color,
            "lid_color": self.lid_color,
            "region_id": self.region_id,
            "image_bytes": len(self.image_b64),
        }


@dataclass(frozen=True)
class Citation:
    """Provenance. Without this the response is worthless to us."""

    title: str
    url: str
    quote: str | None = None


@dataclass(frozen=True)
class EscalationResponse:
    """What the model must return, after validation."""

    stream: str
    confidence: float
    form_factor: str
    local_name: str | None
    citations: tuple[Citation, ...]
    reasoning: str = ""
    accepted_add: tuple[str, ...] = field(default_factory=tuple)
    rejected_add: tuple[str, ...] = field(default_factory=tuple)


RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["stream", "confidence", "form_factor", "citations"],
    "additionalProperties": False,
    "properties": {
        "stream": {"type": "string", "description": "One canonical stream id."},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "form_factor": {"type": "string"},
        "local_name": {"type": ["string", "null"]},
        "reasoning": {"type": "string", "maxLength": 500},
        "accepted_add": {"type": "array", "items": {"type": "string"}},
        "rejected_add": {"type": "array", "items": {"type": "string"}},
        "citations": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["title", "url"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "quote": {"type": ["string", "null"]},
                },
            },
        },
    },
}


PROMPT_TEMPLATE = """\
You are identifying a waste container from a photograph so that a public-good \
app can tell residents what may be disposed of in it.

Location: geohash {geohash6} (approximately {region}).
On-device measurements – form factor guess: {form_factor_guess}; \
body colour: {body_color}; lid colour: {lid_color}.

Return ONLY JSON matching this schema:
{schema}

Hard rules:
- `stream` MUST be one of: {streams}
- `form_factor` MUST be one of: {form_factors}
- `accepted_add` / `rejected_add` MUST use only these item ids: {items}
- `citations` MUST reference the responsible municipality's or waste \
operator's own published guidance for THIS location. If you cannot identify \
such a source, return `stream` = "unknown" with confidence 0.
- Do not invent disposal rules. Do not write advice in prose. If the photograph \
is ambiguous, say so with a low confidence rather than guessing.
"""


def build_prompt(request: EscalationRequest, taxonomy: Taxonomy | None = None) -> str:
    """Render the escalation prompt for a request."""
    taxonomy = taxonomy or load_taxonomy()
    return PROMPT_TEMPLATE.format(
        geohash6=request.geohash6,
        region=request.region_id or "unknown region",
        form_factor_guess=request.form_factor_guess or "none",
        body_color=request.body_color or "not measured",
        lid_color=request.lid_color or "not measured",
        schema=json.dumps(RESPONSE_JSON_SCHEMA, indent=2),
        streams=", ".join(sorted(taxonomy.streams)),
        form_factors=", ".join(taxonomy.detector_classes),
        items=", ".join(sorted(taxonomy.items)),
    )


def parse_response(raw: str | dict[str, Any], taxonomy: Taxonomy | None = None) -> EscalationResponse:
    """Validate a model response against the canonical vocabulary.

    Raises :class:`EscalationRejectedError` on anything outside the contract. A
    rejected response is dropped, counted, and never shown to anyone.
    """
    taxonomy = taxonomy or load_taxonomy()

    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EscalationRejectedError(f"response was not JSON: {exc}") from exc
    else:
        payload = raw

    for key in ("stream", "confidence", "form_factor", "citations"):
        if key not in payload:
            raise EscalationRejectedError(f"missing required field {key!r}")

    stream = payload["stream"]
    if stream not in taxonomy.streams:
        raise EscalationRejectedError(f"stream {stream!r} is not in the canonical vocabulary")

    form_factor = payload["form_factor"]
    if form_factor not in taxonomy.form_factors:
        raise EscalationRejectedError(f"form_factor {form_factor!r} is not a known class")

    confidence = float(payload["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise EscalationRejectedError(f"confidence {confidence} out of range")

    citations = tuple(
        Citation(title=c["title"], url=c["url"], quote=c.get("quote"))
        for c in payload["citations"]
    )
    if not citations:
        raise EscalationRejectedError("at least one municipal citation is required")

    for key in ("accepted_add", "rejected_add"):
        for item in payload.get(key, ()):
            if item not in taxonomy.items:
                raise EscalationRejectedError(f"{key} references unknown item {item!r}")

    return EscalationResponse(
        stream=stream,
        confidence=confidence,
        form_factor=form_factor,
        local_name=payload.get("local_name"),
        citations=citations,
        reasoning=payload.get("reasoning", ""),
        accepted_add=tuple(payload.get("accepted_add", ())),
        rejected_add=tuple(payload.get("rejected_add", ())),
    )
