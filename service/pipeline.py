"""One frame in, detections out.

    validator -> crops -> identifier (BATCHED) -> colour -> resolve -> novelty

Four things here are decisions rather than implementation, and each is written
down where it happens:

1. **The crops go through the identifier in one call.** docs/01 § 4 makes that a
   service requirement, not an optimisation: at the six-container bank the PRD
   calls a normal input, *n* sequential calls is roughly three times the cost and
   drops the concurrency ceiling from about ten scanners to about three and a
   half. If the graph cannot be batched the fallback is sequential and it is
   **reported**, never silent.

2. **The resolver is imported.** ``sbr.taxonomy`` is the reference implementation
   and is unit-tested; ``web/src/domain/`` is the browser one. A third copy of the
   rules deciding what may be thrown where is the worst possible place for drift,
   so there is not one.

3. **No pack means no answer.** ``stream`` is ``None`` where no region pack covers
   the frame - never a neighbouring city's rules, never the taxonomy's typical
   colours. ``unknown`` is a designed state with its own UI, and being
   confidently wrong about what goes in which bin is this product's worst
   failure.

4. **The frame is never written down.** The JPEG exists as a local, is decoded to
   an array, and both go out of scope when this function returns. docs/03 § 4's
   consent lifecycle is not built, so there is nothing that could make retention
   lawful here - and a service that retained "just until the flow exists" is
   exactly the thing that paragraph was written to prevent.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from artefacts import Artefact
from colour import estimate_illuminant, measure_body_colour
from settings import Settings
from wire import VALIDATOR_FLOOR, DetectRequest, DetectResponse, Novelty, WireBox, WireDetection

logger = logging.getLogger("sbr.service")

#: Fallback when neither the sidecar nor the config states one. docs/04 § 7 and
#: identifier.yaml both call 0.55 provisional - it is a guess until docs/12 probe
#: P2 chooses an operating point - so it is read from configuration, and this
#: constant exists only so a missing config is not a crash.
FALLBACK_UNKNOWN_THRESHOLD = 0.55


@dataclass(frozen=True)
class Box:
    """A box in pixels of the original frame."""

    x1: float
    y1: float
    x2: float
    y2: float
    score: float

    def as_wire(self, width: int, height: int) -> WireBox:
        """Percentages of the frame, so the client draws without knowing the size."""
        return WireBox(
            x=round(100 * self.x1 / width, 3),
            y=round(100 * self.y1 / height, 3),
            w=round(100 * (self.x2 - self.x1) / width, 3),
            h=round(100 * (self.y2 - self.y1) / height, 3),
        )


# --------------------------------------------------------------------------- #
# Pre- and post-processing
# --------------------------------------------------------------------------- #


def decode_jpeg(payload: bytes) -> np.ndarray:
    """JPEG bytes to an RGB array. Raises ValueError on anything undecodable."""
    from PIL import Image

    try:
        with Image.open(io.BytesIO(payload)) as handle:
            return np.asarray(handle.convert("RGB"), dtype=np.uint8)
    except Exception as error:  # noqa: BLE001 - any failure is one answer: bad frame
        raise ValueError(f"frame is not a decodable image ({type(error).__name__})") from error


def letterbox(frame: np.ndarray, size: int) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize preserving aspect ratio, pad to square. Returns (image, scale, pad).

    Padded rather than stretched because the detector was trained on letterboxed
    images, and because a stretched bin is a differently-shaped object - which is
    the one thing the form-factor classes are about.
    """
    from PIL import Image

    height, width = frame.shape[:2]
    scale = min(size / width, size / height)
    new_w, new_h = max(1, round(width * scale)), max(1, round(height * scale))

    resized = np.asarray(
        Image.fromarray(frame).resize((new_w, new_h), Image.Resampling.BILINEAR), dtype=np.uint8
    )
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)  # the usual YOLO grey
    pad_x, pad_y = (size - new_w) // 2, (size - new_h) // 2
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    return canvas, scale, (pad_x, pad_y)


def to_input(image: np.ndarray, normalisation: dict[str, Any]) -> np.ndarray:
    """HWC uint8 to NCHW float32, normalised as the sidecar says."""
    scale = float(normalisation.get("scale", 1 / 255.0))
    mean = np.asarray(normalisation.get("mean") or [0, 0, 0], dtype=np.float32)
    std = np.asarray(normalisation.get("std") or [1, 1, 1], dtype=np.float32)

    array = image.astype(np.float32) * scale
    array = (array - mean) / std
    return np.ascontiguousarray(array.transpose(2, 0, 1)[None, ...], dtype=np.float32)


def non_max_suppression(boxes: list[Box], iou_threshold: float) -> list[Box]:
    """Plain greedy NMS. Deliberately out of the ONNX graph.

    ``onnx_export`` exports with ``nms=False`` so the graph stays portable across
    runtimes; the cost of doing it here is about thirty lines and no measurable
    time at the box counts a frame produces.
    """
    kept: list[Box] = []
    for box in sorted(boxes, key=lambda b: b.score, reverse=True):
        if all(_iou(box, other) <= iou_threshold for other in kept):
            kept.append(box)
    return kept


def _iou(a: Box, b: Box) -> float:
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    overlap = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if overlap <= 0:
        return 0.0
    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    union = area_a + area_b - overlap
    return overlap / union if union > 0 else 0.0


def decode_detections(
    raw: np.ndarray, scale: float, pad: tuple[int, int], frame_shape: tuple[int, int],
    score_threshold: float, iou_threshold: float, channels: int,
) -> list[Box]:
    """YOLO head output to boxes in original-frame pixels.

    The head emits ``(1, 4 + classes, anchors)`` as centre-x, centre-y, width,
    height then per-class scores, in input-image pixels. The validator has one
    class, so the maximum over the class rows is simply "is there a bin".

    ``channels`` is ``4 + len(classes)`` and comes from the sidecar. Orienting the
    array by *knowing* the channel count rather than by assuming anchors outnumber
    channels matters more than it looks: the assumption holds for every real
    export, so a decoder built on it works until the day it silently does not, and
    a transposed head produces plausible boxes in the wrong places rather than an
    error.
    """
    array = np.squeeze(raw, axis=0) if raw.ndim == 3 else raw
    if array.shape[0] == channels:
        array = array.T                     # (channels, anchors) -> (anchors, channels)
    elif array.shape[1] != channels:
        raise ValueError(
            f"the validator head emitted {array.shape}, which has no axis of "
            f"{channels} (4 + {channels - 4} classes from the sidecar)"
        )

    coordinates = array[:, :4]
    scores = array[:, 4:].max(axis=1) if array.shape[1] > 4 else array[:, 4]

    keep = scores >= score_threshold
    if not np.any(keep):
        return []
    coordinates, scores = coordinates[keep], scores[keep]

    pad_x, pad_y = pad
    height, width = frame_shape
    cx, cy, w, h = coordinates.T
    x1 = (cx - w / 2 - pad_x) / scale
    y1 = (cy - h / 2 - pad_y) / scale
    x2 = (cx + w / 2 - pad_x) / scale
    y2 = (cy + h / 2 - pad_y) / scale

    boxes = [
        Box(
            x1=float(np.clip(a, 0, width)), y1=float(np.clip(b, 0, height)),
            x2=float(np.clip(c, 0, width)), y2=float(np.clip(d, 0, height)),
            score=float(s),
        )
        for a, b, c, d, s in zip(x1, y1, x2, y2, scores, strict=True)
    ]
    boxes = [b for b in boxes if b.x2 > b.x1 and b.y2 > b.y1]
    return non_max_suppression(boxes, iou_threshold)


def crop_for(frame: np.ndarray, box: Box, padding: float) -> np.ndarray:
    """The identifier's input: the box, padded, clipped to the frame.

    ``identifier.yaml`` pads by 0.12 because a little context helps distinguish a
    240 L bin from a 1100 L one - the distinction docs/12 probe P1 exists to test.
    """
    height, width = frame.shape[:2]
    pad_w = (box.x2 - box.x1) * padding
    pad_h = (box.y2 - box.y1) * padding
    x1 = int(max(0, box.x1 - pad_w))
    y1 = int(max(0, box.y1 - pad_h))
    x2 = int(min(width, box.x2 + pad_w))
    y2 = int(min(height, box.y2 + pad_h))
    return frame[y1:y2, x1:x2]


def softmax(logits: np.ndarray) -> np.ndarray:
    """Only if the head did not already do it. Ultralytics classify heads emit
    probabilities; a raw-logit export must not be read as one."""
    if logits.ndim == 1:
        logits = logits[None, :]
    total = logits.sum(axis=1)
    if np.all(logits >= 0) and np.allclose(total, 1.0, atol=1e-3):
        return logits
    shifted = logits - logits.max(axis=1, keepdims=True)
    exponentiated = np.exp(shifted)
    return exponentiated / exponentiated.sum(axis=1, keepdims=True)


# --------------------------------------------------------------------------- #
# The pipeline
# --------------------------------------------------------------------------- #


class Pipeline:
    """Holds the models and the packs. One instance per process."""

    def __init__(
        self,
        validator: Artefact,
        identifier: Artefact | None,
        settings: Settings,
        config: dict[str, Any] | None = None,
    ) -> None:
        from sbr.taxonomy import load_all_region_packs

        self.validator = validator
        self.identifier = identifier
        self.settings = settings
        self.packs = load_all_region_packs()

        config = config or {}
        crops = ((config.get("data") or {}).get("crops")) or {}
        self.crop_padding = float(crops.get("padding", 0.12))
        self.min_box_px = int(crops.get("min_box_px", 64))

        # P2 will calibrate this and pin it into the sidecar with the run that
        # produced it. Until then it comes from identifier.yaml, which says in as
        # many words that 0.55 is a guess.
        sidecar_threshold = (identifier.sidecar.get("unknown_threshold") if identifier else None)
        self.unknown_threshold = float(
            sidecar_threshold
            if sidecar_threshold is not None
            else ((config.get("inference") or {}).get("unknown_threshold", FALLBACK_UNKNOWN_THRESHOLD))
        )

        nms = validator.nms
        self.score_threshold = float(nms.get("score", 0.35))
        self.iou_threshold = float(nms.get("iou", 0.45))

        self.batching = bool(identifier and identifier.dynamic_batch)
        if identifier and not self.batching:
            logger.warning(
                "the identifier graph has a static batch axis, so crops run SEQUENTIALLY. "
                "A six-bin frame costs about three times what docs/05 § 3 prices. "
                "Re-export it - see sbr.export.onnx_export.batched_role."
            )

    # -- the two model calls ------------------------------------------------ #

    def _validate(self, frame: np.ndarray) -> tuple[list[Box], float]:
        started = time.perf_counter()
        image, scale, pad = letterbox(frame, self.validator.imgsz)
        raw = self.validator.session.run(
            None, {self.validator.input_name: to_input(image, self.validator.normalisation)}
        )[0]
        boxes = decode_detections(
            np.asarray(raw), scale, pad, frame.shape[:2],
            self.score_threshold, self.iou_threshold,
            channels=4 + len(self.validator.classes),
        )
        return boxes, (time.perf_counter() - started) * 1000

    def _identify(self, crops: list[np.ndarray]) -> tuple[list[tuple[str | None, float]], float]:
        """One call for every crop, where the graph allows it."""
        if not self.identifier or not crops:
            return [], 0.0

        size = self.identifier.imgsz
        normalisation = self.identifier.normalisation
        batch = np.concatenate(
            [to_input(letterbox(crop, size)[0], normalisation) for crop in crops], axis=0
        )

        started = time.perf_counter()
        if self.batching:
            raw = self.identifier.session.run(None, {self.identifier.input_name: batch})[0]
            probabilities = softmax(np.asarray(raw))
        else:
            probabilities = np.concatenate(
                [
                    softmax(
                        np.asarray(
                            self.identifier.session.run(
                                None, {self.identifier.input_name: batch[i : i + 1]}
                            )[0]
                        )
                    )
                    for i in range(batch.shape[0])
                ],
                axis=0,
            )
        elapsed = (time.perf_counter() - started) * 1000

        names = self.identifier.classes
        results: list[tuple[str | None, float]] = []
        for row in probabilities:
            index = int(np.argmax(row))
            confidence = float(row[index])
            name = names[index] if index < len(names) else None
            # Below the threshold the identifier says it does not know. That is a
            # designed product state and the entry point to the improvement loop,
            # not a failure - docs/01 § 3.
            results.append((name if confidence >= self.unknown_threshold else None, confidence))
        return results, elapsed

    # -- the whole frame ---------------------------------------------------- #

    def run(self, request: DetectRequest, jpeg: bytes) -> DetectResponse:
        from sbr.taxonomy import Observation, region_for_geohash

        started = time.perf_counter()
        frame = decode_jpeg(jpeg)
        height, width = frame.shape[:2]

        boxes, validator_ms = self._validate(frame)
        boxes = [b for b in boxes if b.score >= VALIDATOR_FLOOR]
        boxes.sort(key=lambda b: b.score, reverse=True)

        # A box too small to identify is still a box: it is reported, and the
        # identifier is simply not asked about it.
        #
        # NOTHING BEYOND max_crops IS DEFERRED. It is truncated, here, and never
        # revisited: the boxes past the cap are still drawn, but they carry no
        # form factor and no colour, so at the six-container bank a cap of three
        # leaves three containers permanently unidentified rather than answered a
        # frame later. docs/05 § 7 and settings.DEFAULT_MAX_CROPS both used to say
        # "with the remainder deferred to the next frame"; that was never built,
        # and the honest reading of the cap is that it trades coverage for cost.
        identifiable = [
            b for b in boxes
            if min(b.x2 - b.x1, b.y2 - b.y1) >= self.min_box_px
        ][: self.settings.max_crops]

        if self.settings.force_crops is not None:
            # THE FORCED BOXES ARE THE SCENE, and the cap applies to them.
            #
            # This used to assign to `identifiable` *after* the truncation above,
            # which silently bypassed max_crops entirely: SBR_FORCE_CROPS=6 with
            # SBR_MAX_CROPS=3 ran six crops, so a probe measuring the cap would
            # have measured nothing and reported a number. Replacing `boxes` too
            # is what makes the detection count deterministic, and therefore what
            # makes "six detections, three crops" checkable from outside.
            forced = _forced_crops(self.settings.force_crops, width, height)
            boxes = forced
            identifiable = forced[: self.settings.max_crops]

        crops = [crop_for(frame, box, self.crop_padding) for box in identifiable]
        crops = [c for c in crops if c.size > 0]
        identities, identifier_ms = self._identify(crops)

        pack = region_for_geohash(request.geohash6, self.packs)
        detections: list[WireDetection] = []

        # Estimated once, from the whole frame, and applied to every crop. The
        # illuminant is a property of the scene, and a crop of one bin is the
        # exact input the gray-world assumption fails on - see colour.py.
        gain = estimate_illuminant(frame.astype(np.float64) / 255.0) if crops else None

        for index, box in enumerate(boxes):
            form_factor, identifier_conf = (
                identities[index] if index < len(identities) else (None, 0.0)
            )
            body_colour = None
            if index < len(crops):
                body_colour, _ = measure_body_colour(crops[index], gain)

            stream, stream_conf, local_name = None, 0.0, None
            if pack is not None and form_factor:
                resolution = pack.resolve(
                    Observation(form_factor=form_factor, body_color=body_colour)
                )
                stream = resolution.stream
                stream_conf = resolution.confidence
                local_name = resolution.local_name

            detections.append(
                WireDetection(
                    box=box.as_wire(width, height),
                    validator_conf=box.score,
                    form_factor=form_factor,
                    identifier_conf=identifier_conf,
                    body_color=body_colour,
                    lid_color=None,  # see colour.py - lid/body separation is unsolved
                    stream=stream,
                    stream_conf=stream_conf,
                    local_name=local_name,
                    novelty=self._novelty(pack, form_factor, identifier_conf, index < len(crops)),
                )
            )

        total_ms = (time.perf_counter() - started) * 1000
        debug = None
        if request.debug:
            debug = {
                "validator_boxes": [
                    {"box": b.as_wire(width, height).as_wire(), "conf": round(b.score, 4)}
                    for b in boxes
                ],
                "validator_ms": round(validator_ms, 1),
                "identifier_ms": round(identifier_ms, 1),
                "crops": len(crops),
                "batched": self.batching,
            }

        return DetectResponse(
            seq=request.seq,
            ms=int(round(total_ms)),
            detections=detections,
            region_id=pack.region_id if pack else None,
            pack_status=pack.status if pack else None,
            debug=debug,
        )

    def _novelty(
        self, pack: Any, form_factor: str | None, confidence: float, asked: bool
    ) -> Novelty:
        """Why this detection might be worth collecting (docs/01 § 3).

        ``new_region`` is *no pack covers this location*, which is a stable fact
        about our coverage. The stronger reading in docs/01 - a geohash cell never
        seen before - needs the registry to remember cells across restarts, and
        this service scales to zero. An in-memory set would flag almost every
        frame after every cold start, which is not a signal, it is a counter of
        deployments.

        ``unknown_type`` requires the identifier to have been *asked* and to have
        declined. No identifier at all is not a disagreement, and reporting it as
        one would fill the collection queue with frames that prove nothing.
        """
        if pack is None:
            return "new_region"
        if self.identifier and asked and form_factor is None and confidence > 0:
            return "unknown_type"
        return "none"

    def health(self) -> dict[str, Any]:
        return {
            "batched_crops": self.batching,
            "max_crops": self.settings.max_crops,
            "crop_padding": self.crop_padding,
            "min_box_px": self.min_box_px,
            "unknown_threshold": self.unknown_threshold,
            "nms": {"score": self.score_threshold, "iou": self.iou_threshold},
            "region_packs": [
                {
                    "region_id": pack.region_id,
                    "status": pack.status,
                    "publishable": pack.is_publishable,
                    "geohash_tiles": list(pack.geohash_tiles),
                }
                for pack in self.packs.values()
            ],
        }


def _forced_crops(count: int, width: int, height: int) -> list[Box]:
    """Evenly spaced synthetic boxes. TEST ONLY - see Settings.force_crops.

    Under an untrained validator the box count is arbitrary, which makes the
    multi-bin cost curve unmeasurable. This makes it controllable. It is refused
    unless SBR_ALLOW_UNGATED is also set, so it can never be mistaken for a
    service answering a real question.
    """
    if count <= 0:
        return []
    step = width / count
    return [
        Box(
            x1=i * step, y1=height * 0.25,
            x2=(i + 1) * step, y2=height * 0.9,
            score=0.99,
        )
        for i in range(count)
    ]
