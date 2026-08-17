# service – the inference service

Two models, one frame, one answer.

```
POST /detect   one frame, one answer – the deployed path
WS   /stream   the same payload, held open – built and tested, not deployed
GET  /health   which artefacts loaded, their gate verdicts, and the load rung
```

## Why POST is primary

Cloud Run bills **request-based** – CPU only while a request is in flight,
180 000 vCPU-seconds free – or **instance-based**, where idle instances bill CPU
and memory too. A held-open WebSocket forces instance-based, and one always-on
2-vCPU instance eats the whole monthly allowance in about twenty-five hours.

So the socket ships in the image and works; the client is pointed at
`VITE_DETECT_URL`. The result lock means a scan is about fifteen frames either
way ([docs/05 § 3](../docs/05-cost-model.md)). If streaming later proves
necessary, HF PRO at USD 9/month restores it with no code change.

## Running it

```bash
# From the REPO ROOT – the build context is the repo, not this directory.
docker build -f service/Dockerfile -t sbr-detect .

# Pinned to two vCPUs, because that is what the whole cost model is arithmetic
# about. Without --cpus the numbers mean nothing.
docker run --rm -p 8080:8080 --cpus 2 \
  -e SBR_MODEL_REPO=arudaev/smart-bin-detect \
  -e SBR_MODEL_REVISION=main \
  sbr-detect

curl -s localhost:8080/health | jq
```

Locally, without Docker:

```bash
PYTHONPATH=../ml/src uvicorn app:app --app-dir . --port 8080
cd service && python -m pytest tests/ -q && ruff check . && mypy .
```

## Configuration

Everything is environment. Nothing about the *model* is here at all – class
names, input size, layout, normalisation and NMS thresholds all come from the
artefact's sidecar.

| Variable | Default | What it does |
|---|---|---|
| `SBR_MODEL_REPO` | `arudaev/smart-bin-detect` | Hub repo holding the artefacts |
| `SBR_MODEL_REVISION` | `main` | pin this for a reproducible deployment |
| `SBR_VALIDATOR_VERSION` / `SBR_IDENTIFIER_VERSION` | `1` | which version to load |
| `SBR_ARTEFACT_DIR` | – | load from a directory instead of the Hub |
| `SBR_INTRA_OP_THREADS` | `2` | onnxruntime threads; the service has 2 vCPU |
| `SBR_MAX_CROPS` | `6` | crops per frame; the rest are reported unidentified, NOT deferred |
| `SBR_ORT_SHARED_POOL` | `1` | one onnxruntime thread pool for both graphs. **On by default** since docs/12 P8b; `0` restores one pool per session |
| `SBR_ORT_SPINNING` | `1` | whether idle intra-op threads spin |
| `SBR_IDENTIFIER_THREADS` | – | threads for the identifier alone; needs `SBR_ORT_SHARED_POOL=0` |
| `SBR_SHED_SLOW` / `_TAP` / `_QUEUE` | `4` / `8` / `16` | the three rungs of the ladder |
| `SBR_ALLOWED_ORIGINS` | `*` | CORS; the client is cross-origin by construction |
| `SBR_ALLOW_UNGATED` | unset | **see below** |
| `SBR_FORCE_CROPS` | unset | **test only**; requires `SBR_ALLOW_UNGATED` |

## The refusal

**An artefact whose sidecar does not say `may_ship` is not served.** Not a
warning, not a degraded mode – a refusal at load time, before the port is open.
That is the entire point of the gate apparatus in `ml/`: until this service
existed there was nothing on the other end of the verdict.

`SBR_ALLOW_UNGATED=1` overrides it, and is the same deliberate friction as
`gate.py --allow-unrepresentative-hardware`. It exists so latency and concurrency
can be measured **before a model is trained**, it is never the default, and
`/health` reports `gated: false` for as long as it is on.

`SBR_FORCE_CROPS=n` runs the identifier on *n* crops whatever the validator
found. It fabricates detections, so it is welded to `SBR_ALLOW_UNGATED` – on a
real artefact it would be a service inventing bins.

## What it does not know

- **Disposal rules.** It looks them up. `sbr.taxonomy` is the reference resolver
  and is imported, never re-implemented; `web/src/domain/` is the browser one.
  A third copy would be the worst possible place for drift.
- **What to say where there is no pack.** `stream` is `null`, and the client says
  `unknown` – a designed state with its own UI. Never a neighbouring city's rules.
- **Which bin it is, today.** The identifier is blocked on the human adjudication
  pass ([docs/07](../docs/07-roadmap.md) phase 2). Without it the service answers
  *where* and declines *which*, `/health` says so, and nothing pretends otherwise.

## Frames are not kept

Processed in memory and discarded. `/health` reports
`retention: "none"`, and `tests/test_discipline.py` parses every module on the
request path and fails if any of them calls `open`, `write_bytes`, `save` or a
sibling.

docs/03 § 4's consent lifecycle is not built, so nothing here could make
retention lawful. A service that retained "just until the flow exists" is exactly
what that section was written to prevent.

## The degradation ladder

[docs/05 § 3](../docs/05-cost-model.md), implemented in `shed.py`:

| Queue depth | What the client is told | Still served? |
|---|---|---|
| `≥ SBR_SHED_SLOW` | `advice.max_fps: 2` | yes |
| `≥ SBR_SHED_TAP` | `advice.max_fps: 0` – stop streaming, offer a tap | yes |
| `≥ SBR_SHED_QUEUE` | `503` with `retry_after_ms` and a stated wait | no |

Two properties worth knowing. The service may **lower** a client's cadence and
never raise it – a gate a server could switch off is not a gate. And a refusal
always quotes a positive wait, because "retry after 0 ms" is how a queue becomes
a stampede.

## Layout

| File | |
|---|---|
| `app.py` | the two transports, `/health`, and the load-shedding edge |
| `pipeline.py` | validator → crops → identifier (batched) → colour → resolve → novelty |
| `artefacts.py` | sidecar loading and the refusal |
| `colour.py` | illuminant, CIELAB, CIEDE2000 – **provisional, see docs/12 P3** |
| `shed.py` | the ladder |
| `wire.py` | the framing, mirroring `web/src/transport/protocol.ts` |
| `settings.py` | the environment, and only that |
| `bench/` | the *latency bench* – a different deployable, see its own README |
