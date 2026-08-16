"""The inference service.

    POST /detect   one frame, one answer - the deployed path
    WS   /stream   the same payload, held open - built, tested, not deployed
    GET  /health   which artefacts loaded, their gate verdicts, and the load rung

**Why POST is primary and the socket is not.** Cloud Run bills request-based -
CPU only while a request is in flight, 180 000 vCPU-seconds free - or
instance-based, where idle instances bill CPU and memory too. A held-open
WebSocket forces instance-based, and one always-on 2-vCPU instance consumes the
whole monthly allowance in about twenty-five hours. So the socket ships in the
image and is reachable, and the client is pointed at ``VITE_DETECT_URL``. The
result lock means a scan is about fifteen frames either way (docs/05 § 3).

**Strict request-response, on both.** The client sends frame ``seq`` and sends
nothing more until the server answers ``seq``. That is what makes backpressure
automatic: a slow server throttles the client without either side implementing a
rate limit, and a queue can never build up because there is never more than one
frame in flight per client. The socket handler enforces it rather than trusting
it, because a client that does not is exactly the client that would hurt.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from artefacts import ArtefactMissingError, UngatedArtefactError, load_artefact
from colour import measurement_note
from pipeline import Pipeline
from settings import Settings
from shed import LoadShedder, admitted
from wire import WireError, WireFormatError, decode_frame

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("sbr.service")

#: A frame is downscaled to 448 and JPEG-encoded at about 30 KB by the client.
#: Anything an order of magnitude larger is not a frame from our client, and
#: decoding it would be somebody else's use of our two vCPUs.
MAX_FRAME_BYTES = 2 * 1024 * 1024

STATE: dict[str, Any] = {}


def _load() -> None:
    """Open the models. Runs once, at startup, and is allowed to fail loudly."""
    settings = Settings.from_env()
    STATE["settings"] = settings
    STATE["shedder"] = LoadShedder(settings.shed)
    STATE["errors"] = {}

    validator = load_artefact("validator", settings)

    # The identifier is expected to be absent today: it is blocked on the human
    # adjudication pass (docs/07 phase 2), and the service runs perfectly well
    # without it - saying where a bin is and declining to say which. An identifier
    # that exists but failed its gates is a different matter and is not caught.
    identifier = None
    try:
        identifier = load_artefact("identifier", settings)
    except ArtefactMissingError as error:
        STATE["errors"]["identifier"] = str(error)
        logger.warning(
            "no identifier: %s. Serving detection only - form_factor will be null and "
            "the resolver will answer unknown, which is a designed state.", error,
        )

    config: dict[str, Any] = {}
    try:
        from sbr.config import load_config

        config = load_config("identifier")
    except Exception as error:  # noqa: BLE001 - defaults are documented in Pipeline
        STATE["errors"]["config"] = f"{type(error).__name__}: {error}"
        logger.warning("could not load identifier.yaml (%s); using documented defaults", error)

    STATE["pipeline"] = Pipeline(validator, identifier, settings, config)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _load()
    yield
    STATE.clear()


app = FastAPI(title="Smart Bin Recognition – inference", lifespan=lifespan)

# The client is served from Vercel and the service from Cloud Run, so they are
# cross-origin by construction. Only the two verbs the protocol uses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("SBR_ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["POST", "GET"],
    allow_headers=["content-type"],
)


@app.exception_handler(UngatedArtefactError)
async def _ungated(_request: Request, error: UngatedArtefactError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": str(error)})


# --------------------------------------------------------------------------- #
# The frame path, shared by both transports
# --------------------------------------------------------------------------- #


def _handle(payload: bytes) -> tuple[dict[str, Any], int]:
    """Decode, admit, run. Returns (wire payload, HTTP status)."""
    shedder: LoadShedder = STATE["shedder"]
    pipeline: Pipeline = STATE["pipeline"]

    if len(payload) > MAX_FRAME_BYTES:
        return WireError(seq=None, error="frame too large").as_wire(), 413

    try:
        request, jpeg = decode_frame(payload)
    except WireFormatError as error:
        return WireError(seq=None, error=str(error)).as_wire(), 400

    with admitted(shedder) as verdict:
        if not verdict.accept:
            # Rung 3: a stated wait, never a silent timeout and never a spinner.
            return (
                WireError(
                    seq=request.seq,
                    error="the service is busy",
                    retry_after_ms=verdict.retry_after_ms,
                    advice=verdict.advice,
                ).as_wire(),
                503,
            )

        started = time.perf_counter()
        try:
            response = pipeline.run(request, jpeg)
        except ValueError as error:
            return WireError(seq=request.seq, error=str(error)).as_wire(), 400
        shedder.observe((time.perf_counter() - started) * 1000)

    # Rungs 1 and 2 ride along with a perfectly good answer: the frame is served
    # AND the client is asked to ease off. Nothing is refused until rung 3.
    if verdict.advice is not None:
        response = replace(response, advice=verdict.advice)
    return response.as_wire(), 200


@app.post("/detect")
async def detect(request: Request) -> JSONResponse:
    payload, status = _handle(await request.body())
    headers = {}
    if status == 503:
        headers["retry-after"] = str(max(1, round((payload.get("retry_after_ms") or 1000) / 1000)))
    return JSONResponse(status_code=status, content=payload, headers=headers)


@app.websocket("/stream")
async def stream(socket: WebSocket) -> None:
    await socket.accept()
    logger.info("socket open")
    try:
        while True:
            payload, _status = _handle(await socket.receive_bytes())
            await socket.send_json(payload)
    except WebSocketDisconnect:
        logger.info("socket closed")
    except Exception as error:  # noqa: BLE001 - one bad frame must not kill the process
        logger.exception("socket failed: %s", error)
        try:
            await socket.send_json(WireError(seq=None, error="internal error").as_wire())
        except Exception:  # noqa: BLE001 - the peer is already gone
            pass


# --------------------------------------------------------------------------- #
# Telling the truth about ourselves
# --------------------------------------------------------------------------- #


@app.get("/health")
def health() -> dict[str, Any]:
    """Everything needed to judge whether an answer from here is trustworthy.

    Deliberately verbose. The gate verdict of each artefact, the target result,
    whether the ungated override is on, whether crops are actually being batched,
    which packs are loaded and whether they are publishable, and how colour is
    being measured - because that method is provisional and a surprising colour
    should be explicable without reading the source.
    """
    pipeline: Pipeline | None = STATE.get("pipeline")
    settings: Settings | None = STATE.get("settings")
    shedder: LoadShedder | None = STATE.get("shedder")

    if pipeline is None or settings is None:
        return {"ok": False, "error": "the service has no model loaded"}

    return {
        "ok": True,
        "service": "smart-bin-recognition inference",
        # docs/03 § 4: the consent lifecycle is not built, so the service does not
        # retain. Stated here so it is checkable rather than promised in a doc.
        "retention": "none - frames are processed in memory and discarded",
        "gated": not settings.allow_ungated,
        "artefacts": {
            "validator": pipeline.validator.health(),
            "identifier": pipeline.identifier.health() if pipeline.identifier else None,
        },
        "missing": STATE.get("errors", {}),
        "pipeline": pipeline.health(),
        "colour": measurement_note(),
        "load": shedder.stats() if shedder else None,
        "settings": settings.as_dict(),
    }


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "smart-bin-recognition inference",
        "endpoints": {
            "POST /detect": "one frame, one answer - the deployed path",
            "WS /stream": "the same payload, held open",
            "GET /health": "artefacts, gate verdicts, load",
        },
        "wire": "4-byte big-endian header length, JSON header, then JPEG bytes",
    }
