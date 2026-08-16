# 01 – Detection and segmentation

*2026-08-16. Feeds docs/04 § 3 (auto-labelling) and § 6 (training).*

---

## 1. SAM 3 collapses two of our four auto-labelling steps

[SAM 3](https://arxiv.org/pdf/2511.16719) (Meta, released 2025-11-19) introduces
**promptable concept segmentation**: given a short noun phrase such as
`"wheelie bin"` or an image exemplar, it returns masks and IDs for *every*
matching instance at once. SAM 1 and SAM 2 returned one object per prompt and
needed a box or point to start from.

docs/04 § 3 currently specifies:

```
[2] candidate boxes    GroundingDINO, prompt: "waste container . wheelie bin . …"
[3] tight masks        SAM 2, prompted by [2]'s boxes
```

SAM 3 does both from the same prompt string. It ships under the SAM License with
checkpoints, inference code and a benchmark, trained on SA-Co (5.2 M images,
4 M noun phrases, 52 M masks).

**This is worth acting on precisely because the pipeline does not exist yet.**
`ml/src/sbr/autolabel/` is documented in docs/04 § 8 and absent from the tree.
Deleting a component before it is written costs nothing; deleting one after costs
a migration.

The residual case for keeping an open-vocabulary detector: SAM 3's concept
vocabulary is noun-phrase driven and our hard cases are *near-misses* (planter
vs bin), which is a discrimination problem rather than a naming one. Keep
GroundingDINO named as a fallback in the doc, but do not build it first.

## 2. Open-vocabulary detectors, if we still need one

The [Roboflow survey](https://blog.roboflow.com/open-vocabulary-object-detection/)
and the [Grounding DINO 1.5 paper](https://arxiv.org/pdf/2405.10300) put the
trade-off simply: **Grounding DINO leads on accuracy, YOLO-World leads on
throughput.** Grounding DINO 1.5 adds an Edge variant for efficiency; 1.6 and
DINO-X extend the pre-training corpus. OWLv2 remains the self-training-scaled
ViT option.

For our use this is a **batch, offline** decision (docs/05 § 5), so throughput
does not matter and accuracy does. That argues for Grounding DINO or SAM 3 over
YOLO-World — the opposite of what one would pick for the request path.

## 3. The validator architecture is worth re-asking, cheaply

[RF-DETR](https://github.com/roboflow/rf-detr) (Roboflow, ICLR 2026) is
Apache-2.0, uses a DINOv2 backbone, and the reported comparisons have RF-DETR and
D-FINE beating YOLO11 at equal latency across sizes, with the **nano variant
standing out most**. [D-FINE](https://blog.roboflow.com/best-object-detection-models/)
ships in five sizes; DEIMv2 (Sept 2025) adds DINOv3 backbones and Pico/Femto/Atto
variants for edge.

The claim that matters for us:

> RF-DETR is best when you have limited data — the transformer backbone often
> generalizes better with fewer training images, and DINOv2 pre-training means it
> adapts to new domains faster and with less data.

We have **1 480 positive frames** and a hypothesis about cross-city
generalisation that the whole project rests on. That is exactly the regime the
claim describes.

**The counter-argument is our binding constraint.** DETR heads are not obviously
fast on two pinned CPU threads, and the gate is 50 ms at 448. Published
comparisons are on T4 and CUDA-ONNX, not on 2 vCPU. So this is a **latency
question first and an accuracy question second** — and latency can be answered
before training, because ONNX inference cost depends on architecture and input
shape, not on learned weights.

## 4. What this changes for us

| Change | Where |
|---|---|
| Replace steps [2]+[3] with a single SAM 3 concept-prompted call; keep GroundingDINO named as the fallback for near-miss discrimination | docs/04 § 3 |
| Record that the batch/offline setting inverts the usual speed-vs-accuracy pick | docs/04 § 3 |
| Add probe **P5**: bench untrained RF-DETR-nano / D-FINE-N against YOLO11n at 448 on 2 pinned vCPUs *before* considering a retrain | docs/12 |
| Keep YOLO11n as the validator until P5 says otherwise — this note is not a licence to swap architectures on a blog post | docs/04 § 6 |

## Sources

- [SAM 3: Segment Anything with Concepts](https://arxiv.org/pdf/2511.16719)
- [Roboflow: what is SAM 3](https://blog.roboflow.com/what-is-sam3/)
- [Ultralytics SAM 3 docs](https://docs.ultralytics.com/models/sam-3)
- [Grounding DINO 1.5](https://arxiv.org/pdf/2405.10300)
- [Open-vocabulary detection, and when to use it](https://blog.roboflow.com/open-vocabulary-object-detection/)
- [RF-DETR](https://github.com/roboflow/rf-detr) · [best detectors 2026](https://blog.roboflow.com/best-object-detection-models/)
