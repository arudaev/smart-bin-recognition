"""The wire, as ``docs/01-architecture.md`` § 4 states it and
``web/src/transport/protocol.ts`` encodes it.

One binary message: a 4-byte big-endian header length, a JSON header, then the
JPEG bytes. **No base64 anywhere near the payload that dominates the uplink
bill** - it would cost a third more on the one thing users actually send.

This file is the Python half of a contract whose other half is TypeScript, and
the two are not checked by both reading the same paragraph. ``web/scripts/
emit-wire-fixtures.mjs`` writes fixtures with the TS encoder, ``tests/
test_wire_contract.py`` decodes them here, and a vitest reads back a response
this module produced. Both sides are pinned to the same bytes.

Field names are ``snake_case`` because the wire is, and the TypeScript uses the
same names rather than translating - one vocabulary, one place to get it wrong.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from typing import Any, Literal

HEADER_BYTES = 4

#: A detection is only worth drawing if model A is sure something is there.
#: The client filters on this too (``usableDetections``); the service applies it
#: so a low-confidence box never leaves the building in the first place.
VALIDATOR_FLOOR = 0.5

Novelty = Literal["none", "unknown_type", "new_region"]


class WireFormatError(ValueError):
    """Raised when a frame message cannot be parsed. Never leaks bytes."""


@dataclass(frozen=True)
class DetectRequest:
    seq: int
    #: geohash-6, about 1.2 km. Enough to pick a jurisdiction, not enough to
    #: locate a household (docs/01 § 7).
    geohash6: str | None = None
    locale: str = "en"
    debug: bool = False

    @classmethod
    def from_header(cls, raw: dict[str, Any]) -> DetectRequest:
        try:
            seq = int(raw["seq"])
        except (KeyError, TypeError, ValueError) as error:
            raise WireFormatError("frame header has no usable seq") from error
        geohash = raw.get("geohash6")
        return cls(
            seq=seq,
            geohash6=str(geohash) if geohash else None,
            locale=str(raw.get("locale") or "en"),
            debug=bool(raw.get("debug", False)),
        )


@dataclass(frozen=True)
class WireBox:
    """Percentages of the frame, so a client can draw without knowing the size."""

    x: float
    y: float
    w: float
    h: float

    def as_wire(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass(frozen=True)
class WireDetection:
    box: WireBox
    validator_conf: float
    form_factor: str | None = None
    identifier_conf: float = 0.0
    body_color: str | None = None
    lid_color: str | None = None
    aperture_color: str | None = None
    text_hint: str | None = None
    stream: str | None = None
    stream_conf: float = 0.0
    local_name: str | None = None
    novelty: Novelty = "none"

    def as_wire(self) -> dict[str, Any]:
        return {
            "box": self.box.as_wire(),
            "validator_conf": round(self.validator_conf, 4),
            "form_factor": self.form_factor,
            "identifier_conf": round(self.identifier_conf, 4),
            "body_color": self.body_color,
            "lid_color": self.lid_color,
            "aperture_color": self.aperture_color,
            "text_hint": self.text_hint,
            "stream": self.stream,
            "stream_conf": round(self.stream_conf, 4),
            "local_name": self.local_name,
            "novelty": self.novelty,
        }


@dataclass(frozen=True)
class LoadAdvice:
    """What the service is asking the client to do about load.

    docs/05 § 3's ladder, on the wire. ``max_fps`` of 0 means *stop streaming and
    offer a tap*, which is a designed state with its own copy - not an error and
    not a spinner. ``queue_wait_ms`` is the deepest rung and is a **stated** wait:
    the one thing the ladder must never do is hold a connection open while
    pretending to work.
    """

    max_fps: int
    queue_wait_ms: int | None = None

    def as_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"max_fps": self.max_fps}
        if self.queue_wait_ms is not None:
            payload["queue_wait_ms"] = self.queue_wait_ms
        return payload


@dataclass(frozen=True)
class DetectResponse:
    seq: int
    #: Server-side inference time. The client's RTT minus this is transit.
    ms: int
    detections: list[WireDetection] = field(default_factory=list)
    region_id: str | None = None
    #: The status of the pack that resolved these detections, so a client that
    #: did not bundle the pack still cannot present a draft as authoritative.
    pack_status: str | None = None
    advice: LoadAdvice | None = None
    debug: dict[str, Any] | None = None

    def as_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "seq": self.seq,
            "ms": self.ms,
            "detections": [d.as_wire() for d in self.detections],
            "region_id": self.region_id,
            "pack_status": self.pack_status,
        }
        # `advice` and `debug` are optional without a null alternative on the
        # TypeScript side, so absent means absent rather than null.
        if self.advice is not None:
            payload["advice"] = self.advice.as_wire()
        if self.debug is not None:
            payload["debug"] = self.debug
        return payload


@dataclass(frozen=True)
class WireError:
    seq: int | None
    error: str
    retry_after_ms: int | None = None
    advice: LoadAdvice | None = None

    def as_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"seq": self.seq, "error": self.error}
        if self.retry_after_ms is not None:
            payload["retry_after_ms"] = self.retry_after_ms
        if self.advice is not None:
            payload["advice"] = self.advice.as_wire()
        return payload


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #


def decode_frame(buffer: bytes) -> tuple[DetectRequest, bytes]:
    """Split one binary message into its header and its JPEG.

    Every failure here is a :class:`WireFormatError` carrying no payload bytes.
    This parses untrusted input from the open internet; an error message that
    echoed part of the frame back would be both a leak and a puzzle.
    """
    if len(buffer) < HEADER_BYTES:
        raise WireFormatError("frame is shorter than its length prefix")

    (header_length,) = struct.unpack_from(">I", buffer, 0)
    end = HEADER_BYTES + header_length
    if header_length == 0:
        raise WireFormatError("frame declares an empty header")
    if end > len(buffer):
        raise WireFormatError(
            f"frame declares a {header_length}-byte header but carries {len(buffer) - HEADER_BYTES}"
        )

    try:
        raw = json.loads(buffer[HEADER_BYTES:end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WireFormatError("frame header is not valid UTF-8 JSON") from error
    if not isinstance(raw, dict):
        raise WireFormatError("frame header is not an object")

    return DetectRequest.from_header(raw), buffer[end:]


def encode_frame(request: DetectRequest, jpeg: bytes) -> bytes:
    """The inverse. Used by the tests and the load test, never by the service."""
    header = json.dumps(
        {
            "seq": request.seq,
            "geohash6": request.geohash6,
            "locale": request.locale,
            "debug": request.debug,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return struct.pack(">I", len(header)) + header + jpeg
