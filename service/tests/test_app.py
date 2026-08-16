"""The HTTP and WebSocket surfaces.

The pipeline is stubbed - what these check is the part that only exists at the
edge: status codes, the ``retry-after`` header, what ``/health`` admits to, and
that the socket enforces the same strict request-response the POST path gets for
free by being a request.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app as service
from artefacts import Artefact
from conftest import FakeSession, sidecar
from pipeline import Pipeline
from settings import Settings, ShedThresholds
from shed import LoadShedder
from wire import DetectRequest, encode_frame

FORM_FACTORS = ["wheelie_small", "wheelie_large", "igloo"]
CONFIG = {"data": {"crops": {"padding": 0.12, "min_box_px": 8}}}


def validator_head(_array):
    raw = np.zeros((1, 5, 1), dtype=np.float32)
    raw[0, :, 0] = [200, 220, 60, 160, 0.95]
    return raw


def classifier_head(array):
    raw = np.full((array.shape[0], 3), 0.05, dtype=np.float32)
    raw[:, 0] = 0.9
    return raw


@pytest.fixture
def client(monkeypatch, request):
    """A service with stub models. `shed` marks a test that wants the ladder."""
    thresholds = getattr(request, "param", ShedThresholds(slow=99, tap=99, queue=99))

    def fake_load() -> None:
        settings = Settings()
        service.STATE["settings"] = settings
        service.STATE["shedder"] = LoadShedder(thresholds)
        service.STATE["errors"] = {}
        service.STATE["pipeline"] = Pipeline(
            Artefact("validator", FakeSession(validator_head), sidecar("validator"), "test"),
            Artefact(
                "identifier", FakeSession(classifier_head),
                sidecar("identifier", classes=FORM_FACTORS), "test",
            ),
            settings,
            CONFIG,
        )

    monkeypatch.setattr(service, "_load", fake_load)
    with TestClient(service.app) as test_client:
        yield test_client


def frame(jpeg: bytes, seq: int = 1, geohash: str | None = "u2853x") -> bytes:
    return encode_frame(DetectRequest(seq=seq, geohash6=geohash), jpeg)


# --------------------------------------------------------------------------- #
# POST /detect - the deployed path
# --------------------------------------------------------------------------- #


def test_a_frame_gets_an_answer(client, jpeg):
    response = client.post("/detect", content=frame(jpeg))
    assert response.status_code == 200

    body = response.json()
    assert body["seq"] == 1
    assert body["region_id"] == "de-by-deggendorf"
    assert len(body["detections"]) == 1


def test_the_answer_carries_the_sequence_it_was_asked_about(client, jpeg):
    # Strict request-response: the client matches on seq and drops stragglers
    # from before a reset. An answer with the wrong seq is silently discarded.
    body = client.post("/detect", content=frame(jpeg, seq=42)).json()
    assert body["seq"] == 42


def test_an_undecodable_frame_is_a_400_not_a_500(client):
    response = client.post("/detect", content=frame(b"not a jpeg"))
    assert response.status_code == 400
    assert "seq" in response.json()


def test_a_malformed_envelope_is_a_400(client):
    response = client.post("/detect", content=b"\x00\x00")
    assert response.status_code == 400


def test_an_oversized_frame_is_refused_without_being_decoded(client):
    # A client frame is ~30 KB. Decoding a 4 MB one would be somebody else's use
    # of the two vCPUs the whole cost model is about.
    response = client.post("/detect", content=b"\x00" * (service.MAX_FRAME_BYTES + 1))
    assert response.status_code == 413


# --------------------------------------------------------------------------- #
# The ladder, over HTTP
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("client", [ShedThresholds(slow=0, tap=99, queue=99)], indirect=True)
def test_rung_one_answers_the_frame_and_asks_for_two_fps(client, jpeg):
    body = client.post("/detect", content=frame(jpeg)).json()
    assert body["detections"]          # served, not refused
    assert body["advice"]["max_fps"] == 2


@pytest.mark.parametrize("client", [ShedThresholds(slow=0, tap=0, queue=99)], indirect=True)
def test_rung_two_asks_the_client_to_stop_streaming(client, jpeg):
    body = client.post("/detect", content=frame(jpeg)).json()
    assert body["detections"]
    assert body["advice"]["max_fps"] == 0


@pytest.mark.parametrize("client", [ShedThresholds(slow=0, tap=0, queue=0)], indirect=True)
def test_rung_three_refuses_with_a_retry_after_header(client, jpeg):
    """The header matters as much as the body.

    ``RestClient`` reads ``retry-after`` on a 503 and backs off by it. Without the
    header it invents five seconds, so a service that knows the real wait would be
    keeping it to itself.
    """
    response = client.post("/detect", content=frame(jpeg))
    assert response.status_code == 503
    assert int(response.headers["retry-after"]) >= 1

    body = response.json()
    assert body["retry_after_ms"] > 0
    assert body["advice"]["queue_wait_ms"] == body["retry_after_ms"]


# --------------------------------------------------------------------------- #
# WS /stream - built and tested, not the deployed path
# --------------------------------------------------------------------------- #


def test_the_socket_answers_the_same_payload(client, jpeg):
    with client.websocket_connect("/stream") as socket:
        socket.send_bytes(frame(jpeg, seq=3))
        body = socket.receive_json()

    assert body["seq"] == 3
    assert body["region_id"] == "de-by-deggendorf"


def test_the_socket_answers_frames_in_order(client, jpeg):
    with client.websocket_connect("/stream") as socket:
        for seq in (1, 2, 3):
            socket.send_bytes(frame(jpeg, seq=seq))
            assert socket.receive_json()["seq"] == seq


def test_one_bad_frame_does_not_close_the_socket(client, jpeg):
    # A scan is fifteen frames. Dropping the connection on a corrupt one would
    # cost a reconnect and, on a cold service, several seconds.
    with client.websocket_connect("/stream") as socket:
        socket.send_bytes(frame(b"not a jpeg", seq=1))
        assert "error" in socket.receive_json()

        socket.send_bytes(frame(jpeg, seq=2))
        assert socket.receive_json()["seq"] == 2


# --------------------------------------------------------------------------- #
# /health
# --------------------------------------------------------------------------- #


def test_health_reports_the_gate_verdict_of_every_artefact(client):
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["artefacts"]["validator"]["gate_result"]["may_ship"] is True
    assert body["gated"] is True


def test_health_states_that_nothing_is_retained(client):
    # docs/03 § 4. A claim nobody can check is a claim nobody should believe.
    assert "none" in client.get("/health").json()["retention"]


def test_health_says_whether_crops_are_actually_being_batched(client):
    # The difference between the cost model and three times it.
    assert client.get("/health").json()["pipeline"]["batched_crops"] is True


def test_health_admits_the_colour_method_is_provisional(client):
    # A surprising colour should be explicable without reading the source.
    assert "PROVISIONAL" in client.get("/health").json()["colour"]["status"]


def test_health_lists_the_packs_and_whether_they_are_publishable(client):
    packs = client.get("/health").json()["pipeline"]["region_packs"]
    deggendorf = next(p for p in packs if p["region_id"] == "de-by-deggendorf")
    assert deggendorf["status"] == "draft"
    assert deggendorf["publishable"] is False
