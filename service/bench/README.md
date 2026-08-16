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

> **Parked, 2026-08-15.** This cannot currently be deployed. Creating a Docker
> Space returns `402 Payment Required`:
>
> > Static Spaces are free for everyone, but hosting Gradio and Docker Spaces on
> > free cpu-basic requires a PRO subscription.
>
> The ship gate is measured on `ml/kaggle/bench_latency/` instead — a Kaggle CPU
> kernel with onnxruntime pinned to two threads, which is free and x86 but a
> **proxy** for a service container rather than one. `gate.py` demands
> `--allow-unrepresentative-hardware` to decide on it.
>
> This directory stays because it is still correct, and because it is the
> skeleton `service/` needs in phase 3: it boots, pulls a pinned revision, and
> reads the sidecar rather than knowing anything about the model. Deploy it the
> moment there is a host — HF PRO at USD 9/month, Google Cloud Run, or anything
> else with 2 vCPU — and `gate.py --source space` will accept its numbers
> without argument.
>
> **This also invalidates docs/05 § 3's "A free Hugging Face Space gives 2 vCPU".**
> The concurrency arithmetic built on it survives only once a host is named.

The ship gate's measuring instrument. It exists because
`ml/configs/validator.yaml` and `ml/configs/identifier.yaml` state their latency
budgets **on service CPU** — validator ≤ 50 ms @ 448, identifier ≤ 25 ms per
crop — and a number measured anywhere else is not evidence for them.

It is built to run where the service runs: Docker SDK, **CPU-basic, 2 vCPU**,
onnxruntime pinned to those two threads, one uvicorn worker holding them.

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
