#!/usr/bin/env python3
"""Send a real frame at a running service and print the answer verbatim.

    python ml/scripts/probe_detect.py 21f9ddd8_img_4877.jpg
    SBR_DETECT_URL=https://.../detect SBR_TOKEN=$(gcloud auth print-identity-token) \
        python ml/scripts/probe_detect.py 27168d08_img_4659.jpg

**Why this exists rather than curl.** ``/detect`` does not take JSON. It takes
the same binary frame the browser sends - a four-byte big-endian header length,
a UTF-8 JSON header, then the JPEG - and the point of the load test and of this
script is that both speak the *same wire* the client does. Hand-rolling that in
a shell is how a byte-level contract quietly stops being one.

Prints the response exactly as it arrives. A claim about what the pipeline
answers should be pasteable from here, not paraphrased.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "service"))

from wire import DetectRequest, encode_frame  # noqa: E402

DEFAULT_POOL = REPO_ROOT / "data/legacy/pool/images"
DEFAULT_URL = "http://127.0.0.1:8099/detect"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("frames", nargs="+", help="file names inside --pool, or paths")
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--url", default=os.environ.get("SBR_DETECT_URL", DEFAULT_URL))
    parser.add_argument("--region", default="de-by-deggendorf")
    parser.add_argument("--geohash6", default="u2853h")
    parser.add_argument("--locale", default="de")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    headers = {"Content-Type": "application/octet-stream"}
    # A private Cloud Run revision needs an identity token. The client does NOT
    # send one - rest.ts has no Authorization header - so a service the browser
    # can reach is a public one, and this flag is for reaching a private one by
    # hand rather than for pretending the browser could.
    token = os.environ.get("SBR_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for name in args.frames:
        path = Path(name)
        if not path.exists():
            path = args.pool / name
        frame = encode_frame(
            DetectRequest(seq=1, geohash6=args.geohash6, locale=args.locale, debug=args.debug),
            path.read_bytes(),
        )
        request = urllib.request.Request(args.url, data=frame, headers=headers)  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
                print(f"=== {path.name} === HTTP {response.status}")
                print(json.dumps(json.load(response), indent=2, ensure_ascii=False))
        except urllib.error.HTTPError as error:
            body = error.read()[:400].decode("utf-8", errors="replace")
            print(f"=== {path.name} === HTTP {error.code}\n{body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
