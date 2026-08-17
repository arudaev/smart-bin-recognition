"""The wire contract, pinned to bytes rather than to a paragraph.

``wire.py`` and ``web/src/transport/protocol.ts`` both open by citing
docs/01 § 4, and both were written by reading it. That is two opinions, not a
contract, and it had already failed in production shape: the service emitted
``advice`` and ``pack_status`` for weeks while the client declared neither and
threw both away.

So the two halves are checked against the same bytes, in both directions:

    web/scripts/emit-wire-fixtures.mjs   TypeScript encoder -> requests/*.bin
    this file                            decodes them, and encodes responses
    web/.../contract.test.ts             reads those responses back

Both directions read **committed** fixtures, so neither test depends on the
other having run first and CI may schedule them in either order.

Regenerating is deliberate: ``SBR_REGEN_FIXTURES=1 pytest tests/test_wire_contract.py``.
Without it a difference is a failure. A fixture that rewrites itself on every
run does not pin anything - it agrees with whatever the code does today, which
is precisely the failure this apparatus exists to prevent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from wire import (
    DetectResponse,
    LoadAdvice,
    WireBox,
    WireDetection,
    WireError,
    WireFormatError,
    decode_frame,
    encode_frame,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "web" / "src" / "transport" / "__fixtures__"
REQUESTS = FIXTURES / "requests"
RESPONSES = FIXTURES / "responses"

REGENERATE = os.environ.get("SBR_REGEN_FIXTURES", "").strip() in {"1", "true", "yes", "on"}


def manifest() -> list[dict]:
    payload = json.loads((REQUESTS / "manifest.json").read_text(encoding="utf-8"))
    return list(payload["cases"])


def case_ids() -> list[str]:
    return [case["name"] for case in manifest()]


# --------------------------------------------------------------------------- #
# Direction 1: bytes the TypeScript encoder produced, decoded here
# --------------------------------------------------------------------------- #


def test_the_fixtures_exist_at_all():
    """A contract test whose fixtures are missing passes by doing nothing.

    Deleting the fixture directory must fail loudly rather than silently
    reducing this file to a no-op that reports green.
    """
    assert REQUESTS.is_dir(), f"no request fixtures at {REQUESTS} - run npm --prefix web run emit:fixtures"
    assert len(manifest()) >= 6


@pytest.mark.parametrize("case", manifest(), ids=case_ids())
def test_decodes_what_the_client_encoded(case: dict):
    raw = (REQUESTS / case["file"]).read_bytes()
    assert len(raw) == case["total_bytes"]

    request, jpeg = decode_frame(raw)
    expected = case["request"]

    assert request.seq == expected["seq"]
    assert request.geohash6 == expected["geohash6"]
    assert request.locale == expected["locale"]
    assert request.debug is expected["debug"]
    assert len(jpeg) == case["jpeg_bytes"]


def test_the_header_length_is_in_bytes_not_characters():
    """The bug this fixture set exists for, stated as its own assertion.

    A length written in characters slices the JPEG in half, and it does so for
    the first non-Latin locale rather than in development. ``ar-Ω`` is one
    character and two bytes, so the two counts differ by exactly one and the
    JPEG must still arrive whole.
    """
    case = next(c for c in manifest() if c["name"] == "multibyte-locale")
    assert case["header_bytes"] == case["header_chars"] + 1, "the fixture no longer exercises the bug"

    _request, jpeg = decode_frame((REQUESTS / case["file"]).read_bytes())
    assert jpeg.startswith(b"\xff\xd8\xff\xe0"), "the JPEG was sliced - the header length was read as characters"
    assert jpeg.endswith(b"\xff\xd9")


def test_a_missing_geohash_is_none_and_never_an_empty_string():
    # The service reads None as "no jurisdiction" and answers stream: null.
    # An empty string would sort as a geohash prefix and match nothing quietly.
    case = next(c for c in manifest() if c["name"] == "no-geohash")
    request, _ = decode_frame((REQUESTS / case["file"]).read_bytes())
    assert request.geohash6 is None


def test_the_python_encoder_reproduces_the_typescript_bytes():
    """``encode_frame`` is used by the tests and the load test, so it has to
    agree with the client rather than merely round-trip against itself."""
    for case in manifest():
        raw = (REQUESTS / case["file"]).read_bytes()
        request, jpeg = decode_frame(raw)
        assert encode_frame(request, jpeg) == raw, f"{case['name']} does not re-encode to the same bytes"


@pytest.mark.parametrize(
    "payload, why",
    [
        (b"", "empty"),
        (b"\x00\x00", "shorter than its length prefix"),
        (b"\x00\x00\x00\x00", "declares an empty header"),
        (b"\x00\x00\xff\xff" + b"{}", "declares more header than it carries"),
        (b"\x00\x00\x00\x02" + b"\xff\xfe", "header is not UTF-8"),
        (b"\x00\x00\x00\x02" + b"[]", "header is not an object"),
        (b"\x00\x00\x00\x02" + b"{}", "header has no seq"),
    ],
)
def test_malformed_frames_raise_without_leaking_bytes(payload: bytes, why: str):
    """This parses untrusted input from the open internet.

    An error message echoing part of the frame back would be both a leak and a
    puzzle, so the assertion is on what is *absent* from the message.
    """
    with pytest.raises(WireFormatError) as caught:
        decode_frame(payload)
    message = str(caught.value)
    assert "\xff" not in message and "\xfe" not in message, f"{why}: the error echoed frame bytes"


# --------------------------------------------------------------------------- #
# Direction 2: responses encoded here, read back by contract.test.ts
# --------------------------------------------------------------------------- #

BOX = WireBox(x=12.5, y=30.0, w=25.25, h=44.5)


def detection() -> WireDetection:
    """One detection in the shape the client receives it *today*.

    ``form_factor`` is None on purpose rather than for brevity: the identifier is
    blocked on the 403-crop human pass, so the service says where a bin is and
    declines to say which. A fixture that invented a form factor would pin a wire
    nothing currently emits.
    """
    return WireDetection(box=BOX, validator_conf=0.9312)


#: Each entry names the thing the client would get wrong if it broke.
RESPONSE_CASES: dict[str, tuple[str, DetectResponse | WireError]] = {
    "plain": (
        "the common path. `advice` and `debug` are ABSENT, not null, and a client "
        "typing them `| null` would be wrong about the wire",
        DetectResponse(seq=1, ms=71, detections=[detection()], region_id="de-by-deggendorf", pack_status="draft"),
    ),
    "no-pack": (
        "outside every known jurisdiction. pack_status and region_id are explicitly "
        "null - the client must say `unknown` rather than borrow a neighbour's rules",
        DetectResponse(seq=2, ms=66, detections=[detection()], region_id=None, pack_status=None),
    ),
    "empty": (
        "nothing in frame. An empty detections list, not a missing key",
        DetectResponse(seq=3, ms=33, detections=[], region_id="de-by-deggendorf", pack_status="draft"),
    ),
    "advice-slow": (
        "ladder rung 1. A perfectly good answer AND a request to halve the cadence: "
        "nothing is refused until rung 3",
        DetectResponse(
            seq=4, ms=88, detections=[detection()], region_id="de-by-deggendorf",
            pack_status="draft", advice=LoadAdvice(max_fps=2),
        ),
    ),
    "advice-tap": (
        "ladder rung 2. max_fps 0 means stop streaming and offer a tap. It is a "
        "designed state with its own copy, not an error and not a spinner",
        DetectResponse(
            seq=5, ms=140, detections=[detection()], region_id="de-by-deggendorf",
            pack_status="draft", advice=LoadAdvice(max_fps=0),
        ),
    ),
    "advice-raise": (
        "A SERVER MAY NOT RAISE A CADENCE. 30 is far over the client's 4 fps cap; "
        "the client must clamp it. A gate a server could switch off is not a gate",
        DetectResponse(
            seq=6, ms=40, detections=[detection()], region_id="de-by-deggendorf",
            pack_status="draft", advice=LoadAdvice(max_fps=30),
        ),
    ),
    "debug": (
        "debug builds only. Present here so the optional block's shape is pinned",
        DetectResponse(
            seq=7, ms=77, detections=[detection()], region_id="de-by-deggendorf", pack_status="draft",
            debug={
                "validator_boxes": [{"box": BOX.as_wire(), "conf": 0.9312}],
                "validator_ms": 31,
                "identifier_ms": 21,
            },
        ),
    ),
    "error-busy": (
        "ladder rung 3. A refusal quoting a STATED wait. retry_after_ms of 0 is how "
        "every client that was just refused comes back at once",
        WireError(seq=8, error="the service is busy", retry_after_ms=1040,
                  advice=LoadAdvice(max_fps=0, queue_wait_ms=1040)),
    ),
    "error-bare": (
        "a framing error. No seq, because the header could not be read far enough to "
        "have one, and no advice because load is not why this failed",
        WireError(seq=None, error="frame header is not valid UTF-8 JSON"),
    ),
}


def render(name: str) -> str:
    """One fixture document: why it exists, and the exact wire payload.

    ``why`` rides along inside the file because a reviewer looking at a failing
    byte comparison needs to know what the case was protecting, and a sibling
    README would drift away from the fixtures it describes.
    """
    why, message = RESPONSE_CASES[name]
    document = {"why": why, "payload": message.as_wire()}
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name", sorted(RESPONSE_CASES), ids=sorted(RESPONSE_CASES))
def test_response_fixtures_match_what_the_service_emits(name: str):
    RESPONSES.mkdir(parents=True, exist_ok=True)
    path = RESPONSES / f"{name}.json"
    rendered = render(name)

    if REGENERATE:
        path.write_text(rendered, encoding="utf-8")
        return

    assert path.exists(), (
        f"no response fixture at {path}. Run SBR_REGEN_FIXTURES=1 python -m pytest "
        f"tests/test_wire_contract.py, then review the diff and commit it."
    )
    assert path.read_text(encoding="utf-8") == rendered, (
        f"{name}.json no longer matches what wire.py emits. If the wire genuinely "
        f"changed, regenerate with SBR_REGEN_FIXTURES=1 AND update "
        f"web/src/transport/protocol.ts in the same commit - that is the whole point."
    )


def test_absent_is_not_null():
    """``as_wire`` omits ``advice`` and ``debug``; it emits ``pack_status: null``.

    The distinction is load-bearing on the TypeScript side, where one is typed
    ``advice?: LoadAdvice`` and the other ``pack_status?: string | null``. A
    service that started emitting ``advice: null`` would not break any Python
    test and would quietly widen the client's type.
    """
    payload = DetectResponse(seq=1, ms=10, detections=[]).as_wire()

    assert "advice" not in payload
    assert "debug" not in payload
    assert "pack_status" in payload and payload["pack_status"] is None
    assert "region_id" in payload and payload["region_id"] is None


def test_advice_omits_a_wait_it_does_not_have():
    assert LoadAdvice(max_fps=2).as_wire() == {"max_fps": 2}
    assert LoadAdvice(max_fps=0, queue_wait_ms=1500).as_wire() == {"max_fps": 0, "queue_wait_ms": 1500}


def test_every_response_fixture_is_reachable_from_a_case():
    """A stale fixture is worse than a missing one: it reads as coverage.

    If a case is renamed or dropped, the orphan on disk still gets committed and
    still gets read by contract.test.ts, which would then be asserting against a
    wire format nothing emits any more.
    """
    if not RESPONSES.is_dir():
        pytest.skip("nothing written yet")
    on_disk = {p.stem for p in RESPONSES.glob("*.json")}
    assert on_disk <= set(RESPONSE_CASES), f"orphaned response fixtures: {sorted(on_disk - set(RESPONSE_CASES))}"
