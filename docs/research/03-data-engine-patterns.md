# 03 – Data-engine patterns

*2026-08-16. Feeds docs/04 § 2 and docs/12.*

Prompted by a read of Flock Safety's ALPR pipeline. The question is not "should
we build that" — we should not — but **which of its properties are affordable for
one person, and which are the expensive half.**

---

## 1. What Flock actually does, and what it costs

Flock runs two connected pipelines:

```
PRODUCTION   road → camera → edge CV → plate + vehicle metadata → cloud → search
DEVELOPMENT  captured data → dataset → train → holdout eval → compare to production → deploy
```

The development half was Kubeflow Pipelines on S3; in 2026 they replaced it with
**Traintrack**, an internal Python system that treats ML development as one
cacheable dependency DAG — Bazel for training. Experiments are YAML in git, jobs
run in Docker, artefacts are deterministically cached, and changing one piece of
training data reruns only the affected downstream nodes. Remote execution is
Traintrack → Prefect → AWS Batch → S3.

**That is a team's worth of infrastructure**, built because their DAG is large
enough that partial reruns save real money. Ours is: import → split → train →
export → bench. Five nodes. A cache would save minutes.

Two caveats worth recording, because the public account is not complete: Flock's
documentation does not clearly state which models run on-device versus in the
cloud per camera generation, so the edge-inference half should not be treated as
a proven pattern to copy. And their scale — continuous capture from fixed
hardware — inverts our data problem entirely. They have too much data and need to
sample it; we have 1 480 positives and need more.

## 2. The three properties worth stealing, all cheap

**1 — Candidate-versus-production comparison as a gate.** Flock explicitly
generates predictions against holdout sets, calculates metrics, and *compares new
models against the current production baseline* before deployment. We have ship
gates (latency, int8 drop) but **no regression gate**: nothing stops v2 from
being worse than v1 on the frozen set as long as it is fast and quantises
cleanly. This is the single most valuable idea here and it costs one comparison
against a pinned sidecar.

**2 — Structured metadata as the output, not images.** Flock's product insight is
that turning images into `plate + make + colour + type + time + place` makes
millions of photographs *searchable* instead of merely stored. Our analogue
already exists — `(form_factor, body_colour, lid_colour, geohash)` — which is
reassurance that the taxonomy's three axes (docs/02 § 1) are the right shape.

**3 — Config-as-code experiments in git.** Already done: `ml/configs/*.yaml` with
`_defaults_` inheritance and the no-hard-coding convention. This is the property
Traintrack is *built around*, and we have it for free.

## 3. What not to steal

| Not this | Why |
|---|---|
| A bespoke cacheable DAG orchestrator | Five nodes. The cache saves minutes; the orchestrator costs weeks |
| Prefect / AWS Batch remote execution | Kaggle dispatch already is this, free, and already works |
| Edge inference | Directly contradicts docs/01 § 1, which was decided deliberately |
| Continuous capture | Our privacy story (docs/01 § 7) is the opposite by design |

## 4. If a cache is ever wanted, what it costs

For reference, not for now. [ZenML](https://www.zenml.io/blog/mlflow-vs-airflow)
uses content- and configuration-derived hash cache keys to decide when a step
output can be reused, versions every artefact and records lineage. DVC does the
same over git. Both are days of adoption, not weeks.

The cheaper 80%: our pool manifests already carry per-frame provenance, and the
dataset is pinned by HF revision. A hash of `(dataset revision, config, code
revision)` written into the sidecar gives most of the reproducibility benefit
with none of the orchestration.

## 5. Curation tooling is the gap worth filling

[FiftyOne](https://docs.voxel51.com/user_guide/brain.html) is open source and
does, out of the box, most of docs/04 § 3's steps [1] and [5]: embedding
computation, near-duplicate detection, clustering for batch annotation, and
"mistakenness" scoring against a predictions field. Its
[clustering plugin](https://docs.voxel51.com/tutorials/clustering.html) is
explicitly aimed at "pre-labeling groups for human annotators", which is exactly
what docs/04 § 4 describes building by hand.

`ml/scripts/adjudicate.py` already exists and works, so this is not a rewrite
argument. It is an argument for **not building `autolabel/dedupe.py` and
`autolabel/cluster.py` from scratch** when a maintained library does it.

## 6. What this changes for us

| Change | Where |
|---|---|
| Add a **regression gate**: no promotion without beating the deployed sidecar on the frozen set | docs/04 § 7, `onnx_export.py` (v2 — noted, not built now) |
| Rename "self-improvement loop"/"flywheel" → **human-reviewed improvement loop** | docs/04 § 2, docs/07 phase 5 |
| Record that the DAG-cache pattern is deliberately declined, with the reason | this note |
| Evaluate FiftyOne for steps [1] and [5] before writing `autolabel/dedupe.py` and `cluster.py` | docs/04 § 3, § 8 |
| Note that Flock's data problem is the inverse of ours — sampling abundance vs escaping scarcity | this note |

## Sources

- Flock Safety engineering write-ups on Traintrack and their ML pipeline (as summarised 2026-08-16; primary sources are Flock's own engineering blog)
- [ZenML: caching and lineage](https://www.zenml.io/blog/mlflow-vs-airflow) · [Flyte vs Airflow vs ZenML](https://www.zenml.io/blog/flyte-vs-airflow)
- [FiftyOne Brain](https://docs.voxel51.com/user_guide/brain.html) · [clustering with embeddings](https://docs.voxel51.com/tutorials/clustering.html) · [dataset curation skill](https://github.com/voxel51/fiftyone-skills/blob/main/skills/fiftyone-dataset-curation/SKILL.md)
