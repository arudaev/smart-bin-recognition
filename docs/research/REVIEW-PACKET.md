# Review packet — 2026-08-22

*Committed, not untracked, so a second model can be pointed at a path in the repo
rather than a paste. Branch `feat/phase3-ready`, eleven commits off `e5fcef3`.*

**`codex` is not on PATH on this machine.** `command -v codex` and `where codex`
both return nothing (*"Could not find files for the given pattern(s)"*), so the
self-review step did not run and this packet stands on its own. A prior review's
factual note that codex *was* available was checked twice and is wrong.

**How to use this.** Every claim below is paired with the exact command or file
that verifies it. Nothing here asks to be believed. The last section is the part
worth attacking first: it is what I am least sure about, written as questions.

---

## 1. Claims about measurements

| # | Claim | Verify with |
|---|---|---|
| 1.1 | fp32 validator is **24.605 ms** p50, int8 **17.921 ms**, on `representative: true` hardware, arms alternated on one instance | `python -c "import json;d=json.load(open('docs/research/probes/data/P13-gce-latency-paired.json'));print({k:v['median_latency_ms'] for k,v in d['formats'].items()}, d['hardware']['representative'], d['ratio'])"` |
| 1.2 | fp32 costs **one** concurrent scanner: 5 → 4 at one bin | `python -c "import json;[print(f,json.load(open(f'docs/research/probes/data/P13-gce-loadtest-1bin-{f}.json'))['concurrent_scanners_within_budget']) for f in ('int8','fp32')]"` |
| 1.3 | The int8 arm **reproduced P12** on a different VM (17.921 vs 18.252) | compare 1.1 against `docs/research/probes/data/P12-gce-latency.json` |
| 1.4 | The measuring host had **AVX-512 VNNI**, which is why the local ARM64 ratio did not transfer | `cat docs/research/probes/data/P13-gce-host.txt` |
| 1.5 | The local triage ratio was **0.5917** on ARM64 — fp32 *faster* — and is recorded as non-transferable | `python -c "import json;d=json.load(open('docs/research/probes/data/P13-fp32-viability.json'));print(d['ratio']['paired_median'], d['architecture'], d['ratio_transferability'][:80])"` |
| 1.6 | P3 body agreement **0.5625**, lid **0.1966**, lid visible in **98.3 %** of scored wheelies | `python -c "import json;d=json.load(open('docs/research/probes/data/P3-colour-measurement.json'));print(d['body']['agreement'], d['lid']['agreement'], d['lid']['lid_visible_fraction'])"` |
| 1.7 | Recalibrated references take body to **0.9125**, lid only to **0.5214**, leave-one-**cluster**-out over 99 groups | `python -c "import json;print(json.load(open('docs/research/probes/data/P3-colour-measurement.json'))['reference_audit']['if_the_references_were_recalibrated'])"` |
| 1.8 | Real green bins measure nearer the **`metal`** swatch than `green` | same file, `reference_audit.centroids.green.nearest_reference_to_the_measured_centroid` |
| 1.9 | Illuminant normalisation **loses** to naive sampling here | same file, `body.agreement` — compare `centre` against `centre_shades_of_gray_p6` |

**The reproducible ones.** `python ml/scripts/probe_fp32_latency.py --out /tmp/x.json`
re-runs the local triage; `python ml/scripts/colour_labels.py score` re-runs all of
P3's scoring from the committed labels. Both are deterministic apart from timing.

## 2. Claims about state

| # | Claim | Verify with |
|---|---|---|
| 2.1 | The published identifier sidecar now reads `may_ship: true` with the **canonical run-2** latency | `curl -sL https://huggingface.co/arudaev/smart-bin-detect/resolve/main/v1/identifier-v1.json \| python -c "import json,sys;d=json.load(sys.stdin);print(d['gate_result'],d['p95_latency_ms'])"` → `11.409` |
| 2.2 | The graph it describes is **byte-identical** to the local one | `sha256sum artifacts/local/identifier-v1.onnx` → `cf2f3376…` |
| 2.3 | The model repo now has a card with real metadata (it had **none**) | `curl -s https://huggingface.co/api/models/arudaev/smart-bin-detect \| python -c "import json,sys;print(list(json.load(sys.stdin)['cardData']))"` |
| 2.4 | The public dataset **viewer builds** — three configs, nothing failed | `curl -s "https://datasets-server.huggingface.co/is-valid?dataset=arudaev/smart-bin-detect"` → `viewer: true` |
| 2.5 | …with 370 / 1 110 / 17 474 rows and a clean single `image` feature | `curl -s "https://datasets-server.huggingface.co/size?dataset=arudaev/smart-bin-detect"` |
| 2.6 | A production-equivalent private Cloud Run deploy **refuses to start**, on the gate | the log quoted in §3 below; re-runnable with `SBR_PUBLIC=0 SBR_TAG=v2 service/deploy/cloudrun.sh --no-build` |
| 2.7 | Nothing is left running anywhere | `gcloud run services list --project smart-bin-recognition --region europe-west3` and `gcloud compute instances list --project smart-bin-recognition` → both empty |
| 2.8 | `docs/submissions/` untouched | `git status --short` → still `??` |
| 2.9 | Nothing on `main` | `git log --oneline main -1` → `e5fcef3` |

## 3. The deployment, verbatim

**Production-equivalent, private, no `SBR_ALLOW_UNGATED`:**

```
artefacts.UngatedArtefactError: validator v1 from arudaev/smart-bin-detect@main
has not passed its ship gates and will not be served.
failures: int8 quantisation cost 0.727 map50 (max 0.02).
```

**Temporary private smoke revision** (`SBR_ALLOW_UNGATED=1`, deleted afterwards,
`gcloud run services list` now empty) — infrastructure only:

- anonymous `GET /health` → **HTTP 403**, `POST /detect` → **HTTP 403**, both by
  making the request rather than reading a flag
- authenticated `GET /health` → **200**, `gated: false`,
  `identifier.may_ship: true` (which is the sidecar published in 2.1, read back
  off a live service)
- authenticated `POST /detect` → **200** on real Deggendorf frames

**Image:** `europe-west3-docker.pkg.dev/smart-bin-recognition/sbr/detect@sha256:cd52b20bac39315d77295ea230467cf2deb77a1413b3aa50c813a31bbaa7cebc`

**The public step is blocked and was not forced.** `web/src/transport/rest.ts`
sends no `Authorization` header, so the client needs a *public* service; a public
service serving disposal answers needs a validator that genuinely passes;
`SBR_ALLOW_UNGATED=1` was **not** used to reach a public URL.

## 4. The `/detect` evidence, before and after

There is no "after". P3's pre-registered rule said **do not wire the lid in**, so
the response is unchanged by design:

```json
{ "form_factor": "wheelie_large", "identifier_conf": 0.9961,
  "body_color": "blue", "lid_color": null,
  "stream": "unknown", "stream_conf": 0.0, "local_name": null }
```

A `Papier` wheelie, `body_color: blue` — the exact colour `deg-paper-wheelie`
looks for — resolving to `unknown`, because the rule reads the *lid*. The glass
path answers (`glass_mixed` / "Glascontainer"). **This is the measured reason the
definition-of-done item was not met, not a failure to attempt it.**

One incidental observation worth a reviewer's eye: the deployed int8 validator
returns `validator_conf: 1.7864`. A sigmoid-headed detector cannot exceed 1.0.
That is further evidence the int8 graph is broken rather than merely weak, and it
is **not** currently written up anywhere as a finding.

## 5. Things a prior review got wrong, checked

Recorded because they were nearly acted on:

- **"`codex` is on PATH"** — it is not; checked twice.
- **"`detect:v2` exists"** (before this run) — the registry had exactly `latest`
  and `v1`. `v2` exists *now* because this run built it.
- **"the manifests are JSONL"** — `legacy/manifest.json` is a single JSON
  *object*. The conclusion drawn from it (the viewer cannot auto-detect the
  layout) was right anyway.
- **"a 25-image human spot-check after scoring does not repair the
  circularity"** — there is no circularity: the sampler is a fixed geometric rule
  with no parameter fitted to the labels. The real risk is **labeller bias** —
  my colour reads could be wrong in the same direction as the sampler's — and the
  conclusion (P3 must not close on agent labels) is right for that reason
  instead. Adopted.

Things the same review got **right**, all verified and all acted on: the Cloud
Run env-var gap, the GCE harness not staging artefacts, the 92-vs-121 cluster
count, publishing the repudiated run's sidecar, the dashboard's dependence on
gitignored `artifacts/`, Playwright's inability to prove the camera fix, and the
illuminant coming from the whole frame.

---

## 6. What I am least sure about — attack these first

1. **Are 160 agent-written colour labels good enough to justify not wiring the
   lid in?** The verdict rests on 0.1966 against a 0.60 floor — a gap so wide
   that plausible labelling error does not close it — but I labelled from
   260-pixel contact-sheet tiles, and human colour constancy discounts an
   illuminant far more aggressively than the algorithm does. **Is some of that
   0.5625 body gap my perception rather than the measurement's?**

2. **Is `--scan-media-block-start: 50%` right, or should the tablet camera pane
   keep the frame's full aspect instead of centre-cropping it?** Markers position
   inside the aspect box, so correctness is preserved either way. I chose even
   clipping over bottom-only clipping. It is a design call I made alone.

3. **Does `concurrent_scanners_at_1_bin` belong on a gate profile at all?** I put
   it there so a format's cost cannot live only in a document. It may belong in
   `targets` (reported) rather than `gates` (enforced). Named in the memo as the
   part most likely to be wrong.

4. **The dashboard's two-tier rule.** A probe file contributes a headline number
   only if it matches a recognised shape. **Is shape-sniffing better than
   requiring every probe to declare a `dashboard` block?** Sniffing means a new
   probe works with no edit; declaring means it is explicit. I chose sniffing
   plus an opt-in override, and I am not certain that is the right default.

5. **Was the temporary ungated private Cloud Run revision within authorisation?**
   The instruction prohibited `SBR_ALLOW_UNGATED=1` on a **public** URL. I read a
   private, authenticated-only, immediately-deleted revision as outside that
   prohibition and inside "deploy privately and verify it". **If that reading is
   wrong, the revision should not have existed** — it is deleted either way, and
   nothing it proved depends on serving a real user.

6. ~~`web/e2e/shots.spec.ts` runs in the default suite.~~ **Found while writing
   this packet and fixed** — it is now `test.skip` unless `SBR_SHOTS` is set, so
   CI runs 13 specs and skips the 5 screenshot ones. A screenshot is evidence for
   a human, not a gate. Left here because the packet is meant to record what a
   reviewer would have caught.

7. **P13's fp32 measurement is 448, one bin, Cascade Lake.** At six bins neither
   format was measured, and the PRD calls a bank of six a normal input. **The
   recommendation may not survive a six-bin measurement**, and I did not take
   one.
