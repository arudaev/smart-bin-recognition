"""Send a real Deggendorf frame to a running service and print the answer verbatim."""
import json, sys, urllib.request
from pathlib import Path

sys.path.insert(0, "service")
from wire import DetectRequest, encode_frame  # noqa: E402

POOL = Path("data/legacy/pool/images")
URL = "http://127.0.0.1:8099/detect"

for name in sys.argv[1:]:
    frame = encode_frame(
        DetectRequest(seq=1, geohash6="u2853h", locale="de", debug=False),
        (POOL / name).read_bytes(),
    )
    req = urllib.request.Request(URL, data=frame, headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"=== {name} === HTTP {e.code}: {e.read()[:400].decode(errors='replace')}")
        continue
    print(f"=== {name} ===")
    print(json.dumps(out, indent=2, ensure_ascii=False))
