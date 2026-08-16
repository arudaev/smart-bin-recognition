"""The degradation ladder: what the service does when it runs out of CPU.

docs/05 § 3 says it plainly - *"when the service saturates it must degrade
honestly"* - and then gives three rungs. This is those three rungs, and the one
sentence that matters most is the last: **never a spinner that lies.**

    depth >= slow   -> tell clients 2 fps
    depth >= tap    -> streaming off, tap-to-scan only
    depth >= queue  -> refuse, with a stated wait

The client already has a designed state for each. It has never had a way to be
*told*, because the wire had no field for it; ``wire.LoadAdvice`` is that field
and this is what decides its value.

**Depth, not latency.** Queue depth is what the service knows immediately and
without a model of itself. Latency is a consequence of depth, so reacting to
depth reacts one round-trip earlier - which on a two-vCPU box is the difference
between shedding and thrashing.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from settings import ShedThresholds
from wire import LoadAdvice

#: What a client is asked to drop to on rung 1. docs/05 § 3 names 2 fps, against
#: the 4 fps cap in docs/01 § 4 - so this halves the load a scanner generates.
SLOWED_FPS = 2

#: The client's own cap. The service may lower a client's cadence and may never
#: raise it: a gate that a server could switch off is not a gate. The client
#: enforces this too - belt and braces, because the two are deployed separately.
CLIENT_MAX_FPS = 4


@dataclass(frozen=True)
class Verdict:
    """What to do with this request, and what to tell the client."""

    accept: bool
    advice: LoadAdvice | None
    depth: int
    #: Only when refusing. A stated wait, derived from depth and observed cost.
    retry_after_ms: int | None = None

    @property
    def rung(self) -> str:
        if not self.accept:
            return "queue"
        if self.advice is None:
            return "none"
        return "tap" if self.advice.max_fps == 0 else "slow"


class LoadShedder:
    """Tracks in-flight work and maps its depth onto the ladder.

    Counts requests that have been *admitted*, not connections. On the socket a
    client holds a connection open for a whole scan while sending perhaps fifteen
    frames, and counting connections would read a locked scan - which costs
    nothing at all - as load.
    """

    def __init__(self, thresholds: ShedThresholds, frame_cost_ms: float = 65.0) -> None:
        self._thresholds = thresholds
        self._lock = threading.Lock()
        self._depth = 0
        self._peak = 0
        self._shed = 0
        # Seeded from docs/05 § 3's one-bin figure and replaced by observation on
        # the first frame, so a stated wait is derived from this service's actual
        # cost rather than from a number in a document.
        self._frame_cost_ms = frame_cost_ms

    @property
    def depth(self) -> int:
        with self._lock:
            return self._depth

    def observe(self, frame_ms: float) -> None:
        """Fold one completed frame into the cost estimate.

        An exponential moving average, weighted lightly, so a single slow frame
        does not make the service quote a wait it will not take.
        """
        with self._lock:
            self._frame_cost_ms = 0.9 * self._frame_cost_ms + 0.1 * max(1.0, frame_ms)

    def admit(self) -> Verdict:
        """Decide on one request and, if accepted, count it as in flight.

        The caller must :meth:`release` an accepted request. ``admitted`` is a
        context manager that does it for them.
        """
        with self._lock:
            depth = self._depth
            if depth >= self._thresholds.queue:
                self._shed += 1
                # At least one frame's worth. A refusal quoting zero is not a
                # stated wait, it is "retry immediately" - which is how every
                # client that was just refused comes back at once.
                wait = int(max(1, depth) * self._frame_cost_ms)
                return Verdict(
                    accept=False,
                    advice=LoadAdvice(max_fps=0, queue_wait_ms=wait),
                    depth=depth,
                    retry_after_ms=wait,
                )

            self._depth += 1
            self._peak = max(self._peak, self._depth)

            if depth >= self._thresholds.tap:
                advice: LoadAdvice | None = LoadAdvice(max_fps=0)
            elif depth >= self._thresholds.slow:
                advice = LoadAdvice(max_fps=SLOWED_FPS)
            else:
                advice = None
            return Verdict(accept=True, advice=advice, depth=depth)

    def release(self) -> None:
        with self._lock:
            self._depth = max(0, self._depth - 1)

    def stats(self) -> dict:
        with self._lock:
            return {
                "depth": self._depth,
                "peak_depth": self._peak,
                "shed": self._shed,
                "frame_cost_ms": round(self._frame_cost_ms, 1),
                "thresholds": {
                    "slow": self._thresholds.slow,
                    "tap": self._thresholds.tap,
                    "queue": self._thresholds.queue,
                },
            }


class admitted:  # noqa: N801 - a context manager reads as a verb at the call site
    """``with admitted(shedder) as verdict:`` - releases even if the frame raises."""

    def __init__(self, shedder: LoadShedder) -> None:
        self._shedder = shedder
        self._verdict: Verdict | None = None

    def __enter__(self) -> Verdict:
        self._verdict = self._shedder.admit()
        return self._verdict

    def __exit__(self, *_exc: object) -> None:
        if self._verdict is not None and self._verdict.accept:
            self._shedder.release()
