# 06 – Colour measurement

*2026-08-16. Feeds docs/02 § 1 (the three axes) and docs/04 § 1 (why B runs on
crops).*

---

## 1. "Colour is measured, not learnt" is right, and not free

docs/02 § 1 makes colour the second axis and calls it *"Classical CV, measured
per-pixel … Never changes – it is a measurement"*. The architecture is correct
and it is what lets a new country ship as a JSON pull request.

But "it is a measurement" understates the work. A camera does not record object
colour; it records object colour × illuminant × white balance × exposure. Rain,
shade, dusk, sodium street lighting, faded plastic and wet surfaces all move the
measured value. This is the **colour constancy** problem and it has a fifty-year
literature.

## 2. The classical methods, cheapest first

Statistics-based illuminant estimation is efficient and interpretable, and its
known weakness — limited generalisation because of its assumptions — is
tolerable here for a reason specific to us: **we do not need the true colour, we
need a stable assignment to one of about a dozen named colours.** That is a much
weaker requirement than colorimetric accuracy.

| Method | Assumption | Cost |
|---|---|---|
| **Gray World** | average scene reflectance is gray | trivial |
| **Shades of Gray** | the *p*-norm of the image estimates the illuminant | trivial; usually beats Gray World |
| **Gray Edge** | the same, in the gradient domain | cheap |
| Learning-based / DNN | none | a model, a dataset, and a budget we do not have |

Then convert to **CIELAB** and assign by **ΔE** to the nearest named colour.
CIELAB is the right space because it is perceptually approximately uniform, so a
ΔE threshold means roughly the same thing across the colour wheel — which an RGB
distance does not.

## 3. The unexamined assumption: masks

docs/04 § 1 says colour is taken "from the *mask*, so a bin photographed against
grass no longer reads as greenish", making SAM a dependency of colour
measurement.

That may not be necessary. Model B's crop is *filled* by the object — the
validator localised it and `identifier.yaml` pads by only 0.12. A centre-weighted
sample inside the box may already exclude most background. And a mask does not
solve the harder problem anyway: **separating lid from body**, which is what the
region pack actually joins on. SAM gives one object mask, not parts.

So the real open questions are, in order:

1. Does box-centre sampling beat naive whole-crop averaging? *(probably)*
2. Does illuminant normalisation beat box-centre sampling? *(probably)*
3. Does a mask beat illuminant-normalised box-centre sampling? *(unknown — and if
   not, SAM leaves the critical path entirely)*
4. How is lid separated from body? *(unsolved by any of the above; likely a
   vertical-band heuristic, since lids are on top)*

## 4. Ground truth we do not have

docs/07 phase 2 lists *"Colour extraction from SAM 2 masks, validated against the
legacy class labels"*. That validation is not sound: legacy labels are waste
**streams** (Biomüll, Glas, Papier, Restmüll), and a stream is not a colour. It
is the same category error the adjudication pass exists to fix for form factors —
docs/04 § 5 already says a stream does not determine a shape, and it does not
determine a colour either.

Colour needs its own small ground truth: body and lid colour hand-labelled on a
few hundred crops. That is fast work — it is colour, one keystroke — and it is
the only thing that makes any of the above measurable.

## 5. What this changes for us

| Change | Where |
|---|---|
| State that colour is a measurement **under an illuminant**, and that normalisation is part of the method | docs/02 § 1 |
| Correct phase 2's colour task: validating against legacy *stream* labels is a category error | docs/07 |
| Add ~120 hand-labelled body/lid colours as the ground truth | docs/12, probe **P3** |
| Test whether SAM is needed at all before making it a dependency | docs/04 § 1, probe **P3** |
| Name lid-vs-body separation as an open problem no method above solves | docs/02 § 1 |
| Specify CIELAB + ΔE-to-named-colour as the assignment rule, with an `unknown` band | docs/02 § 1 |

## Sources

- [Edge-based colour constancy (Gevers et al.)](https://staff.science.uva.nl/th.gevers/pub/GeversTIP07.pdf)
- [Shades of Gray and colour constancy](https://www.researchgate.net/publication/221502067_Shades_of_Gray_and_Colour_Constancy)
- [Gray-world assumption on perceptual colour spaces](https://link.springer.com/content/pdf/10.1007/978-3-642-53842-1_42.pdf)
- [Multi-illuminant colour constancy (2025)](https://arxiv.org/pdf/2502.02021)
