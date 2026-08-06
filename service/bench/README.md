---
title: SBR Latency Bench
emoji: ⏱️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# SBR latency bench

The ship gate's measuring instrument. It exists because
`ml/configs/validator.yaml` and `ml/configs/identifier.yaml` state their latency
budgets **on service CPU** — validator ≤ 50 ms @ 448, identifier ≤ 25 ms per
crop — and a number measured anywhere else is not evidence for them.

So this runs where the service runs: a free Hugging Face Space, Docker SDK,
**CPU-basic, 2 vCPU**. onnxruntime is pinned to those two threads, and one
uvicorn worker holds them.

## Using it

```
GET /bench?role=validator&version=1&repo=arudaev/smart-bin-detect&revision=<sha>
```

Returns p50 / p95 / mean / min / max in milliseconds, plus a `hardware` block
naming the CPU, the core count, the thread count and the onnxruntime version.
Every number this project publishes carries that block with it.

You do not normally call it by hand. `ml/scripts/gate.py` calls it, writes the
result into the model's sidecar, re-runs `check_gates`, and exits non-zero if a
gate fails.

## What it does not do

- It does not serve detections. That is `service/`, phase 3 — this is the
  skeleton that proves the boot path, the pinned-revision pull and the sidecar
  contract, and nothing more.
- It does not decide anything. It measures; `check_gates` decides.
- It does not accept arbitrary repos. `ALLOWED_REPOS` is the project's own two
  artefact repos, because the Space is public and this loads an ONNX graph.

## Input

Synthetic, seeded. int8 QDQ convolution latency does not depend on pixel values,
so a real photograph would buy realism nobody can use and give the bench a
reason to hold image data it has none.

## Deploying

```bash
huggingface-cli repo create sbr-bench --type space --space_sdk docker
git clone https://huggingface.co/spaces/arudaev/sbr-bench
cp service/bench/* sbr-bench/ && cd sbr-bench && git add -A && git commit -m "bench" && git push
```

Keep it on CPU-basic. Upgrading the hardware would make the gate pass by
measuring something the users will never run on.
