# 08 – Video as the capture format

*2026-08-16. Feeds docs/04 § 3 and § 5, docs/07 phase 2 and phase 6, and
`ml/src/sbr/dataset/prepare.py`.*

The pattern: submit an hour of walking video, and a pipeline picks the frames
worth keeping, boxes and tracks every object across them, pulls location and time
from the container metadata, and emits training data. Instead of photographing
bins one at a time, you **walk past them**.

This is worth taking seriously, because it addresses more of this project's
actual blockers than anything else currently on the table.

---

## 1. What it solves here

| Blocker today | What video does to it |
|---|---|
| **No geographic holdout.** Every subset carries `region_id: "unknown"`, so `holdout_region` is empty and the phase-2 hypothesis is **untestable** (docs/04 § 5) | Video containers carry GPS and timestamp. `region_id` becomes **real**. This is the one that matters most — it converts the central unanswerable question into an answerable one |
| **Zero multi-bin frames in legacy**, 92 % single-bin, and the PRD calls a bank of six normal | Walk along a bank of containers and every frame has 4+ bins, from the distance a person actually stands at |
| **Seven of ten form factors have no data at all** | Find one textile bank, film it for thirty seconds, get hundreds of frames from every angle |
| **One viewpoint per bin.** The identifier needs viewpoint diversity and the legacy archive is one centred shot per visit | A walk-around is viewpoint diversity by construction — near, far, oblique, occluded |
| **Adjudication is 403 individual decisions** | A human labels a **track**, not a frame. One decision covers every frame that object appears in |

That last row inverts the economics of the human pass, which is the only
irreplaceable step in the whole pipeline (docs/04 § 4). Forty tracks is forty
decisions covering thousands of frames.

## 2. SAM 3 is the right tool, and it is the reason this is newly practical

[SAM 3](https://arxiv.org/pdf/2511.16719) detects, segments **and tracks** from a
concept prompt, in images *and video*, returning consistent IDs per instance.
That is the whole of steps [2], [3] and the tracking this needs, in one call:

```
video → keyframe selection → SAM 3 "wheelie bin . glass bank . textile bank ."
                           → per-object TRACKS with masks, stable across frames
                           → one human decision per track
```

Before SAM 3 this needed a detector, a segmenter and a tracker wired together.
Now it does not, which is why this pattern is worth adopting in 2026 and was not
obviously worth it in 2024.

## 3. The five ways this goes wrong

Enthusiasm here is cheap and the failure modes are quiet. Ordered by how much
damage they do.

### 3.1 Correlated leakage — the one that destroys the evaluation

Consecutive frames of one bin are near-identical. **If they straddle a split, the
test set is the training set**, mAP goes to 0.99, and nothing says so. This is
exactly the predecessor's failure (docs/08 § 7.3) reproduced at a hundred times
the scale, and it is *invisible* — the numbers get better, not worse.

The grouping key must be the **track** (one physical object through one video),
never the frame. `prepare.py` now derives `capture_cluster` from
`video_id`/`track_id`, **refuses** a frame declaring `source: video` with no
grouping key, and warns when frames-per-group falls near 1 — because a
group-aware split where every frame is its own group *is* a random split.

### 3.2 Effective sample size is tracks, not frames

An hour at 30 fps is 108 000 frames and perhaps forty bins. The dataset would
*look* a hundred times larger and carry almost no new information. **Report
counts as `tracks / distinct objects / videos / locations`, never as a frame
total**, or every later ratio in docs/04 § 1 becomes meaningless.

Aggressive keyframe selection is not an optimisation, it is the point: sharpness,
pose change, and embedding distance from what is already kept.

### 3.3 Label error propagates along a track

One wrong track label is wrong in every frame of that track — but symmetrically,
one human correction fixes every frame. Net strongly positive, *provided
adjudication is per-track*. Adjudicating per-frame gets the downside and not the
upside.

### 3.4 GPS is a privacy problem, not just a metadata win

Full-precision GPS in video metadata is exactly what docs/01 § 7 refuses to
collect from users (geohash-6, ~1.2 km). Two different cases, and they must not
be conflated:

- **Maintainer capture** — deliberate, consented, own device. Full GPS is fine
  internally; it is reduced to `region_id` before anything is published.
- **User-contributed video** — should be **out of scope for v1**. It multiplies
  every consent, moderation and face/plate problem in docs/03 § 4 by the frame
  count, and there is no moderation capacity for it.

### 3.5 Dwell time becomes class imbalance

You film the interesting bin longer, so it dominates the dataset in proportion to
how long you stood there. Cap frames per track, and balance at the **track**
level rather than the frame level.

## 4. Why this does not change the architecture

Nothing above touches the three decisions in AGENTS.md. Video is a **capture
format for training data**, entirely offline. The product still streams gated
single frames from a phone to a service; the client is unchanged; the wire
contract is unchanged. This is a change to how the dataset is built, not to what
the system is.

That is also why it is safe to adopt: it fails cheaply. If the pipeline produces
poor tracks, we have lost some walking and a Kaggle kernel.

## 5. What this changes for us

| Change | Where |
|---|---|
| **Track-grouped splitting**, with video provenance refused when it has no grouping key, and a random-split warning | `prepare.py` — **done**, `MIN_FRAMES_PER_GROUP` |
| Video as the primary capture format for the second-city round, since it carries a real `region_id` | docs/07 phase 2, phase 6 |
| Adjudication becomes **per track**, which is what makes the human pass affordable | docs/04 § 4 |
| Dataset counts reported as tracks/objects/videos/locations, never as frames | docs/04 § 5 |
| SAM 3 concept-prompted tracking replaces detector + segmenter + tracker | docs/04 § 3 |
| User-contributed video is **out of scope for v1**, with the reason recorded | docs/03 § 4 |
| Add probe **P7** before building any of it | docs/12 |

## Sources

- [SAM 3: Segment Anything with Concepts](https://arxiv.org/pdf/2511.16719) — concept prompts, video tracking, stable instance IDs
- [Ultralytics SAM 3 docs](https://docs.ultralytics.com/models/sam-3)
- [FiftyOne clustering and dataset curation](https://docs.voxel51.com/tutorials/clustering.html) — near-duplicate removal at the scale video produces
