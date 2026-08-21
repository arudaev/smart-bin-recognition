"""Discipline tests for the Kaggle kernels.

These scripts cannot be imported – they carry injection sentinels and expect a
GPU – and they are the most expensive thing in the repo to get wrong: a mistake
costs a dispatch, a queue wait, and a GPU hour before it surfaces. So they are
checked as source.

Every assertion here corresponds to something that was actually wrong:

- the two scripts were **byte-identical**, both copies of an older single-model
  script, so "training the identifier" trained a second detector;
- both constructed ``ExportReport(version=…)`` without ``role``, which is the
  first field with no default, so every run would have raised ``TypeError``
  after training finished and before anything was uploaded;
- both took the ten form factors from the taxonomy, including the validator,
  which has one class;
- ``train_validator`` pointed at the kernel id ``sbr-train-detector``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
KAGGLE = ML_ROOT / "kaggle"
KERNELS = ("train_validator", "train_identifier")
CPU_KERNELS = ("build_negatives", "bench_latency", "probe_latency", "probe_quantisation")

#: The diagnostic ladder from docs/07 phase 2. Each rung changes exactly one
#: thing from the one before it, which is the only way to find a boundary when
#: the platform returns an empty log.
SMOKE_KERNELS = (
    "smoke_bare",         # no bundle, no dataset, no GPU
    "smoke_plain",        # + the injected bundle
    "smoke_secrets",      # + the attached secrets dataset
    "smoke_usersecret",   # a Kaggle Secret instead - does it bind to an API push?
    "smoke_data",         # the pinned pool and the composition contract
    "smoke_train",        # one epoch on the GPU
    "smoke_gpu",          # what GPU, and can the IMAGE'S own torch use it?
)

#: Every kernel that unpacks the bundle. `smoke_bare` deliberately does not.
BUNDLED_KERNELS = (*KERNELS, *CPU_KERNELS, *[k for k in SMOKE_KERNELS if k != "smoke_bare"])

ALL_KERNELS = (*KERNELS, *CPU_KERNELS, *SMOKE_KERNELS)

#: Kernels that read from or write to the Hub, and therefore need the token the
#: secrets dataset carries. ``probe_latency`` is deliberately not one: it builds
#: its own untrained artefacts and reports through the kernel log, so attaching a
#: token it never uses would be cargo cult rather than configuration.
#: ``probe_quantisation`` IS one - it reads ``v1/best.pt`` - even though it
#: uploads nothing.
HUB_KERNELS = (*KERNELS, "build_negatives", "bench_latency", "probe_quantisation")


def source(kernel: str) -> str:
    return (KAGGLE / kernel / "script.py").read_text(encoding="utf-8")


def metadata(kernel: str) -> dict:
    return json.loads((KAGGLE / kernel / "kernel-metadata.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("kernel", KERNELS)
def test_the_kernel_exists(kernel):
    assert (KAGGLE / kernel / "script.py").exists()
    assert (KAGGLE / kernel / "kernel-metadata.json").exists()


def test_the_two_kernels_are_not_the_same_script():
    # They were byte-identical. "Training the identifier" trained a detector.
    assert source("train_validator") != source("train_identifier")


def test_each_kernel_trains_its_own_role():
    assert 'ROLE = "validator"' in source("train_validator")
    assert 'ROLE = "identifier"' in source("train_identifier")


@pytest.mark.parametrize("kernel", KERNELS)
def test_export_report_is_given_a_role(kernel):
    # role is the first field with no default. Without it the run raises
    # TypeError after training and before uploading anything - the most
    # expensive possible place to fail.
    assert "ExportReport(" in source(kernel)
    assert "role=ROLE" in source(kernel)


@pytest.mark.parametrize("kernel", KERNELS)
def test_the_dataset_revision_is_pinned(kernel):
    # A number measured against a moving 'main' cannot be reproduced.
    assert "strict=True" in source(kernel)


@pytest.mark.parametrize("kernel", KERNELS)
def test_every_source_of_randomness_is_seeded(kernel):
    text = source(kernel)
    for call in (
        "random.seed(seed)",
        "np.random.seed(seed)",
        "torch.manual_seed(seed)",
        "torch.cuda.manual_seed_all(seed)",
    ):
        assert call in text, call


@pytest.mark.parametrize("kernel", KERNELS)
def test_the_injection_sentinels_are_present(kernel):
    text = source(kernel)
    for sentinel in ("__SBR_PROJECT_BUNDLE_B64__", "__SBR_CONFIG_NAME__", "__SBR_MODEL_VERSION__"):
        assert sentinel in text, sentinel


@pytest.mark.parametrize("kernel", KERNELS)
def test_pushing_the_script_directly_is_refused(kernel):
    assert "bundle sentinel was not replaced" in source(kernel)


@pytest.mark.parametrize("kernel", KERNELS)
def test_the_kernel_does_not_claim_to_decide_shipping(kernel):
    # The latency budget is stated on service CPU. This machine has a GPU and
    # somebody else's CPU, so the kernel exports with latency unmeasured and
    # gate.py decides.
    text = source(kernel)
    assert "median_latency_ms=None" in text
    assert "gate.py" in text


@pytest.mark.parametrize("kernel", KERNELS)
def test_the_kernel_measures_int8_accuracy(kernel):
    """Every gate must have an owner, or the artefact can never ship.

    Until 2026-08-16 neither did: both kernels wrote ``*_int8=None`` deferring
    to ``gate.py``, and ``gate.py`` measures only latency. ``check_gates``
    requires an accuracy drop for ``may_ship``, so the documented promotion path
    terminated in a permanently *unmeasured* artefact.

    ``check_gates`` itself was tested and correct - see
    ``test_export_gates.py::test_a_healthy_artefact_ships``. What nothing tested
    was whether any *producer* fills the fields it needs. That is this test.
    """
    text = source(kernel)
    assert "evaluate_int8(" in text
    metric = "top1" if kernel == "train_identifier" else "map50"
    assert f"{metric}_int8=None" not in text, (
        f"{kernel} defers int8 accuracy to nothing; the artefact can never ship"
    )
    assert f"{metric}_int8={metric}_int8" in text


def test_the_validator_refuses_a_multi_class_dataset():
    assert "must train on exactly ['bin']" in source("train_validator")


def test_the_validator_reports_recall_by_bins_per_frame():
    # docs/04 5: a model that only works on one big centred bin must not be able
    # to hide behind an aggregate.
    text = source("train_validator")
    assert "recall_by_bins_per_frame" in text
    assert '"4+"' in text


def test_the_validator_measures_precision_on_negatives():
    assert "precision_on_negatives" in source("train_validator")


def test_the_identifier_trains_a_classifier_not_a_detector():
    text = source("train_identifier")
    assert "metrics.top1" in text
    assert "build_classification_tree" in text
    assert "metrics.box" not in text


def test_the_identifier_reads_its_class_order_from_the_model():
    # Ultralytics indexes classification by sorted directory name, not by
    # taxonomy file order. Assuming otherwise would mislabel every prediction.
    assert "model.names[index] for index in sorted(model.names)" in source("train_identifier")


def test_the_identifier_reports_its_unknown_rate():
    # `unknown` is a designed product state and the entry to the improvement
    # loop, so its rate is a headline number.
    assert "unknown_rate" in source("train_identifier")


def test_the_identifier_names_classes_it_could_not_train():
    assert "classes_absent" in source("train_identifier")


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kernel", ALL_KERNELS)
def test_the_title_slugs_to_the_kernel_id(kernel):
    """Kaggle derives the real slug from the TITLE, not from the id.

    A title of "SBR - Build Negatives + Open Images Bins" against an id of
    `sbr-build-negatives` creates the kernel at
    `sbr-build-negatives-open-images-bins`, and every later `status` and
    `output` call then fails with a permission error that reads like an auth
    problem. It cost one confusing dispatch to find; it costs one assertion to
    never repeat.
    """
    meta = metadata(kernel)
    slug = meta["id"].split("/", 1)[1]
    assert meta["title"].lower().replace(" ", "-") == slug


def test_kernel_ids_are_distinct_and_named_for_their_role():
    ids = {kernel: metadata(kernel)["id"] for kernel in KERNELS}
    assert len(set(ids.values())) == len(ids)
    assert ids["train_validator"].endswith("sbr-train-validator")
    assert ids["train_identifier"].endswith("sbr-train-identifier")


@pytest.mark.parametrize("kernel", KERNELS)
def test_the_training_kernels_ask_for_a_gpu(kernel):
    meta = metadata(kernel)
    assert meta["enable_gpu"] is True
    assert meta["enable_internet"] is True


# --------------------------------------------------------------------------- #
# The bundle layout - it mirrors the repository, and that is load-bearing
# --------------------------------------------------------------------------- #


def test_the_bundle_puts_the_taxonomy_where_sbr_looks_for_it(tmp_path):
    """`sbr` finds its data by walking up from its own file. The bundle must agree.

    ``taxonomy.py`` resolves the repo root as ``parents[3]`` and ``config.py``
    resolves configs as ``parents[2]/configs``. The bundle used to unpack ``src/``
    and ``data/taxonomy`` as siblings, which put ``parents[3]`` one level ABOVE
    the unpack directory: every ``load_taxonomy()`` inside a kernel died with
    ``FileNotFoundError: .../data/taxonomy/waste-streams.json``.

    It stayed hidden because ``load_config`` resolved correctly from the same
    tree and the one kernel that completed - ``probe_latency`` - never calls
    ``load_taxonomy``. This test builds the real bundle and checks the invariant
    on the unpacked tree, rather than asserting a string that could be right for
    the wrong reason.
    """
    import base64
    import io
    import sys
    import zipfile

    sys.path.insert(0, str(ML_ROOT / "scripts"))
    import dispatch

    with zipfile.ZipFile(io.BytesIO(base64.b64decode(dispatch.build_bundle()))) as archive:
        archive.extractall(tmp_path)

    taxonomy = tmp_path / "ml" / "src" / "sbr" / "taxonomy.py"
    assert taxonomy.exists(), "the bundle does not carry sbr/taxonomy.py where sys.path expects it"

    # The two invariants, computed exactly as the modules compute them.
    repo_root = taxonomy.resolve().parents[3]
    assert (repo_root / "data" / "taxonomy" / "waste-streams.json").exists(), (
        f"taxonomy.py resolves the repo root to {repo_root}, which holds no "
        "data/taxonomy - every load_taxonomy() in a kernel would raise"
    )

    config_py = tmp_path / "ml" / "src" / "sbr" / "config.py"
    assert (config_py.resolve().parents[2] / "configs" / "validator.yaml").exists()


@pytest.mark.parametrize("kernel", BUNDLED_KERNELS)
def test_every_bundled_kernel_uses_the_mirrored_layout(kernel):
    # One sys.path spelling. A kernel still inserting `project/src` would import
    # nothing, or worse, import a stale copy.
    text = source(kernel)
    assert 'PROJECT / "ml" / "src"' in text, f"{kernel} does not use the mirrored bundle layout"
    assert 'str(PROJECT / "src")' not in text


@pytest.mark.parametrize("kernel", CPU_KERNELS)
def test_the_cpu_kernels_do_not_burn_gpu_quota(kernel):
    # Downloading JPEGs and timing an int8 graph on two threads are both
    # bandwidth or CPU. The GPU quota is 30 h/week and training needs it.
    meta = metadata(kernel)
    assert meta["enable_gpu"] is False
    assert meta["enable_internet"] is True


def test_the_bench_kernel_admits_it_is_not_the_service():
    # The budget says "service CPU". A Kaggle kernel is free and x86 but it is
    # not a service container, and the number has to say so.
    text = source("bench_latency")
    assert "representative" in text
    assert "402" in text


def test_the_probe_kernel_needs_no_trained_model():
    """P4 and P5 exist because latency is answerable before training.

    ONNX cost depends on architecture and input shape rather than on learned
    weights, so the probe builds its own untrained exports. If it ever grew a
    dependency on a Hub artefact it would stop being runnable today, which is
    the entire reason docs/12 sequences it first.
    """
    text = source("probe_latency")
    assert "hf_hub_download" not in text
    assert "UNTRAINED" in text


def test_the_probe_kernel_measures_both_batched_and_sequential_crops():
    # docs/12 P4's third decision rule turns on the ratio between them. Measuring
    # only the batched path cannot fire it.
    text = source("probe_latency")
    assert "batched=batched" in text
    assert "CROP_COUNTS = (0, 1, 3, 6)" in text


def test_the_probe_kernel_separates_not_evaluated_from_did_not_fit():
    # P5's rule asks whether a candidate FITS 50 ms. A candidate that failed to
    # install has not answered that question, and collapsing the two would read
    # as evidence for "YOLO11n stays" when none was gathered.
    text = source("probe_latency")
    assert '"evaluated": False' in text
    assert "NOT EVALUATED" in text


def test_the_harvest_kernel_does_not_burn_gpu_quota():
    # Downloading JPEGs is bandwidth, not compute. The GPU quota is 30 h/week
    # and training is what needs it.
    meta = metadata("build_negatives")
    assert meta["enable_gpu"] is False
    assert meta["enable_internet"] is True


@pytest.mark.parametrize("kernel", HUB_KERNELS)
def test_the_secrets_dataset_is_attached(kernel):
    # How the HF token reaches an API-pushed kernel today. Whether a Kaggle
    # Secret could do it instead is not assumed either way - `smoke_usersecret`
    # asks, because the documented kernel metadata has fields for attaching a
    # dataset and none for binding a secret.
    assert metadata(kernel)["dataset_sources"]


# --------------------------------------------------------------------------- #
# torch, and the thing that must never install a different one
# --------------------------------------------------------------------------- #

TORCH_KERNELS = (*KERNELS, "smoke_train")


@pytest.mark.parametrize("kernel", TORCH_KERNELS)
def test_installing_ultralytics_does_not_replace_torch(kernel):
    """Keep pip away from torch - as hygiene, not as the fix.

    `pip install ultralytics` does resolve its own torch, and that was the first
    suspect for the 2026-08-16 failure. **It was the wrong suspect.** A rung that
    installs nothing at all (`smoke_gpu`) reported `installed_anything: false`
    beside `torch==2.10.0+cu128` and a P100 at sm_60, so the mismatch arrives
    with the Kaggle image:

        Tesla P100-PCIE-16GB with CUDA capability sm_60 is not compatible with
        the current PyTorch installation. The current PyTorch install supports
        CUDA capabilities sm_70 sm_75 sm_80 sm_86 sm_90 sm_100 sm_120.

    This assertion still earns its place: a resolver quietly swapping torch would
    stack a second cause on top of a platform one, and the next person would have
    to separate them again.
    """
    text = source(kernel)
    assert "--no-deps" in text, f"{kernel} lets pip resolve ultralytics' own torch"
    assert "ultralytics-thop" in text, (
        f"{kernel} uses --no-deps but does not install ultralytics-thop, which is "
        "the one ultralytics dependency the Kaggle image does not already carry"
    )
    # Nothing in the same pip invocation may name torch either.
    for line in text.splitlines():
        if "pip" in line and "install" in line:
            assert '"torch' not in line, f"{kernel} installs torch explicitly: {line.strip()}"


@pytest.mark.parametrize("kernel", TORCH_KERNELS)
def test_the_device_is_decided_by_capability_not_availability(kernel):
    # `torch.cuda.is_available()` reports that a device exists, not that this
    # torch was compiled for it. The gap between those is the whole failure.
    text = source(kernel)
    assert "sbr.utils.gpu" in text, f"{kernel} does not consult sbr.utils.gpu"
    assert "accelerator.device" in text
    assert 'device=0 if torch.cuda.is_available()' not in text


GPU_KERNELS = (*KERNELS, "smoke_train", "smoke_gpu")


@pytest.mark.parametrize("kernel", GPU_KERNELS)
def test_every_gpu_kernel_asks_for_the_t4_by_name(kernel):
    """Kaggle allocates P100 (sm_60) or T4 (sm_75), and the image's torch only
    runs on the T4. The accelerator IS requestable - `machine_shape` is read by
    `kernels_push` and `kaggle kernels push --accelerator` sets the same field -
    so leaving it to chance is a choice, and the wrong one.

    An earlier version of this work claimed no metadata field could request a
    GPU type. That was wrong, and this assertion is what stops the claim, and
    the retry-until-lucky workflow it implied, coming back.
    """
    meta = metadata(kernel)
    assert meta["enable_gpu"] is True
    assert meta.get("machine_shape") == "NvidiaTeslaT4", (
        f"{kernel} does not request a T4; on a P100 the image's torch has no "
        "sm_60 kernels and the run dies at the first tensor move"
    )


@pytest.mark.parametrize("kernel", KERNELS)
def test_the_gpu_is_checked_before_the_data_is_pulled(kernel):
    """A refusal after the pool is downloaded has already spent the cost.

    The pinned pool is 37 913 files. Checking the accelerator beside
    `model.train()` - which is where it started - means a P100 allocation still
    costs the download and the tree build before it says so, which is most of
    what the 2026-08-16 failure cost.
    """
    text = source(kernel)
    guard = text.index("require_usable_gpu(\"train")
    pull = text.index("download_dataset(")
    assert guard < pull, (
        f"{kernel} checks the GPU after downloading the dataset; the check has to "
        "come first or it saves nothing"
    )


def test_the_training_kernels_refuse_an_unusable_gpu():
    # A silent CPU fallback would burn the wall clock and deliver hours late;
    # a crash inside Ultralytics reproduces 2026-08-16. Neither is acceptable.
    for kernel in KERNELS:
        assert "require_usable_gpu" in source(kernel), kernel


def test_the_smoke_rung_reports_the_gpu_rather_than_refusing_it():
    # Its whole job is to say what the GPU is and whether torch can use it.
    # Refusing would withhold the answer the rung exists to produce.
    text = source("smoke_train")
    assert "inspect_accelerator" in text
    assert "require_usable_gpu" not in text


# --------------------------------------------------------------------------- #
# The smoke ladder
# --------------------------------------------------------------------------- #


def test_each_rung_of_the_ladder_changes_exactly_one_thing():
    """The ladder's whole value is that the rungs differ by one variable each.

    1a -> 1b adds the bundle. 1b -> 2 adds the attached dataset. If two rungs
    ever differ by two things, a failure stops localising anything and the
    ladder becomes six kernels that all do roughly the same.
    """
    bare, plain = metadata("smoke_bare"), metadata("smoke_plain")
    assert bare["dataset_sources"] == [] and plain["dataset_sources"] == []
    assert bare["enable_gpu"] is False and plain["enable_gpu"] is False
    # The one difference: only smoke_plain carries the injection sentinel.
    assert "__SBR_PROJECT_BUNDLE_B64__" not in source("smoke_bare")
    assert "__SBR_PROJECT_BUNDLE_B64__" in source("smoke_plain")

    secrets = metadata("smoke_secrets")
    assert secrets["dataset_sources"] == ["hlexnc/chexvision-secrets"]
    assert secrets["enable_gpu"] is False

    # 2b must NOT attach the dataset, or a token reaching it proves nothing
    # about whether a Kaggle Secret is visible to an API-pushed kernel.
    assert metadata("smoke_usersecret")["dataset_sources"] == []
    assert "UserSecretsClient" in source("smoke_usersecret")


@pytest.mark.parametrize("kernel", SMOKE_KERNELS)
def test_every_rung_writes_a_file_as_well_as_printing(kernel):
    # "No artefact and an empty log" is the failure being diagnosed. A rung that
    # only printed could not distinguish "ran and failed" from "never ran".
    assert 'WORKING / f"{NAME}.json"' in source(kernel)


def test_only_the_two_gpu_rungs_ask_for_a_gpu():
    """The quota is 30 h/week and finding a boundary must not cost much of it.

    Two rungs need one and both earn it: `smoke_gpu` runs for seconds and is the
    only thing that can say whether the image's own torch matches the allocated
    device, and `smoke_train` runs one epoch. Everything else is CPU.
    """
    needs_gpu = {"smoke_gpu", "smoke_train"}
    for kernel in SMOKE_KERNELS:
        assert metadata(kernel)["enable_gpu"] is (kernel in needs_gpu), kernel


def test_the_ladder_does_not_upload_anything():
    # These are diagnostics. A smoke kernel that pushed to the Hub could publish
    # a one-epoch checkpoint as if it were a model.
    for kernel in SMOKE_KERNELS:
        assert "upload_artifacts" not in source(kernel), kernel


def test_the_data_rung_asserts_the_composition_contract():
    # The point of running it on CPU: a drifted pool fails there, for free,
    # rather than inside the GPU run that follows.
    text = source("smoke_data")
    assert "check_composition" in text
    assert "expectation_for" in text


@pytest.mark.parametrize("kernel", ALL_KERNELS)
def test_dispatch_knows_every_kernel(kernel):
    text = (ML_ROOT / "scripts" / "dispatch.py").read_text(encoding="utf-8")
    assert kernel in text


def test_dispatch_does_not_force_a_gpu_on_every_kernel():
    text = (ML_ROOT / "scripts" / "dispatch.py").read_text(encoding="utf-8")
    assert 'metadata["enable_gpu"] = True' not in text


def test_the_harvest_kernel_never_lets_a_bin_into_the_negatives():
    # scan.negatives() removes every image holding a waste container. If this
    # call were replaced by the raw id sets, the validator would be taught that
    # a bin is not a bin, and no aggregate metric would show it.
    text = source("build_negatives")
    assert "scan.negatives()" in text
    assert "bins excluded" in text


# --------------------------------------------------------------------------- #
# The rule that has its own paragraph in AGENTS.md
# --------------------------------------------------------------------------- #


def test_there_are_no_notebooks_anywhere_in_ml():
    # "The predecessor's central artefact was a notebook that could not
    # reproduce its own model." Logic lives in src/ or scripts/.
    assert list(ML_ROOT.rglob("*.ipynb")) == []


# --------------------------------------------------------------------------- #
# P9 - the quantisation probe, and the ways it could measure the wrong thing
# --------------------------------------------------------------------------- #


def test_the_quantisation_probe_never_calibrates_on_val_or_test():
    """Calibration draws from `train`. The one exception is named as one.

    The whole probe turns on a clean partition: calibrate on `train`, select on
    `val`, confirm once on `test`. Calibrating on the split a variant is scored
    on would make every comparison flattering, and the historical baseline is
    allowed to use `val` only because reproducing exactly what v1 did is the
    entire point of that row.

    Read with `ast` rather than a regex: the calls span several lines and a
    pattern that has to match whitespace is a pattern that quietly matches
    nothing the day somebody reformats the file.
    """
    import ast

    tree = ast.parse(source("probe_quantisation"))
    splits = [
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "calibration_frames"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
    ]

    assert splits, "no calibration_frames call found - has the probe stopped calibrating?"
    assert "test" not in splits, "the test split must never calibrate anything"
    assert splits.count("val") == 1, (
        f"expected exactly one val calibration - the historical baseline - got {splits}"
    )
    assert set(splits) <= {"train", "val"}, splits


def test_the_quantisation_probe_selects_on_val_and_confirms_on_test():
    # A winner chosen on `test` and then reported as ship-gate evidence is a
    # number tuned against its own gate. Note the claim is "no candidate is
    # SELECTED on test", not "test is touched once" - test is scored three
    # times and each one is named.
    text = source("probe_quantisation")
    assert 'split="val"' in text
    assert "only ship-gate number in this file" in text
    assert "no candidate is ever selected on ``test``" in text
    # Asserted on the LIVE claim rather than on the presence of a phrase: the
    # docstring also records that it once said "touched exactly once" and that
    # this was false, and a test that forbade the phrase outright would forbid
    # keeping the correction visible.
    import ast

    docstring = ast.get_docstring(ast.parse(text)) or ""
    named = [line for line in docstring.splitlines() if "touched exactly once" in line]
    assert all("was simply false" in line or "said" in line for line in named), (
        "the docstring still claims test is touched exactly once; it is scored three times"
    )


def test_the_quantisation_probe_uses_the_tested_selection_rule():
    """The winner rule must be importable, or it is a rule nothing tests.

    It decides whether an artefact reaches the ship gate. The first version
    lived inline in this kernel and ranked candidates by rounding mAP and
    latency into buckets, which is not the same as the protocol's sequential
    "within 0.005, then within 1 ms" and picks a different winner near an edge.
    """
    text = source("probe_quantisation")
    assert "from sbr.export.selection import Candidate, choose_winner" in text
    assert "choose_winner(" in text
    # The bucketing that used to stand in for the rule.
    assert "NOISE_MAP50" not in text
    assert "round(latency / NOISE_MS)" not in text


def test_the_quantisation_probe_judges_against_the_pytorch_reference():
    """Eligibility reads the PyTorch fp32 val score, not the fp32 ONNX one.

    A lossy ONNX export would otherwise lower the bar its own candidates are
    measured against - the same failure the three-drop accounting prevents, one
    split further up. An earlier version measured the ONNX score and called it
    "PyTorch-equivalent", which is not the same thing.
    """
    text = source("probe_quantisation")
    assert "pytorch_val" in text
    assert "reference_map50=pytorch_val" in text
    # The ONNX score is still measured - it is what separates export loss from
    # quantisation loss - but it must not be what eligibility reads.
    assert "reference_map50=fp32_val" not in text


def test_the_quantisation_probe_runs_the_combined_variant():
    """docs/12 P9 promises one when the two axes disagree.

    Without it the probe could conclude that post-training quantisation cannot
    recover the model when two remedies are jointly necessary and neither is
    sufficient alone.
    """
    text = source("probe_quantisation")
    assert "30-combined" in text
    assert "best_format" in text and "best_calibration" in text


def test_the_quantisation_probe_records_the_whole_calibration_list():
    # The hash fingerprints a set without saying what is in it. Both are needed,
    # and the manifests are written once and referenced by hash from each row.
    text = source("probe_quantisation")
    assert "calibration_sets" in text
    assert ".manifest()" in text


def test_the_quantisation_probe_reproduces_the_baseline_before_remedying_it():
    """A remedy measured against a baseline that does not reproduce is noise.

    The kernel must stop rather than continue, because every later row would be
    compared to something other than the 0.025 the probe exists to explain.
    """
    text = source("probe_quantisation")
    assert "00-historical-baseline" in text
    assert "first_lexicographic" in text
    assert "did not reproduce" in text
    assert "raise SystemExit" in text


def test_the_quantisation_probe_keeps_the_frozen_pytorch_reference():
    # A re-derived fp32 reference would let a lossy export lower the gate's own
    # denominator. The gate reads the total served drop and nothing else.
    text = source("probe_quantisation")
    assert "PYTORCH_FP32_TEST_MAP50 = 0.7524389678079388" in text
    assert "TOTAL SERVED DROP" in text


def test_the_quantisation_probe_treats_fp16_as_informational():
    # onnxruntime's CPU execution provider does not broadly support fp16 ops, so
    # an fp16 row measures something this service cannot serve.
    text = source("probe_quantisation")
    assert "INFORMATIONAL ONLY" in text
    assert '!= "02-fp16-informational"' in text


def test_the_quantisation_probe_records_an_error_rather_than_inventing_a_number():
    # "either metric or error, never both" - a failed load is a valid result.
    text = source("probe_quantisation")
    assert 'row["error"]' in text
    assert 'row["metric"] = value' in text


def test_the_quantisation_probe_builds_its_tree_outside_the_kernel_output():
    """Everything under /kaggle/working is kernel output.

    The pinned pool is 37 913 files, which is why `kaggle kernels output` on a
    training run tries to download all of them. This probe's output has to stay
    small enough to fetch.
    """
    text = source("probe_quantisation")
    assert 'SCRATCH = pathlib.Path("/tmp/sbr")' in text
    assert "local_dir=SCRATCH" in text
    assert 'tree = SCRATCH / "dataset"' in text
    assert 'tree = WORKING' not in text


def test_the_quantisation_probe_uploads_nothing():
    # It is a diagnostic. Promotion is a separate, gated step in gate.py.
    assert "upload_artifacts" not in source("probe_quantisation")


def test_the_quantisation_probe_pins_the_ultralytics_that_produced_v1():
    # Everything in this repo is lower-bounded rather than pinned, and the
    # baseline being reproduced was produced by 8.4.121. A newer ultralytics is
    # a live confound on the one measurement the probe is anchored to.
    text = source("probe_quantisation")
    assert "ultralytics==8.4.121" in text


def test_the_quantisation_probe_covers_the_formats_onnxruntime_names():
    """S8S8, U8S8+reduce_range and U8U8 are the documented remedies.

    onnxruntime names S8S8 the normal CPU choice and describes a large U8S8 loss
    as an x86 activation-saturation symptom. v1 shipped U8S8 without reduced
    range, so a probe omitting these rows could not explain the failure.
    """
    text = source("probe_quantisation")
    for variant in ("11-s8s8", "12-u8s8-reduce-range", "13-u8u8", "14-per-tensor",
                    "15-head-fp32", "21-letterboxed"):
        assert variant in text, variant


def test_the_quantisation_probe_records_the_test_runs_it_actually_made():
    """The record must not declare evaluations that never happened.

    Run 2 was eligible for none, so only the historical baseline touched `test` -
    while the record still listed a locked winner and an fp32 control, because
    the list was a hard-coded plan rather than a reading of the rows.
    """
    text = source("probe_quantisation")
    assert 'r["variant"] for r in rows if r["split"] == "test"' in text
    assert "what ran, not what was planned" in text
