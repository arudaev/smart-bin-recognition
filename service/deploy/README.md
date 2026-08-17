# Deploying the inference service

> **Nothing is serving right now, and that is correct.** The service refuses to
> load an artefact whose sidecar does not say `may_ship`, no such artefact
> exists yet, so there is no Cloud Run service. Everything around it is built
> and paid for: project, billing, budget alert, registry, and an `amd64` image.
> Deploying once a model exists is one command.

---

## What exists today

| | |
|---|---|
| Project | `smart-bin-recognition` (number `1086239258147`) |
| Billing | `01F3FA-432CE4-B00D5D` – *My Billing Account 1*, open |
| Budget | €5/month, alerts at 50 %, 90 %, 100 % of actual and 100 % of forecast |
| Region | `europe-west3` (Frankfurt) |
| Registry | `europe-west3-docker.pkg.dev/smart-bin-recognition/sbr` |
| Image | `detect:v1` and `detect:latest`, built `2026-08-16`, `linux/amd64` |
| Cloud Run service | **none** – see above |

**Billing account `01195D-5CDD92-701A09` is closed and must never be linked.**
It still appears in `gcloud billing accounts list` with `OPEN: False`. Linking a
closed account does not fail loudly; it leaves a project that cannot use any
paid API, with an error that points at the API rather than at the billing.

`exportease-405510` on this profile is an unrelated project. Nothing here
touches it.

## Deploy

```bash
service/deploy/cloudrun.sh              # build on Cloud Build, then deploy
service/deploy/cloudrun.sh --no-build   # deploy the image already in the registry
```

It will not come up until a validator artefact passes its gates. That is the
whole point of `artefacts.py`, and a failed startup with
`ArtefactMissingError` or `UngatedArtefactError` in the log is the gate working,
not a broken deployment.

## Why each flag

| Flag | Why, and what changing it costs |
|---|---|
| `--region europe-west3` | Frankfurt: nearest region to Deggendorf, and data stays in the EU. Moving it adds a round trip to every frame, and a frame is already 66–77 ms of CPU. |
| `--cpu 2` | **The entire cost model is arithmetic about two vCPU** ([docs/05 § 3](../../docs/05-cost-model.md)). Change this and every latency and concurrency number this project has published stops being about the thing that is running. |
| `--memory 2Gi` | Two onnxruntime sessions plus a decoded frame. 1Gi OOMs on the first six-bin frame. |
| `--min-instances 0` | **Decides the billing model.** See below. |
| `--max-instances 1` | The hard cost ceiling. See the note on what it means for capacity. |
| `--concurrency 1` | The container holds two ONNX sessions pinned to both vCPUs. A second concurrent request does not go twice as fast, it halves the speed of the first – measured, not assumed. |
| `--timeout 60s` | A frame is under a second. A minute is generous for a cold start and still bounds a stuck request. |
| `--port 8080` | Cloud Run injects `PORT`; the Dockerfile honours it and falls back to 8080. |

### The request-versus-instance trap

Cloud Run bills two ways and the difference is the whole free tier.

- **Request-based** – CPU is charged only while a request is in flight. The free
  tier is 2 M requests, 180 000 vCPU-seconds and 360 000 GiB-seconds a month.
- **Instance-based** – idle instances bill CPU and memory too. One always-on
  2-vCPU instance consumes the entire monthly vCPU-second allowance in **about
  twenty-five hours**.

You get request-based by scaling to zero with no always-allocated CPU. Two
changes silently switch you to instance-based:

1. `--min-instances 1` or higher.
2. `--no-cpu-throttling` (CPU always allocated).

**This is also why `POST /detect` is the deployed path and the WebSocket is
not.** A held-open socket forces instance-based billing by construction. The
socket ships in the image and works; the client is pointed at `VITE_DETECT_URL`.
The result lock means a scan is about fifteen frames either way
([01 § 2](../../docs/01-architecture.md#which-inference-host)).

### What `--max-instances 1` actually means

With `--concurrency 1` as well, the deployment serves **one frame at a time in
total**. That is a deliberate cost ceiling and it is what was asked for, but be
clear about the consequence: this configuration is a **demonstrator, not a
capacity**. A second simultaneous scanner queues behind the first.

It is also why the concurrency measurement in
[docs/05 § 3](../../docs/05-cost-model.md) is taken against
`docker run --cpus 2` and never here. Cloud Run autoscales; measuring
concurrency on it measures Google's scheduler rather than the two vCPU the cost
model prices. Raising `--max-instances` raises both the ceiling and the bill,
and the free tier is the budget.

## Who can reach it — check the request, not the flag

**`--no-allow-unauthenticated` does not revoke an existing public binding.**

Found on 2026-08-16, deploying a private smoke-test revision over a service
whose first (failed) deploy had used `--allow-unauthenticated`:

- `gcloud run deploy --no-allow-unauthenticated` reported `Setting IAM Policy…done`
- `gcloud run services get-iam-policy` returned **no bindings at all**
- `gcloud run services remove-iam-policy-binding … --member=allUsers` answered
  **"Policy binding with the specified principal, role, and condition not found"**
- and an anonymous `curl $URL/health` returned **HTTP 200 with a full body**

Every reading gcloud offered said private. The service was public. `cloudrun.sh`
now finishes by making an unauthenticated request and telling you what actually
happened; if a revision is meant to be private and answers 200, **delete the
service** rather than trying to patch the policy.

The production service is *intended* to be public – the Vercel client calls it
cross-origin with no credentials – so narrow it at the edge instead:

```bash
--set-env-vars SBR_ALLOWED_ORIGINS=https://<the-vercel-domain>
```

`*` is the default and is not what a deployed service should carry.

## Never deploy an ungated model publicly

`SBR_ALLOW_UNGATED=1` makes the service serve an artefact that has not passed
its ship gates. It exists so latency and concurrency can be measured **before a
model is trained**, and `/health` reports `gated: false` for as long as it is on.

It must not be combined with a public URL. An untrained graph answers
confidently about objects that are not bins, and this product's worst failure is
being confidently wrong. If Cloud Run itself needs verifying before a model
exists, deploy the ungated image **with authentication required**, smoke-test it
with `gcloud auth print-identity-token`, record the result, and delete the
revision – then confirm with an anonymous request that it is gone.

## Rollback

```bash
gcloud run revisions list --service sbr-detect --region europe-west3 --project smart-bin-recognition
gcloud run services update-traffic sbr-detect --region europe-west3 \
  --project smart-bin-recognition --to-revisions <REVISION>=100
```

Traffic splitting rather than redeploying: the previous revision is still there
and shifting traffic back takes seconds, where a rebuild takes minutes and might
not reproduce the image.

## Reading free-tier usage

```bash
# What has actually been billed. Costs lag by up to a day.
gcloud billing accounts describe 01F3FA-432CE4-B00D5D

# The budget and its thresholds
gcloud billing budgets list --billing-account=01F3FA-432CE4-B00D5D

# Requests and CPU, per revision
gcloud monitoring dashboards list --project smart-bin-recognition
```

The console's *Billing → Reports*, filtered to this project and grouped by SKU,
is the honest view: it separates `CPU Allocation Time` from `Request Count`, and
seeing CPU allocation accrue while nobody is scanning is the signal that the
service has slipped into instance-based billing.

## Teardown

```bash
gcloud run services delete sbr-detect --region europe-west3 --project smart-bin-recognition
gcloud artifacts repositories delete sbr --location europe-west3 --project smart-bin-recognition
gcloud billing projects unlink smart-bin-recognition
gcloud projects delete smart-bin-recognition
```

Deleting the project is the only thing that guarantees nothing bills. It is
recoverable for 30 days. Unlink billing first if you want to keep the project
but be certain it cannot spend.

## The build

```bash
gcloud builds submit --config service/deploy/cloudbuild.yaml \
  --project smart-bin-recognition --region europe-west3 \
  --substitutions _TAG=v1 .
```

Two things about it are load-bearing.

**Build on Cloud Build, not locally.** Cloud Run is `amd64`. This project is
developed on a Snapdragon X1E80100, where `docker build` produces an `arm64`
image that Cloud Run rejects with a manifest error naming the platform rather
than the cause.

**`.gcloudignore` is a deny-list-first file, and that matters.** gcloud reads
`.gitignore` *only when there is no `.gcloudignore`*. Adding one made gcloud stop
reading `.gitignore` entirely, so `cv_garbage/` – 3.8 GB, git-ignored for months
– silently became part of the build context and the upload stalled. The file now
denies everything at the root and re-includes the three trees the Dockerfile
copies. Context after the fix: **84 files, 616 KiB, 40-second build.**
