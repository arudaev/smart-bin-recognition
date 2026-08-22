# Next session — make a Deggendorf wheelie answer

*Written 2026-08-22 at the end of the session that produced PR #10. Every command
and every path in this file was executed or read before it was written down; the
"verified" notes say which. Paste the whole thing into a fresh agent session.*

---

## The one-line goal

**Today a Deggendorf wheelie resolves to `unknown`. By the end of this session it
resolves to `paper` / `bio` / `residual`, and a person can see it happen.**

Everything else in this file serves that or is explicitly optional.

---

## Ground truth — verify each before relying on it

I have been wrong in this project before, and a prior review caught four real
defects in my last session. **Check these; correct me out loud where I am wrong.**

- **Branch `main` is at `e5fcef3`.** PR #10 (`feat/phase3-ready`) is open, CI
  green, **not merged**. A second branch `feat/fp32-ship-profile` is open and
  **deliberately unmerged**.
- **`docs/submissions/` is untracked and must stay that way.** Do not stage it,
  do not commit it, **do not gitignore it**. It is another session's work.
- **`artifacts/` is gitignored** (`.gitignore:35`). Anything that must survive a
  clean checkout goes in `docs/research/probes/data/`.
- **The dev box is ARM64** (Snapdragon X Elite, no AVX-512 VNNI). The service host
  is x86 Cascade Lake. **Local int8-vs-fp32 benchmarks do not transfer** — the
  same comparison gave 0.59 here and 1.37 there.
- **`data/legacy/pool/` is gitignored except three files**: `adjudication.json`,
  `colour-labels.json`, `colour-sample.json`. `manifest.json` is **not** tracked —
  this bit me once already.
- **Two pytest trees cannot share one invocation.** `python -m pytest ml/tests
  service/tests` fails collection. Run them separately, as CI does. Same for
  `mypy`: `cd ml && mypy src/`, then `cd service && mypy .`.

### The measurement this session turns on

`docs/research/probes/data/P3-rule-axis.json`, reproducible with
`python ml/scripts/probe_rule_axis.py --out <path>`:

| the pack's wheelie rules match on | resolves | correct stream |
|---|---:|---:|
| `lid_color` — **today** | **0 / 119 (0 %)** | **0 / 119 (0 %)** |
| `body_color`, swatches **unchanged** | 114 / 119 (95.8 %) | **92 / 119 (77.3 %)** |
| `body_color` + recalibrated swatches | 119 / 119 | 113 / 119 (95.0 %) |

Truth is `legacy_class` from the archive — human, and independent of the colour
labels. Supporting evidence: `docs/research/12-deggendorf-packaging-evidence.md`
quotes the municipality naming *„die **graue** Restmülltonne, die **braune**
Biotonne und die **blaue** Papiertonne"* — **the bin, not the lid**.

---

## Do these, in this order

### 0 · Start from the right commit — this is the first thing to get right

**Do NOT branch off `main`. Every tool this plan uses is on PR #10 and none of it
is on `main`** — I checked each one:

| needed by | on `main`? |
|---|---|
| `ml/scripts/colour_labels.py` (steps 1, 3) | **no** |
| `ml/scripts/probe_rule_axis.py` (step 2's evidence) | **no** |
| `ml/scripts/probe_detect.py` (step 2's proof) | **no** |
| `ml/scripts/build_dashboard.py` (the PR gate) | **no** |
| `data/legacy/pool/colour-labels.json` (the 160 labels) | **no** |

So do one of these **first**, and say which you did:

- **Preferred: merge PR #10**, then branch off the new `main`. It is CI-green and
  its review response is the top comment on the PR. It ships tooling and evidence,
  and it does **not** claim P3 is closed.
- **Or: branch off `feat/phase3-ready`** and target your PR at that branch. Say so
  explicitly, because it stacks two unmerged PRs.

Then record what is already red before touching anything.

```
python -m pytest ml/tests/ -q
python -m pytest service/tests/ -q
ruff check ml/src ml/scripts ml/tests ml/kaggle service
cd ml && mypy src/ ; cd ../service && mypy . ; cd ..
python ml/scripts/validate_taxonomy.py --locales en
npm --prefix web run verify
npx --prefix web playwright test --config=web/playwright.config.ts
```

**Expected, from `feat/phase3-ready` (or `main` once #10 is merged):** ml
`461 passed, 2 skipped`; service `177 passed`; ruff clean; both mypy clean;
taxonomy clean; web `281 passed`; Playwright `13 passed, 5 skipped`.

*(On unmerged `main` the first two are 456+2 and 172 — if you see those, you are
on the wrong commit and half this plan's tooling is missing.)*

**Playwright needs `npx --prefix web playwright install chromium` once.** The 5
skips are the screenshot spec, which is gated behind `SBR_SHOTS` on purpose.

### 1 · The spot-check — 25 crops, and it gates everything (30 min)

```
python ml/scripts/colour_labels.py spot-check --reviewer alex -n 25
```

**Verified: this runs and serves on `http://127.0.0.1:8766`.** It is a browser
keystroke UI — **a person must do it**, and if the maintainer is not available
**say so and stop treating step 3 as closed**, do not label them yourself again.

Then:

```
python ml/scripts/colour_labels.py score --labeller alex
```

Human rows automatically win over agent rows. **If human and agent disagree on
more than ~4 of 25, stop and re-run the full 160-crop pass** (`--label`) before
step 2 — the whole plan rests on those labels.

### 2 · [D1] Move the wheelie rules onto `body_color` — the big one (1 h)

Edit **four rules** in `data/taxonomy/regions/de-by-deggendorf.json`:
`deg-residual-wheelie`, `deg-paper-wheelie`, `deg-bio-wheelie`,
`deg-packaging-wheelie`. Change `"lid_color"` → `"body_color"`, keep the same
colours and streams, and **add the municipal source citation** to each
(`research/12` has the verbatim quote and the retrieval date).

**Verified feasible with zero code:** `body_color` is already in
`region-pack.schema.json`, already used by `deg-packaging-sack`, and
`RegionPack.resolve` scores by axis count so specificity still works.

**Do not touch** `deg-packaging-sack` or `deg-packaging-wheelie`'s *stream*, and
**do not remove the CONTRADICTED note** — `ml/tests/test_taxonomy.py` fails if it
vanishes, deliberately. `deg-packaging-wheelie` describes a collection that does
not exist (research/12); moving its axis is fine, resolving its truth is D6.

Then prove it end to end:

```
cd service && PYTHONPATH=../ml/src SBR_ARTEFACT_DIR=../artifacts/local \
  SBR_ALLOW_UNGATED=1 SBR_INTRA_OP_THREADS=2 python -m uvicorn app:app --port 8099
# in another shell:
python ml/scripts/probe_detect.py 21f9ddd8_img_4877.jpg 27168d08_img_4659.jpg
```

**Verified: that exact invocation works.** `21f9ddd8_img_4877.jpg` is a `Papier`
wheelie that returns `body_color: blue`, `stream: "unknown"` today. **Paste the
before and after verbatim.** Success is `stream: "paper"`.

### 3 · [D5] The confidence floor, before anyone sees an answer (45 min)

77.3 % correct means **one wheelie in four or five is wrong about where rubbish
goes**. That is the product's worst failure mode and it must not ship unguarded.

Decide and implement one of:
- a ΔE floor on the colour measurement, below which `body_color` is `None` and
  the rule cannot fire (the `unknown` path already exists and is designed), or
- a rule-confidence floor in the resolver, or
- ship at 77 % with the draft-pack banner doing the work.

**Whichever you pick, write down what fraction it converts from *wrong* to
*unknown*** — `probe_rule_axis.py` has the per-error breakdown (3 black-bodied
`paper` bins, 3 `bio` measured grey/black). **A floor that only lowers coverage
without lowering the error rate is not worth having; measure both.**

### 4 · The regression corpus — do this before 3.3, not after (1 h)

`ml/tests/` and `web/src/domain/resolver.test.ts` test the resolver against
**synthetic** packs. Nothing today would catch a real-frame answer changing for
the worse. Freeze the 119 wheelies + 40 igloos with their expected streams as a
fixture, and fail CI on a drop.

**This is what makes steps 2 and 3.3 reversible rather than brave.** Put the
fixture in `docs/research/probes/data/` or `ml/tests/fixtures/` — **not** under
`data/legacy/pool/`, which is gitignored.

### 5 · [D3] The fp32 validator — merge is necessary, not sufficient (2 h)

**Read the memo first — and note it is NOT on `main`.** It lives only on
`feat/fp32-ship-profile`:
`git show feat/fp32-ship-profile:docs/research/FP32-PROFILE-MEMO.md`.
(I checked; a fresh session looking for it in a `main` checkout finds nothing.)
The branch was wrong when first written and is now correct; the memo carries the
correction.

Verified state: against the **real** sidecar plus P13's latency, the branch
returns `may_ship: false` with *"the fp32 ONNX graph for the validator has not
been scored"*. That is correct — `map50_fp32: 0.7524` is **copied from the
PyTorch run** (`"accuracy_is": "copied from the run that measured it, not
measured here"`). Once `accuracy_onnx` is set, `may_ship` flips to `true`.

So: **score the exported fp32 ONNX graph on `test`.**

**Verified feasible, no GPU:** `score_onnx(onnx_path, role=, data=, imgsz=,
split=)` already exists in `ml/src/sbr/export/onnx_export.py:1117`, and
`ml/kaggle/probe_quantisation/` is a **CPU** kernel (`enable_gpu: false`) that
already downloads the pinned pool, calls `build_yolo_tree`, and runs `score_onnx`
on `test` and `val`. Registering a new kernel is: a directory with `script.py` +
`kernel-metadata.json`, one line in `KERNELS` and one in `CONFIGS` in
`ml/scripts/dispatch.py`.

**Kaggle rules that will bite otherwise:** never `kaggle kernels output` (it
downloads everything — use `dispatch.py log`); never build a pool under
`/kaggle/working` (use `/tmp`); GPU kernels must request a T4 via
`machine_shape: "NvidiaTeslaT4"` — **this one needs no GPU, so that risk does not
apply.**

Then merge `feat/fp32-ship-profile`, run `gate.py`, publish the sidecar, and
deploy. **The deploy path is proven**: `SBR_PUBLIC=0 SBR_TAG=v2
service/deploy/cloudrun.sh --no-build` against
`detect@sha256:cd52b20bac39315d77295ea230467cf2deb77a1413b3aa50c813a31bbaa7cebc`.
Anonymous returns 403 by request; authenticated returns 200. **Delete anything
temporary and verify `gcloud run services list` is empty afterwards.**

### 6 · First contact — five people (2 h, and it needs no model)

**The riskiest assumption in this project has never been tested**: that a person
points a phone at a bin instead of reading the sticker on it. It is testable
today — `npm --prefix web run dev` runs the real resolver against the real
Deggendorf pack with fixture frames, no service required.

Write down, before showing anybody: what would make you stop building this.

---

## Explicitly do NOT do these

Each has been measured; the approach is exhausted, not the attempt.

| Do not | Why | Evidence |
|---|---|---|
| Retry lid colour by geometry or add SAM | 0.1966, and **0.5214 even with perfect references**. Lids are visible in 98 % of frames and the band lands on them | `docs/research/probes/P3-colour-measurement.md` |
| Chase 10 concurrent scanners on 2 vCPU | Frame is 49 ms and needs ~25. Shared pool already applied; 384 px worth ~6 ms; crop cap worth 0 at one bin | P12, P13 |
| Try int8 on the validator again | Four probes; best config still misses by 0.0052 | P9, P10, P13 |
| **Move the global `hex_ref`** | One city, one week, one camera; `glass_mixed` is 2 crops of 119. Per-region is the right answer and **is code, not a data edit** — schema has `additionalProperties: false`, `named_colours()` is `lru_cache(maxsize=1)` over the global file, `measure_body_colour` takes no region | verified 2026-08-22 |
| Start phases 4, 5 or 6 | They build on an answer that does not exist yet. Phase 5 additionally rests on **novelty precision ≥ 0.5**, a kill criterion that has **never been measured** (P2 has not run) | `docs/07-roadmap.md` |

---

## House rules that are not negotiable

- **Never state a claim as measured when it is assumed.** Every number carries its
  split and its hardware. A proxy is labelled a proxy.
- **Never loosen a ship gate to make an artefact pass.** `max_accuracy_drop`
  stays `0.02` in every profile.
- **Never assert a disposal rule without a region-pack entry.** `unknown` is a
  designed state — this whole session is about making it fire *less often*, not
  about replacing it with a guess.
- **Never commit to `main`.** Typed branch prefix, PR, Conventional Commits,
  ≤ 72 chars, imperative, lower-case.
- **No AI attribution** in commits. No `Co-Authored-By`, no "Generated with".
- **Stage explicit paths. Never `git add -A`** — other sessions commit here.
- **Taxonomy and pack edits are the maintainer's**, except D1 which this prompt
  authorises explicitly and narrowly (four rules, axis only, citations added).
- Regenerate the dashboard before the PR: `python ml/scripts/build_dashboard.py
  --out docs/dashboard.html`. **CI fails if it is stale.** Use `--snapshot` only
  when a gate sidecar under `artifacts/` has actually changed.

## Money

Cloud Run at this scale is cents and is approved. **One** GCE measurement run is
pre-approved at **USD 1.00 / 2 h** via `service/deploy/measure-on-gce.sh`
(`ARM=fp32` for the paired arm) — destroy on every exit path and verify the
instance and disk lists are empty. Billing account `01195D-5CDD92-701A09` is
**closed and must never be linked**; never touch project `exportease-405510`;
never measure concurrency against Cloud Run. **Anything else with a price: do not
buy it — record it with the current price and its source.** HF PRO is USD 9/month
and gates the private dataset viewer; it is recorded as blocked, not bought.

## Definition of done

1. A real Deggendorf `Papier` wheelie returns `stream: "paper"` — **verbatim
   `/detect` before and after**, in the PR.
2. The confidence floor is decided, implemented, and its effect on *wrong* versus
   *unknown* is measured, not asserted.
3. A regression corpus fails CI if a real-frame answer degrades.
4. P3 is closed on **human** labels, or explicitly still open and labelled
   PROVISIONAL everywhere.
5. The fp32 graph is scored; `may_ship` is `true` or the reason it is not is a
   measurement.
6. `docs/submissions/` untouched. Nothing on `main`. CI green on final HEAD,
   confirmed with `gh pr checks` — note `web.yml` is path-filtered, so a docs-only
   HEAD shows no `web` run; confirm the run exists rather than reading absence as
   green.

## How to report

Lead with anything that contradicted this prompt. Then what landed, what did not,
and what is staged for a decision. **Do not soften a failed measurement into a
pass, and do not describe as verified anything you inferred.** If the spot-check
could not happen because no human was available, say that first — it changes what
every other number on the page is worth.
