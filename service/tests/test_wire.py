"""The framing, from the Python side.

``web/src/transport/protocol.test.ts`` asserts the same paragraph from the other
side. Both reading the same paragraph is not a contract, which is why
``test_wire_contract.py`` exists as well and pins the two to the same *bytes*.
What is checked here is the half that only matters on a server: hostile input.
"""

from __future__ import annotations

import json
import struct

import pytest

from wire import (
    DetectRequest,
    DetectResponse,
    LoadAdvice,
    WireBox,
    WireDetection,
    WireError,
    WireFormatError,
    decode_frame,
    encode_frame,
)

JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46])


def test_a_frame_round_trips():
    request = DetectRequest(seq=7, geohash6="u2853x", locale="de", debug=False)
    back, payload = decode_frame(encode_frame(request, JPEG))
    assert back == request
    assert payload == JPEG


def test_the_jpeg_travels_as_bytes_not_base64():
    # A third more uplink on the one payload that dominates the bill.
    request = DetectRequest(seq=1, geohash6=None, locale="en")
    buffer = encode_frame(request, JPEG)
    header_length = struct.unpack_from(">I", buffer, 0)[0]
    assert len(buffer) == 4 + header_length + len(JPEG)


def test_the_header_length_is_big_endian():
    buffer = encode_frame(DetectRequest(seq=1), JPEG)
    assert struct.unpack_from(">I", buffer, 0)[0] == struct.unpack_from("!I", buffer, 0)[0]
    # And not little-endian, which would agree only for lengths under 256.
    assert struct.unpack_from(">I", buffer, 0)[0] != struct.unpack_from("<I", buffer, 0)[0]


def test_a_multibyte_header_is_measured_in_bytes_not_characters():
    """Arabic is a launch locale.

    A length written in characters would slice the JPEG in half on the first
    non-ASCII header, and the failure would look like a corrupt image rather than
    a framing bug.
    """
    request = DetectRequest(seq=3, geohash6="u2853x", locale="ar-Ω")
    back, payload = decode_frame(encode_frame(request, JPEG))
    assert back.locale == "ar-Ω"
    assert payload == JPEG


def test_an_empty_frame_does_not_corrupt_the_header():
    back, payload = decode_frame(encode_frame(DetectRequest(seq=9), b""))
    assert back.seq == 9
    assert payload == b""


# --------------------------------------------------------------------------- #
# Hostile input - this parses bytes from the open internet
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "buffer",
    [
        b"",
        b"\x00\x00",
        struct.pack(">I", 0) + b"",
        struct.pack(">I", 9999) + b"{}",
        struct.pack(">I", 2) + b"\xff\xfe",
        struct.pack(">I", 2) + b"[]",
        struct.pack(">I", 4) + b"null",
    ],
    ids=["empty", "truncated-prefix", "zero-header", "header-overruns",
         "header-not-utf8", "header-is-array", "header-is-null"],
)
def test_malformed_frames_raise_a_wire_error(buffer):
    with pytest.raises(WireFormatError):
        decode_frame(buffer)


def test_a_header_without_a_seq_is_refused():
    # seq is what makes strict request-response work. A frame without one cannot
    # be answered, only guessed at.
    header = json.dumps({"locale": "en"}).encode()
    with pytest.raises(WireFormatError, match="seq"):
        decode_frame(struct.pack(">I", len(header)) + header + JPEG)


def test_an_error_message_never_echoes_the_payload():
    # Both a leak and a puzzle. The frame is a photograph of somebody's street.
    header = json.dumps({"seq": 1}).encode()
    buffer = struct.pack(">I", 9999) + header + b"SECRETPIXELS"
    with pytest.raises(WireFormatError) as raised:
        decode_frame(buffer)
    assert "SECRETPIXELS" not in str(raised.value)


# --------------------------------------------------------------------------- #
# The response shape
# --------------------------------------------------------------------------- #


def _detection(**over) -> WireDetection:
    return WireDetection(box=WireBox(10, 20, 30, 40), validator_conf=0.95, **over)


def test_optional_fields_without_a_null_alternative_are_omitted():
    """`advice?` and `debug?` are optional in TypeScript with no `| null`.

    Emitting them as null would be a type violation on the client, and the client
    checks `advice` for presence rather than truthiness.
    """
    payload = DetectResponse(seq=1, ms=40, detections=[_detection()]).as_wire()
    assert "advice" not in payload
    assert "debug" not in payload
    # These are `T | null` and are always present, so a client can read them
    # without a guard.
    assert payload["region_id"] is None
    assert payload["pack_status"] is None


def test_advice_is_emitted_when_the_ladder_engages():
    payload = DetectResponse(seq=1, ms=40, advice=LoadAdvice(max_fps=2)).as_wire()
    assert payload["advice"] == {"max_fps": 2}


def test_the_deepest_rung_states_its_wait():
    # docs/05 § 3: "queue with a stated wait, never a silent timeout".
    payload = WireError(
        seq=4, error="the service is busy", retry_after_ms=1300,
        advice=LoadAdvice(max_fps=0, queue_wait_ms=1300),
    ).as_wire()
    assert payload["retry_after_ms"] == 1300
    assert payload["advice"]["queue_wait_ms"] == 1300
    assert payload["advice"]["max_fps"] == 0


def test_a_detection_carries_every_field_the_client_reads():
    payload = _detection().as_wire()
    assert set(payload) == {
        "box", "validator_conf", "form_factor", "identifier_conf",
        "body_color", "lid_color", "aperture_color", "text_hint",
        "stream", "stream_conf", "local_name", "novelty",
    }
