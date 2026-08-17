#!/usr/bin/env python3
"""How many people can scan at the same time before it stops being usable?

This is the unanswered half of the phase-2 gate (docs/07). Everything about
concurrency in docs/05 § 3 is currently *derived* from single-stream latency
measured on a shared Kaggle box - probe P4 says so in as many words - and a
derivation is not a measurement.

    # From the repo root, with a container already running on :8080
    python service/loadtest/run.py --bins 1
    python service/loadtest/run.py --bins 6 --out artifacts/loadtest-6.json

**Run it against `docker run --cpus 2`, never against Cloud Run.** Cloud Run
autoscales, so a concurrency number measured there measures Google's scheduler
rather than the two vCPU the cost model is arithmetic about. The runner refuses
a URL that looks like Cloud Run unless told twice.

WHAT A SCANNER IS HERE. One virtual scanner is one client obeying the same
discipline the real one does: strict request-response, never two frames in
flight, ~3 frames per second (the 4 fps cap in docs/01 § 4, less what the motion
gate saves). A load test that fired frames without waiting would measure a
client nobody ships and would report a ceiling that cannot be reached.

WHAT IT REPORTS. p50/p95/p99 per level, throughput, and which rung of the
degradation ladder the service reached. The verdict is the largest N whose p95
stayed inside the budget - the point of the whole exercise, and the number
docs/05 § 3 and docs/11 quote.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))

from wire import DetectRequest, encode_frame  # noqa: E402 - after the path insert

#: Frames per second per scanner. The client's cap is 4 and the motion gate
#: means about 3 is what a real scan achieves (docs/05 § 3).
SCANNER_FPS = 3.0

#: A scan is short: the result lock stops it after about fifteen frames. Each
#: virtual scanner therefore runs a scan, pauses, and runs another, rather than
#: streaming forever - which would measure a client the gates forbid.
FRAMES_PER_SCAN = 15
PAUSE_BETWEEN_SCANS_S = 2.0

#: The budget a level has to stay inside to count as usable. Not the model
#: budget - this is the whole frame, over the network, under contention.
#: docs/01 § 4's one-bin frame is 66-77 ms of CPU; 250 ms of wall clock at p95
#: is the point past which the interface stops feeling like it is tracking.
DEFAULT_BUDGET_MS = 250.0


@dataclass
class Level:
    """One concurrency level: N scanners, held for a while."""

    scanners: int
    frames: int = 0
    errors: int = 0
    shed_slow: int = 0
    shed_tap: int = 0
    refused: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    seconds: float = 0.0
    #: The first thing that went wrong, kept verbatim. Counting errors without
    #: recording one is how a whole ramp gets thrown away.
    first_error: str | None = None

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return float("nan")
        ordered = sorted(self.latencies_ms)
        index = min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1))))
        return ordered[index]

    def summary(self) -> dict:
        return {
            "scanners": self.scanners,
            "frames": self.frames,
            "errors": self.errors,
            "refused_503": self.refused,
            "advice_slow": self.shed_slow,
            "advice_tap": self.shed_tap,
            "throughput_fps": round(self.frames / self.seconds, 2) if self.seconds else 0.0,
            "p50_ms": round(self.percentile(50), 1),
            "p95_ms": round(self.percentile(95), 1),
            "p99_ms": round(self.percentile(99), 1),
            "mean_ms": round(statistics.fmean(self.latencies_ms), 1) if self.latencies_ms else None,
            "first_error": self.first_error,
        }


def synthetic_jpeg(size: int = 448) -> bytes:
    """A frame shaped like the one the client sends: 448 px, JPEG, ~30 KB.

    Content is noise rather than a photograph on purpose. The validator here is
    untrained (see --force-crops), so what a real bin looks like changes nothing
    about the cost, and generating noise keeps this file free of a fixture whose
    provenance would then need explaining.
    """
    import io

    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(0)
    # Smooth-ish noise, so the JPEG compresses to roughly what a real frame does
    # rather than to the worst case pure noise would produce.
    small = rng.integers(0, 255, (size // 8, size // 8, 3), dtype=np.uint8)
    frame = np.asarray(Image.fromarray(small).resize((size, size), Image.Resampling.BILINEAR))
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="JPEG", quality=75)
    return buffer.getvalue()


async def scanner(
    client: httpx.AsyncClient,
    url: str,
    payload: bytes,
    level: Level,
    stop: asyncio.Event,
    scanner_id: int,
) -> None:
    """One person, pointing one phone, obeying the client's own gates."""
    interval = 1.0 / SCANNER_FPS
    seq = 0
    frames_this_scan = 0

    while not stop.is_set():
        seq += 1
        frames_this_scan += 1
        started = time.perf_counter()

        try:
            # Strict request-response: this await IS the backpressure. Nothing
            # else is sent by this scanner until the service answers.
            response = await client.post(
                url,
                content=payload,
                headers={"content-type": "application/octet-stream"},
                timeout=30.0,
            )
            elapsed = (time.perf_counter() - started) * 1000

            if response.status_code == 503:
                level.refused += 1
                body = response.json()
                wait = (body.get("retry_after_ms") or 1000) / 1000
                # Cooperate exactly as the client does. A load test that ignored
                # the stated wait would measure a stampede, not a ceiling.
                await asyncio.sleep(min(wait, 5.0))
                continue

            if response.status_code != 200:
                level.errors += 1
                # Keep the first one. A run that reports "480 errors" and not
                # what they were is a run that has to be done again - this cost
                # exactly one wasted ramp before it was worth doing.
                if level.first_error is None:
                    level.first_error = f"HTTP {response.status_code}: {response.text[:200]}"
                await asyncio.sleep(interval)
                continue

            level.frames += 1
            level.latencies_ms.append(elapsed)

            advice = response.json().get("advice")
            if advice:
                if advice.get("max_fps") == 0:
                    level.shed_tap += 1
                else:
                    level.shed_slow += 1

        except Exception as error:  # noqa: BLE001 - a timeout or a reset is a data point
            level.errors += 1
            if level.first_error is None:
                level.first_error = f"{type(error).__name__}: {error}"

        if frames_this_scan >= FRAMES_PER_SCAN:
            # The result lock closed. A scan is a task with an end.
            frames_this_scan = 0
            await asyncio.sleep(PAUSE_BETWEEN_SCANS_S)
            continue

        spent = time.perf_counter() - started
        if spent < interval:
            await asyncio.sleep(interval - spent)
        # Nothing else: a scanner that has already spent longer than its own
        # interval is being throttled by the service, which is the whole point.
    # Deliberately no final sleep - the level's clock stops with the event.


async def run_level(url: str, payload: bytes, scanners: int, hold_s: float) -> Level:
    level = Level(scanners=scanners)
    stop = asyncio.Event()

    limits = httpx.Limits(max_connections=scanners + 4, max_keepalive_connections=scanners + 4)
    async with httpx.AsyncClient(limits=limits) as client:
        started = time.perf_counter()
        tasks = [
            asyncio.create_task(scanner(client, url, payload, level, stop, i)) for i in range(scanners)
        ]
        await asyncio.sleep(hold_s)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        level.seconds = time.perf_counter() - started

    return level


async def warm_up(url: str, payload: bytes) -> None:
    """One frame, discarded.

    Every free tier scales to zero and the first request after a quiet period
    pays for the model load. Including that in a percentile would report the
    cold start as the steady state.
    """
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                url, content=payload, headers={"content-type": "application/octet-stream"}, timeout=120.0
            )
        except Exception as error:  # noqa: BLE001
            raise SystemExit(f"the service did not answer a warm-up frame at {url}: {error}") from error


async def health(base: str) -> dict:
    """What the service says about itself, recorded beside the numbers.

    A latency figure without the artefact and the thread count it was measured
    on is exactly the kind of number AGENTS.md forbids shipping.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{base}/health", timeout=60.0)
            return dict(response.json())
        except Exception as error:  # noqa: BLE001
            return {"error": f"{type(error).__name__}: {error}"}


async def main_async(args: argparse.Namespace) -> int:
    base = args.url.rstrip("/")
    detect = f"{base}/detect"

    if "run.app" in base and not args.i_know_this_is_not_two_vcpu:
        raise SystemExit(
            "That looks like Cloud Run, which autoscales - a concurrency number measured "
            "there measures Google's scheduler, not the 2 vCPU docs/05 § 3 prices. Run it "
            "against `docker run --cpus 2`. Pass --i-know-this-is-not-two-vcpu to override."
        )

    payload = encode_frame(
        DetectRequest(seq=1, geohash6=args.geohash, locale="en", debug=False), synthetic_jpeg(args.imgsz)
    )
    print(f"frame: {len(payload) / 1024:.1f} KB  ->  {detect}")

    info = await health(base)
    artefacts = info.get("artefacts") or {}
    validator = (artefacts.get("validator") or {}) if isinstance(artefacts, dict) else {}
    settings = info.get("settings") or {}
    print(
        f"service: gated={info.get('gated')}  threads={settings.get('intra_op_threads')}  "
        f"force_crops={settings.get('force_crops')}  imgsz={validator.get('imgsz')}"
    )
    if info.get("gated") is True:
        print("  note: serving a gated artefact - these are real numbers for a shippable model")

    print("warming up (the first frame pays for the model load) ...")
    await warm_up(detect, payload)

    levels: list[Level] = []
    verdict: int | None = None

    for scanners in args.levels:
        level = await run_level(detect, payload, scanners, args.hold)
        levels.append(level)
        s = level.summary()
        flag = "" if s["p95_ms"] <= args.budget_ms else "  <- OVER BUDGET"
        print(
            f"  {scanners:>3} scanners   p50 {s['p50_ms']:>7.1f}   p95 {s['p95_ms']:>7.1f}   "
            f"{s['throughput_fps']:>5.1f} fps   shed {s['advice_slow']}/{s['advice_tap']}/"
            f"{s['refused_503']}   err {s['errors']}{flag}"
        )
        if s["first_error"]:
            print(f"        first error: {s['first_error']}")
        if s["p95_ms"] <= args.budget_ms and s["errors"] == 0:
            verdict = scanners
        elif args.stop_when_over:
            break

    report = {
        "measured": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": detect,
        "hardware": args.host,
        # Cloud Run is x86_64. Anything else measuring for it is a proxy and has
        # to say so, exactly as sbr.bench.Hardware.representative does for the
        # latency gate - gate.py refuses to decide on a proxy without being told.
        "representative": bool(args.representative),
        "bins_per_frame": args.force_crops_note,
        "budget_p95_ms": args.budget_ms,
        "scanner_fps": SCANNER_FPS,
        "hold_seconds": args.hold,
        "frame_bytes": len(payload),
        "concurrent_scanners_within_budget": verdict,
        "health": info,
        "levels": [level.summary() for level in levels],
        "raw": [asdict(level) for level in levels] if args.raw else None,
    }

    print()
    if verdict is None:
        print(f"VERDICT: not even {args.levels[0]} scanner(s) stayed inside {args.budget_ms:.0f} ms at p95.")
    else:
        print(f"VERDICT: {verdict} concurrent scanners within {args.budget_ms:.0f} ms at p95.")
    print("This is a measurement of THIS host. Quote it with the host beside it.")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.out}")

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument(
        "--levels", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6, 8, 10, 12],
        help="concurrency levels to ramp through",
    )
    parser.add_argument("--hold", type=float, default=20.0, help="seconds to hold each level")
    parser.add_argument("--budget-ms", type=float, default=DEFAULT_BUDGET_MS, dest="budget_ms")
    parser.add_argument("--imgsz", type=int, default=448, help="frame size the client would send")
    parser.add_argument("--geohash", default="u2853k", help="geohash-6; u2853k is Deggendorf")
    parser.add_argument(
        "--bins", type=int, default=None, dest="bins",
        help="how many bins the scene has, for the report only - set SBR_FORCE_CROPS on the CONTAINER to make it true",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--host", default=None,
        help="what this was measured on, in words. REQUIRED with --out - a latency "
             "number without its hardware is the kind of number AGENTS.md forbids shipping",
    )
    parser.add_argument(
        "--representative", action="store_true",
        help="the measuring host is the serving host. Almost never true: say so only "
             "when the container really is the tier the cost model prices",
    )
    parser.add_argument("--raw", action="store_true", help="include every latency sample in the report")
    parser.add_argument("--stop-when-over", action="store_true", help="stop at the first level over budget")
    parser.add_argument("--i-know-this-is-not-two-vcpu", action="store_true")

    args = parser.parse_args(argv)
    if args.out and not args.host:
        parser.error(
            "--out needs --host. A concurrency figure is only meaningful with the "
            "hardware beside it, and a JSON file outlives the terminal it was printed "
            'in. Example: --host "docker --cpus 2 on a Snapdragon X1E80100, linux/arm64"'
        )
    args.force_crops_note = args.bins
    return args


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
