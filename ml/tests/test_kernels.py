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
CPU_KERNELS = ("build_negatives", "bench_latency", "probe_latency")
ALL_KERNELS = (*KERNELS, *CPU_KERNELS)

#: Kernels that read from or write to the Hub, and therefore need the token the
#: secrets dataset carries. ``probe_latency`` is deliberately not one: it builds
#: its own untrained artefacts and reports through the kernel log, so attaching a
#: token it never uses would be cargo cult rather than configuration.
HUB_KERNELS = (*KERNELS, "build_negatives", "bench_latency")


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
    # How the HF token reaches an API-pushed kernel; UserSecretsClient only
    # works in an interactive session.
    assert metadata(kernel)["dataset_sources"]


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
