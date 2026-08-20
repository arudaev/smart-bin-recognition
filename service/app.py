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
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from artefacts import (
    ArtefactMissingError,
    UngatedArtefactError,
    artefact_exists,
    load_artefact,
)
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
    # See settings.DEFAULT_INFERENCE_SLOTS. Requests arrive concurrently so the
    # shedder can see a queue; this decides how many of them the CPU works on.
    STATE["slots"] = threading.BoundedSemaphore(settings.inference_slots)
    STATE["errors"] = {}

    # ONE THREAD POOL OR TWO, decided before anything is opened.
    #
    # onnxruntime's global pools are process-wide and cannot be created after the
    # first session that opts out of per-session threads, so this cannot be
    # deferred until we discover whether an identifier exists. docs/12 P8b
    # measured both sides: sharing is worth ~31 ms on the two-graph call and
    # costs ~11 % on a single hot session, and the service is single-session
    # today because the identifier does not exist yet.
    if settings.ort_shared_pool is not None:
        shared_pool = settings.ort_shared_pool          # explicitly forced either way
    elif settings.identifier_threads is not None:
        shared_pool = False                             # a per-session count implies per-session pools
    else:
        shared_pool = artefact_exists("identifier", settings)
    STATE["ort_shared_pool"] = shared_pool
    logger.info(
        "onnxruntime thread pool: %s (%s)",
        "shared" if shared_pool else "per session",
        "explicit" if settings.ort_shared_pool is not None else "from the number of graphs",
    )

    validator = load_artefact("validator", settings, shared_pool=shared_pool)

    # The identifier is expected to be absent today: it is blocked on the human
    # adjudication pass (docs/07 phase 2), and the service runs perfectly well
    # without it - saying where a bin is and declining to say which. An identifier
    # that exists but failed its gates is a different matter and is not caught.
    identifier = None
    try:
        identifier = load_artefact("identifier", settings, shared_pool=shared_pool)
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
    slots: threading.BoundedSemaphore = STATE["slots"]

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

        with slots:
            # ADMISSION AND EXECUTION ARE DIFFERENT THINGS. The shedder counts
            # everyone waiting, which is what the advice is about; this bounds how
            # many are actually inside onnxruntime, which is what throughput is
            # about. Both graphs are pinned to both vCPUs, so a second concurrent
            # frame does not go twice as fast - it halves the speed of the first.
            started = time.perf_counter()
            try:
                response = pipeline.run(request, jpeg)
            except ValueError as error:
                return WireError(seq=request.seq, error=str(error)).as_wire(), 400
            # Inference time only. The wait quoted at rung 3 is depth times the
            # cost of a frame, so folding queueing in here would compound it.
            shedder.observe((time.perf_counter() - started) * 1000)

    # Rungs 1 and 2 ride along with a perfectly good answer: the frame is served
    # AND the client is asked to ease off. Nothing is refused until rung 3.
    if verdict.advice is not None:
        response = replace(response, advice=verdict.advice)
    return response.as_wire(), 200


@app.post("/detect")
async def detect(request: Request) -> JSONResponse:
    body = await request.body()
    # OFF THE EVENT LOOP, and this is load-bearing rather than tidy.
    #
    # `_handle` runs two ONNX graphs and blocks for 60-200 ms. Called directly
    # from a coroutine it blocks the whole event loop, so requests queue in the
    # ASGI layer instead of arriving at the shedder, and `LoadShedder.depth`
    # never exceeds 1 however many people are scanning. The load test measured
    # exactly that: twelve concurrent scanners, p95 climbing to 738 ms, and
    # `peak_depth: 1` with not one rung of the ladder fired.
    #
    # The whole of shed.py, and the client half that reads its advice, was
    # unreachable in production - the service degraded by getting slower and
    # silently, which is the one behaviour docs/05 § 3 forbids by name.
    payload, status = await run_in_threadpool(_handle, body)
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
            frame = await socket.receive_bytes()
            # Same reason as /detect. One socket blocking the loop would stall
            # every other connection on the instance, not just its own.
            payload, _status = await run_in_threadpool(_handle, frame)
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
        # The effective pool, not just the request: `ort_shared_pool: null`
        # means "decide from the graph count", and a report that only echoed
        # the request would not say which way it went.
        "settings": settings.as_dict() | {"ort_shared_pool_effective": STATE.get("ort_shared_pool")},
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
