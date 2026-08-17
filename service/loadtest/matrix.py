#!/usr/bin/env python3
"""Run docs/12 probe P8: every recovery measured the same way, or not at all.

    # From the repo root
    python service/loadtest/matrix.py --build --host "docker --cpus 2 on ..."
    python service/loadtest/matrix.py --decompose --host "..."
    python service/loadtest/matrix.py --combined val384 nospin --host "..."

`run.py` measures one configuration. This runs the *comparison*, and it exists
because a comparison is where the mistakes live: four numbers taken on the same
host at different times, with different container lifetimes and in a convenient
order, can support almost any conclusion. Four properties are enforced here
rather than remembered:

**One variable at a time.** Each configuration differs from the baseline by
exactly one environment variable, and the container is rebuilt between them, so
nothing carries over.

**One repetition owner.** `run.py --repeats` repeats. This file calls it once per
configuration. The obvious alternative - loop here and pass --repeats too -
silently produces nine ramps and reports three.

**A baseline at both ends.** Each scene runs `baseline -> candidates in
randomised order -> baseline`. The measuring host is a laptop and it throttles;
drift shows up as the difference between the two baselines, and
**a candidate delta smaller than that drift is not a result.** The seed for the
ordering is recorded so the order can be reproduced.

**The scene is verified before it is measured.** Every configuration is sent one
debug frame first and must answer with the expected number of detections and the
expected number of crops. That check is not ceremony: `SBR_FORCE_CROPS` used to
replace the crop list *after* `SBR_MAX_CROPS` truncated it, so a P8c run would
have measured six crops under a cap of three and reported the number as a
recovery.

**Never against Cloud Run.** It autoscales; a concurrency number measured there
measures Google's scheduler rather than the two vCPU docs/05 § 3 prices. This
file only ever talks to a container it started itself.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parent
sys.path.insert(0, str(SERVICE))

from wire import DetectRequest, encode_frame  # noqa: E402 - after the path insert

CONTAINER = "sbr-p8"
IMAGE = "sbr-detect"
PORT = 8080
BASE = f"http://localhost:{PORT}"

#: Where the ungated measuring artefacts live, inside the container. The whole
#: `artifacts/` tree is mounted read-only, so a configuration can point at a
#: different graph without a different mount.
ARTEFACTS_MOUNT = "/artefacts"
DEFAULT_ARTEFACTS = f"{ARTEFACTS_MOUNT}/loadtest-artefacts"
VAL384_ARTEFACTS = f"{ARTEFACTS_MOUNT}/p8/artefacts-val384"

#: The same validator at 448, exported by the same local toolchain as the 384
#: one. It exists because ``val384`` would otherwise differ from the baseline in
#: TWO ways - input size and which machine exported the graph - and the whole
#: claim of P8a is that one variable moved. baseline vs val448local measures the
#: toolchain; val448local vs val384 measures the input size.
VAL448_LOCAL_ARTEFACTS = f"{ARTEFACTS_MOUNT}/p8/artefacts-val448local"

#: The scenes docs/12 P8 reports against. One bin is where the gate is stated;
#: six is what the PRD calls a normal input.
SCENES = (1, 6)


@dataclass(frozen=True)
class Configuration:
    """One thing to measure, and what makes it different from the baseline."""

    label: str
    env: dict[str, str] = field(default_factory=dict)
    note: str = ""

    #: Which scenes this configuration is measured in. P8c cannot move the
    #: one-bin number - there is nothing to cap - so measuring it there would
    #: produce a number whose only use is being quoted out of context.
    scenes: tuple[int, ...] = SCENES

    def crops_for(self, bins: int) -> int:
        """How many crops the service should run for this scene, given the cap."""
        return min(bins, int(self.env.get("SBR_MAX_CROPS", "6")))


CANDIDATES: dict[str, Configuration] = {
    "val448local": Configuration(
        label="val448local",
        env={"SBR_ARTEFACT_DIR": VAL448_LOCAL_ARTEFACTS},
        note="the CONTROL for val384: same size as the baseline, different exporter",
    ),
    "val384": Configuration(
        label="val384",
        env={"SBR_ARTEFACT_DIR": VAL384_ARTEFACTS},
        note="docs/05 § 7's first response to saturation. Accuracy at 384 is UNMEASURED.",
    ),
    "nospin": Configuration(
        label="nospin",
        env={"SBR_ORT_SPINNING": "0"},
        note="two sessions on two cores, neither spinning while the other works",
    ),
    "sharedpool": Configuration(
        label="sharedpool",
        env={"SBR_ORT_SHARED_POOL": "1"},
        note="one intra-op pool for both graphs instead of one each",
    ),
    "idthreads1": Configuration(
        label="idthreads1",
        env={"SBR_IDENTIFIER_THREADS": "1"},
        note="the smaller graph gets one thread, leaving one for everything else",
    ),
    "maxcrops3": Configuration(
        label="maxcrops3",
        env={"SBR_MAX_CROPS": "3"},
        note="costs coverage: the remainder is NOT deferred, it is unidentified",
        scenes=(6,),
    ),
}

BASELINE = Configuration(label="baseline", note="the service as it ships")


# --------------------------------------------------------------------------- #
# The container
# --------------------------------------------------------------------------- #


def docker(*args: str, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise SystemExit(f"docker {' '.join(args)} failed:\n{result.stderr.strip()}")
    if not quiet and result.stdout.strip():
        print(f"  docker: {result.stdout.strip()[:200]}")
    return result


def build_image() -> None:
    """Build from the REPO root - the context is the repo, not service/."""
    print(f"building {IMAGE} (context: {REPO})")
    result = subprocess.run(
        ["docker", "build", "-f", str(SERVICE / "Dockerfile"), "-t", IMAGE, str(REPO)],
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("the image did not build; nothing below can run")


def start(configuration: Configuration, bins: int, artefacts: Path) -> None:
    """A fresh container per configuration, pinned to two vCPU.

    Fresh, because onnxruntime arenas and the shedder's cost estimate both carry
    state across requests, and a configuration inheriting the previous one's warm
    arena is not the configuration it claims to be.
    """
    docker("rm", "-f", CONTAINER, check=False, quiet=True)

    environment = {
        # Every measurement in P8 runs an untrained graph, so the refusal has to
        # be lifted - and /health says `gated: false` for as long as it is.
        "SBR_ALLOW_UNGATED": "1",
        "SBR_ARTEFACT_DIR": DEFAULT_ARTEFACTS,
        "SBR_FORCE_CROPS": str(bins),
        **configuration.env,
    }
    arguments = ["run", "--rm", "-d", "--name", CONTAINER, "-p", f"{PORT}:8080", "--cpus", "2"]
    for key, value in environment.items():
        arguments += ["-e", f"{key}={value}"]
    arguments += ["-v", f"{artefacts}:{ARTEFACTS_MOUNT}:ro", IMAGE]

    docker(*arguments, quiet=True)


def stop() -> None:
    docker("rm", "-f", CONTAINER, check=False, quiet=True)


def wait_for_health(timeout_s: float = 120.0) -> dict:
    """Poll until the models are open, or give up loudly with the container log.

    A refusal at load time is the gate working and it is silent from out here -
    the port simply never answers - so the log is printed rather than left in a
    container that `--rm` is about to delete.
    """
    deadline = time.time() + timeout_s
    last: str = "no answer"
    while time.time() < deadline:
        try:
            response = httpx.get(f"{BASE}/health", timeout=5.0)
            if response.status_code == 200:
                return dict(response.json())
            last = f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as error:  # noqa: BLE001 - a container still booting is normal
            last = f"{type(error).__name__}: {error}"
        time.sleep(1.0)

    log = docker("logs", CONTAINER, check=False, quiet=True)
    raise SystemExit(
        f"the service never became healthy ({last}).\n"
        f"container log:\n{log.stdout[-2000:]}\n{log.stderr[-2000:]}"
    )


# --------------------------------------------------------------------------- #
# Verify the scene before measuring it
# --------------------------------------------------------------------------- #


def verify_scene(configuration: Configuration, bins: int) -> dict:
    """One debug frame, and the run is refused unless it answers correctly.

    Two numbers have to be right before a ramp means anything: the scene has as
    many bins as the report will claim, and the cap allowed through as many crops
    as the configuration says. The second is the one that has already been wrong
    - `SBR_FORCE_CROPS` bypassed `SBR_MAX_CROPS` entirely, so P8c would have
    measured an uncapped service and called the result a recovery.
    """
    from run import synthetic_jpeg

    payload = encode_frame(
        DetectRequest(seq=1, geohash6="u2853k", locale="en", debug=True), synthetic_jpeg(448)
    )
    response = httpx.post(
        f"{BASE}/detect",
        content=payload,
        headers={"content-type": "application/octet-stream"},
        timeout=120.0,
    )
    if response.status_code != 200:
        raise SystemExit(f"the verification frame was not served: HTTP {response.status_code}")

    body = response.json()
    debug = body.get("debug") or {}
    detections = len(body.get("detections") or [])
    crops = debug.get("crops")
    expected_crops = configuration.crops_for(bins)

    if detections != bins or crops != expected_crops:
        raise SystemExit(
            f"REFUSING TO MEASURE {configuration.label} at {bins} bin(s): the service "
            f"reported {detections} detection(s) and {crops} crop(s), expected {bins} "
            f"and {expected_crops}.\n"
            "A ramp taken against a scene that is not the scene being reported is "
            "worse than no ramp - it is a number nobody can tell is wrong."
        )

    print(f"  scene verified: {detections} detections, {crops} crops, {body.get('ms')} ms")
    return {"detections": detections, "crops": crops, "first_frame_ms": body.get("ms")}


# --------------------------------------------------------------------------- #
# One configuration, one ramp
# --------------------------------------------------------------------------- #


def measure(
    configuration: Configuration,
    bins: int,
    args: argparse.Namespace,
    out: Path,
    label_suffix: str = "",
) -> dict:
    label = f"{configuration.label}{label_suffix}"
    print(f"\n=== {label} @ {bins} bin(s) ===  {configuration.note}")
    if configuration.env:
        print(f"  env: {configuration.env}")

    start(configuration, bins, args.artefacts)
    try:
        health = wait_for_health()
        if health.get("gated") is not False:
            print("  note: this service reports gated=true, which P8 did not expect")
        scene = verify_scene(configuration, bins)

        report_path = out / f"{label}-{bins}bin.json"
        command = [
            sys.executable,
            str(SERVICE / "loadtest" / "run.py"),
            "--url", BASE,
            "--bins", str(bins),
            "--label", label,
            # THE ONLY REPETITION. See this module's docstring.
            "--repeats", str(args.repeats),
            "--hold", str(args.hold),
            "--out", str(report_path),
            "--host", args.host,
        ]
        if args.levels:
            command += ["--levels", *[str(n) for n in args.levels]]
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            raise SystemExit(f"the ramp for {label} failed with exit {result.returncode}")

        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["scene_verified"] = scene
        report["configuration"] = {"label": label, "env": configuration.env, "note": configuration.note}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    finally:
        stop()


def decompose(args: argparse.Namespace, out: Path) -> list[dict]:
    """Where the milliseconds go, at one scanner, at 1 / 3 / 6 bins.

    One scanner on purpose. Under contention the buckets describe contention,
    and docs/12 P8b is asking what a frame costs when nothing is competing with
    it - which is the quantity P4 could not account for.
    """
    reports = []
    for bins in (1, 3, 6):
        print(f"\n=== decomposition @ {bins} bin(s) ===")
        start(BASELINE, bins, args.artefacts)
        try:
            wait_for_health()
            verify_scene(BASELINE, bins)
            path = out / f"decompose-{bins}bin.json"
            subprocess.run(
                [
                    sys.executable, str(SERVICE / "loadtest" / "run.py"),
                    "--url", BASE, "--bins", str(bins), "--label", f"decompose-{bins}bin",
                    "--levels", "1", "--repeats", str(args.repeats), "--hold", str(args.hold),
                    "--debug", "--out", str(path), "--host", args.host,
                ],
                check=True,
            )
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        finally:
            stop()
    return reports


# --------------------------------------------------------------------------- #


def run_matrix(args: argparse.Namespace, out: Path) -> dict:
    rng = random.Random(args.seed)
    candidates = [CANDIDATES[name] for name in args.candidates]
    if args.combined:
        merged: dict[str, str] = {}
        for name in args.combined:
            merged |= CANDIDATES[name].env
        candidates.append(
            Configuration(
                label="combined",
                env=merged,
                note=f"every adopted recovery at once: {'+'.join(args.combined)}",
            )
        )

    results: dict[str, list[dict]] = {}
    for bins in SCENES:
        applicable = [c for c in candidates if bins in c.scenes]
        order = list(applicable)
        rng.shuffle(order)
        print(f"\n########## {bins} bin(s): {[c.label for c in order]} ##########")

        # The bracket. Both baselines are measured; the difference between them
        # is this host's drift over the block, and it is the floor under which a
        # candidate delta means nothing.
        sequence = [(BASELINE, "-a"), *[(c, "") for c in order], (BASELINE, "-b")]
        results[f"{bins}bin"] = [
            measure(configuration, bins, args, out, suffix)
            for configuration, suffix in sequence
        ]

    return {
        "probe": "P8",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": args.host,
        "representative": False,
        "seed": args.seed,
        "repeats": args.repeats,
        "hold_seconds": args.hold,
        "scenes": list(SCENES),
        "note": (
            "Each scene is bracketed by a baseline. A candidate delta smaller than "
            "the baseline-to-baseline difference is drift, not a recovery."
        ),
        "results": {
            scene: [
                {
                    "label": report["configuration"]["label"],
                    "env": report["configuration"]["env"],
                    "concurrent_scanners": report["concurrent_scanners_within_budget"],
                }
                for report in reports
            ]
            for scene, reports in results.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--host", required=True,
        help='what this is measured on, in words. Example: "docker --cpus 2, '
             'linux/arm64 native, Snapdragon X1E80100"',
    )
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "p8")
    parser.add_argument("--artefacts", type=Path, default=REPO / "artifacts")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--hold", type=float, default=20.0)
    parser.add_argument("--levels", type=int, nargs="+", default=None)
    parser.add_argument("--seed", type=int, default=20260817, help="orders the candidates")
    parser.add_argument("--build", action="store_true", help="rebuild the image first")
    parser.add_argument(
        "--decompose", action="store_true",
        help="run P8b's decomposition instead of the matrix",
    )
    parser.add_argument(
        "--candidates", nargs="+", default=["val448local", "val384", "nospin", "maxcrops3"],
        choices=sorted(CANDIDATES),
    )
    parser.add_argument(
        "--combined", nargs="+", default=None, choices=sorted(CANDIDATES),
        help="also measure these together, as the run the verdict is read off",
    )
    args = parser.parse_args(argv)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    args.artefacts = args.artefacts.resolve()

    if args.build:
        build_image()

    try:
        if args.decompose:
            payload = {
                "probe": "P8b",
                "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "hardware": args.host,
                "representative": False,
                "reports": decompose(args, out),
            }
            (out / "decomposition.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"\nwrote {out / 'decomposition.json'}")
            return 0

        summary = run_matrix(args, out)
        (out / "matrix.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nwrote {out / 'matrix.json'}")
        for scene, rows in summary["results"].items():
            print(f"\n{scene}:")
            for row in rows:
                print(f"  {row['label']:>14}  {row['concurrent_scanners']}")
        print(
            "\nThis host is a PROXY. Cloud Run is x86_64; these are within-host "
            "deltas, and the gate is stated at 10."
        )
        return 0
    finally:
        stop()


if __name__ == "__main__":
    raise SystemExit(main())
