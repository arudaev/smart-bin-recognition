#!/usr/bin/env python3
"""Check the pinned pool against its contract without downloading the pool.

    python ml/scripts/preflight_dataset.py
    python ml/scripts/preflight_dataset.py --revision <sha>   # check a candidate

Three manifests, about 15 MB, against a repo of 37 913 files. That is the whole
point: this answers "is the data still what we said it was" in seconds, from a
laptop, before anything is dispatched - rather than inside a kernel, after the
pool has been pulled, in a log that is only read when the run has already failed.

The contract itself lives in :mod:`sbr.dataset.expected`, beside the reasoning
for each number. This script is the network half and nothing else, which is why
the assertions here are three lines and the module they call is a hundred.

Exits non-zero on drift, so it can gate a dispatch.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT / "src"))

from sbr.dataset.expected import (  # noqa: E402 - after the path insert
    CompositionDriftError,
    DatasetExpectation,
    expectation_for,
)


def read_manifests(
    repo_id: str, revision: str, subsets: list[str]
) -> dict[str, tuple[int, int]]:
    """``{subset: (frames, boxes)}``, from the manifests alone."""
    from huggingface_hub import hf_hub_download

    from sbr.utils.hub import configure_hf_runtime, load_hf_token

    configure_hf_runtime()
    token = load_hf_token()

    counts: dict[str, tuple[int, int]] = {}
    for subset in subsets:
        local = hf_hub_download(
            repo_id=repo_id,
            filename=f"{subset}/manifest.json",
            repo_type="dataset",
            revision=revision,
            token=token,
        )
        size_mb = Path(local).stat().st_size / 1e6
        manifest = json.loads(Path(local).read_text(encoding="utf-8"))
        records = manifest.get("records") or []
        frames = len(records)
        boxes = sum(int(record.get("boxes", 0)) for record in records)
        counts[subset] = (frames, boxes)
        print(f"  {subset:>12}  {frames:>6} frames  {boxes:>6} boxes   ({size_mb:.1f} MB manifest)")

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default="arudaev/smart-bin-detect")
    parser.add_argument(
        "--revision", default=None,
        help="override the pinned revision, to check a candidate before pinning it",
    )
    args = parser.parse_args(argv)

    expected: DatasetExpectation | None = expectation_for(args.repo)
    if expected is None:
        print(
            f"{args.repo} has no composition contract.\n"
            "That is deliberate for the identifier's dataset - it is unpinned and "
            "there are no adjudicated crops yet, so there is nothing to assert. "
            "See sbr.dataset.expected."
        )
        return 0

    revision = args.revision or expected.revision
    print(f"{args.repo} @ {revision[:12]}")
    counts = read_manifests(args.repo, revision, sorted(expected.pools))

    try:
        from sbr.dataset.expected import check_manifest_counts

        check_manifest_counts(counts, expected)
    except CompositionDriftError as drift:
        print(f"\nDRIFT\n{drift}", file=sys.stderr)
        return 1

    total = sum(frames for frames, _ in counts.values())
    ratios = expected.ratios()
    print(
        f"\nOK: {total} frames = {expected.background_frames} background + "
        f"{expected.positive_frames} positive, {expected.total_boxes} boxes."
    )
    for name, value in sorted(ratios.items()):
        print(f"  negative ratio {name.replace('_', ' ')}: {value}:1")
    if args.revision and args.revision != expected.revision:
        print(
            f"\nNote: checked {args.revision[:12]}, which is NOT the pin "
            f"({expected.revision[:12]}). Pinning it is a separate, deliberate commit."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
