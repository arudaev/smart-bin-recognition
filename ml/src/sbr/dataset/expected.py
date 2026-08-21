"""What a pinned revision is asserted to contain, and the refusal when it is not.

A pin says *which* data. It does not say *what is in it*, and the difference has
already cost a GPU hour: the 2026-08-16 validator run pulled the pinned pool,
built its tree, reported ``background_images: 0`` over a pool that is 92 %
background, and started training anyway. The counting bug is fixed
(``prepare.build_yolo_tree`` counts a background image by its boxes rather than
by a missing label file). What was missing was anything that would have
**refused** - the number was written into a report nobody read until afterwards.

So the composition is a contract, checked before the expensive work rather than
described after it.

**One role only, deliberately.** The validator trains on
``arudaev/smart-bin-detect`` through :func:`sbr.dataset.prepare.build_yolo_tree`.
The identifier trains on ``arudaev/smart-bin-identify`` through
``build_classification_tree``, over **adjudicated crops**, of which there are
currently none - the repo is unpinned and the human pass has not run. Writing it
a contract today would be asserting a composition nobody has produced. It gets
one in the same commit as its pin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CompositionDriftError(ValueError):
    """The pinned revision no longer holds what this module says it holds.

    Raised rather than logged. A warning here is a warning in the first hundred
    lines of a kernel log that ends in an artefact somebody quotes.
    """


@dataclass(frozen=True)
class PoolExpectation:
    """One subset of a dataset repo."""

    frames: int
    boxes: int
    note: str = ""

    #: Identifier-side. Zero for a subset that carries no crops at all.
    crops: int = 0
    #: Crops carrying a human decision - `confirmed`, `corrected` or `authored`.
    #: A run that trains on crops asserts this equals :attr:`crops`.
    crops_adjudicated: int = 0
    #: Crops a reviewer rejected as not a bin. A decision, not outstanding work,
    #: and counted apart from the pending ones for exactly that reason.
    crops_rejected: int = 0
    #: **The human pass's own result, per form factor.** Totals are necessary
    #: and not sufficient: 403 crops can stay 403 crops while every label
    #: underneath them changes, and the identifier would train on the difference
    #: without a word. This is what makes the contract about labels rather than
    #: about arithmetic.
    crops_by_form_factor: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetExpectation:
    """What one pinned revision of one repo contains."""

    repo_id: str
    revision: str
    pools: dict[str, PoolExpectation] = field(default_factory=dict)

    #: Frames with no boxes at all. The negative corpus is most of what buys the
    #: validator its precision, and `min_precision_on_negatives` is one of its
    #: targets, so a pool that quietly lost them would train a different model.
    background_frames: int = 0

    @property
    def total_frames(self) -> int:
        return sum(pool.frames for pool in self.pools.values())

    @property
    def positive_frames(self) -> int:
        return self.total_frames - self.background_frames

    @property
    def total_boxes(self) -> int:
        return sum(pool.boxes for pool in self.pools.values())

    def ratios(self) -> dict[str, float]:
        """Both negative ratios, each labelled with what it is a ratio of.

        Two numbers are in circulation for this dataset and **both are correct**:
        15.7:1 counts the backgrounds against the Open Images bin frames they
        were harvested alongside, and 11.8:1 counts them against every positive
        frame in the pool. Quoting either without saying which is how a document
        ends up contradicting itself six weeks later.
        """
        open_images = self.pools.get("open_images")
        ratios = {
            "against_all_positives": round(self.background_frames / self.positive_frames, 1)
            if self.positive_frames
            else 0.0
        }
        if open_images and open_images.frames:
            ratios["within_the_open_images_subset"] = round(
                self.background_frames / open_images.frames, 1
            )
        return ratios


#: The contract, per repo. Changing one of these means the next training run sees
#: different data: it is a deliberate act and belongs in its own commit, with the
#: reason in the message - exactly as ``sbr.utils.hub.PINS`` says of the pin
#: itself. The two are checked against each other by a test.
EXPECTED: dict[str, DatasetExpectation] = {
    "arudaev/smart-bin-detect": DatasetExpectation(
        repo_id="arudaev/smart-bin-detect",
        # The parent commit, c39b0f879dba, is "negatives: drop 25 street/hard
        # duplicate records (17499 -> 17474)" and holds byte-identical data; the
        # only path that differs between the two is README.md. Either sha
        # describes this composition, and this is the one the kernels resolve.
        revision="8666aa23ff1a8572cd57349a8c5bd1f0b2d88285",
        pools={
            "legacy": PoolExpectation(
                frames=370, boxes=403,
                note="one city, one week; 403 crops all still pending adjudication",
            ),
            "open_images": PoolExpectation(
                frames=1110, boxes=1936,
                note="the only multi-bin frames in the project; 98 hold four or more",
            ),
            "negatives": PoolExpectation(
                frames=17474, boxes=0,
                note="14 975 street scenes + 2 499 hard negatives",
            ),
        },
        background_frames=17474,
    ),
    # The identifier's dataset. Pushed 2026-08-21, private, in the same commit
    # as this contract - which is what the docstring above promised it would
    # wait for. It is the SAME legacy pool as `smart-bin-detect`'s `legacy`
    # subset, with `crops/` included and the human pass applied to the manifest.
    #
    # The per-class counts are the human pass's result, all 403 decisions taken
    # blind by reviewer `alex`: no proposal was shown, so every verdict is
    # `authored` rather than `confirmed`. That distinction is load-bearing - the
    # pool's shipped `form_factor_proposed` is a stream -> shape mapping and is
    # wrong on 116 of 403, of which 111 are `wheelie_small` where the answer is
    # `wheelie_large`.
    "arudaev/smart-bin-identify": DatasetExpectation(
        repo_id="arudaev/smart-bin-identify",
        revision="cda374c9a55dccb7e05c2fb6b4929077f8174d6a",
        pools={
            "legacy": PoolExpectation(
                frames=370, boxes=403,
                crops=403, crops_adjudicated=403, crops_rejected=0,
                crops_by_form_factor={
                    "wheelie_small": 247,
                    "wheelie_large": 115,
                    "igloo": 40,
                    # n=1 in ONE capture cluster, so it cannot be split across
                    # train/val/test and cannot be trained or evaluated. It is
                    # asserted here because it EXISTS; whether it reaches a
                    # class list is a separate decision, and dropping it is
                    # recorded as a coverage gap rather than merged away.
                    "street_basket": 1,
                },
                note="one city, one week; 403 crops, all adjudicated blind by `alex`",
            ),
        },
        background_frames=0,
    ),
}


def expectation_for(repo_id: str) -> DatasetExpectation | None:
    """The contract for a repo, or ``None`` where there is deliberately none."""
    expectation = EXPECTED.get(repo_id)
    if expectation is None or not expectation.revision:
        return None
    return expectation


def check_composition(composition: dict[str, Any], expected: DatasetExpectation) -> None:
    """Compare what ``build_yolo_tree`` wrote against the contract. Raise on drift.

    ``composition`` is ``composition.json`` verbatim. Every disagreement is
    collected before raising, because a run that fails on the first difference
    makes somebody dispatch again to find the second.
    """
    drift: list[str] = []

    per_pool = composition.get("per_pool") or {}
    for name, pool in sorted(expected.pools.items()):
        actual = per_pool.get(name)
        if actual is None:
            drift.append(f"subset {name!r} is missing entirely (expected {pool.frames} frames)")
        elif actual != pool.frames:
            drift.append(f"subset {name!r}: {actual} frames, expected {pool.frames}")

    unexpected = sorted(set(per_pool) - set(expected.pools))
    if unexpected:
        drift.append(f"subsets nobody wrote a contract for: {unexpected}")

    for key, want in (
        ("background_images", expected.background_frames),
        ("positives", expected.positive_frames),
    ):
        actual = composition.get(key)
        if actual != want:
            drift.append(f"{key}: {actual}, expected {want}")

    if drift:
        raise CompositionDriftError(
            f"{expected.repo_id}@{expected.revision[:12]} does not hold what "
            f"sbr.dataset.expected says it holds:\n  - "
            + "\n  - ".join(drift)
            + "\n\nEither the pool changed under a pin that says it did not, or the "
            "builder changed what it counts. Both are reasons to stop before "
            "spending a GPU hour, and neither is a reason to loosen this check: "
            "fix the pool, or change the contract deliberately and say why."
        )


def check_manifest_counts(
    counts: dict[str, tuple[int, int]], expected: DatasetExpectation
) -> None:
    """Compare ``{subset: (frames, boxes)}`` read from the manifests against the contract.

    This is the stronger check of the two - it sees box counts, which
    ``composition.json`` does not record - and it is the one that can run without
    downloading a single image.
    """
    drift: list[str] = []
    for name, pool in sorted(expected.pools.items()):
        actual = counts.get(name)
        if actual is None:
            drift.append(f"subset {name!r} is missing entirely")
            continue
        frames, boxes = actual
        if frames != pool.frames:
            drift.append(f"subset {name!r}: {frames} frames, expected {pool.frames}")
        if boxes != pool.boxes:
            drift.append(f"subset {name!r}: {boxes} boxes, expected {pool.boxes}")

    total = sum(frames for frames, _ in counts.values())
    if total != expected.total_frames:
        drift.append(f"total: {total} frames, expected {expected.total_frames}")

    if drift:
        raise CompositionDriftError(
            f"{expected.repo_id}@{expected.revision[:12]} manifests do not match "
            f"sbr.dataset.expected:\n  - " + "\n  - ".join(drift)
        )


# --------------------------------------------------------------------------- #
# The identifier's side: crops, and the labels on them
# --------------------------------------------------------------------------- #

#: What counts as a human decision. Mirrors `sbr.dataset.prepare.ADJUDICATED`,
#: and a test pins the two together - they are the same fact stated twice, and
#: the day they disagree the contract passes over data the builder skips.
ADJUDICATED = frozenset({"confirmed", "corrected", "authored"})


@dataclass(frozen=True)
class CropCounts:
    """What one pool's ``crop_records`` actually hold."""

    crops: int
    adjudicated: int
    rejected: int
    pending: int
    by_form_factor: dict[str, int] = field(default_factory=dict)


def crop_counts(manifest: dict[str, Any]) -> CropCounts:
    """Count a pool manifest's crops by state and by form factor.

    Only *adjudicated* crops contribute to ``by_form_factor``. A form factor
    sitting on a pending crop is the pool's stream -> shape guess, not a label,
    and counting it here would let the guess satisfy a contract about the
    human pass.
    """
    records = manifest.get("crop_records", []) or []
    by_form_factor: dict[str, int] = {}
    adjudicated = rejected = pending = 0

    for crop in records:
        state = crop.get("adjudication")
        if state == "rejected":
            rejected += 1
            continue
        if state not in ADJUDICATED:
            pending += 1
            continue
        adjudicated += 1
        form_factor = crop.get("form_factor")
        if form_factor:
            by_form_factor[form_factor] = by_form_factor.get(form_factor, 0) + 1

    return CropCounts(
        crops=len(records),
        adjudicated=adjudicated,
        rejected=rejected,
        pending=pending,
        by_form_factor=dict(sorted(by_form_factor.items())),
    )


def check_crop_composition(
    counts: dict[str, CropCounts], expected: DatasetExpectation
) -> None:
    """Compare ``{subset: CropCounts}`` against the contract. Raise on drift.

    This is the check that makes the identifier's pin mean something. The frame
    and box totals can hold exactly while every form factor underneath them
    changes - a re-run of the adjudication tool, a merged class, a partially
    applied decision file - and the model would train on the difference in
    silence. So the **per-class counts are asserted**, not just the totals.
    """
    drift: list[str] = []

    for name, pool in sorted(expected.pools.items()):
        actual = counts.get(name)
        if actual is None:
            drift.append(f"subset {name!r} is missing entirely")
            continue
        if actual.crops != pool.crops:
            drift.append(f"subset {name!r}: {actual.crops} crops, expected {pool.crops}")
        if actual.adjudicated != pool.crops_adjudicated:
            drift.append(
                f"subset {name!r}: {actual.adjudicated} adjudicated crops, "
                f"expected {pool.crops_adjudicated}"
            )
        if actual.rejected != pool.crops_rejected:
            drift.append(
                f"subset {name!r}: {actual.rejected} rejected crops, "
                f"expected {pool.crops_rejected}"
            )
        if actual.pending:
            drift.append(
                f"subset {name!r}: {actual.pending} crops are still pending "
                "adjudication. The identifier cannot be trained on a form factor "
                "nobody confirmed"
            )
        if actual.by_form_factor != pool.crops_by_form_factor:
            drift.append(
                f"subset {name!r} labels changed: {actual.by_form_factor} against "
                f"an expected {pool.crops_by_form_factor}"
            )

    if drift:
        raise CompositionDriftError(
            f"{expected.repo_id}@{expected.revision[:12]} does not hold the crops "
            f"sbr.dataset.expected says it holds:\n  - "
            + "\n  - ".join(drift)
            + "\n\nThe human pass is the one irreplaceable step in this phase. If "
            "it was re-run, pin the new revision and update this contract in the "
            "same commit, with the reason in the message."
        )
