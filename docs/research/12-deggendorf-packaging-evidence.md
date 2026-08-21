# 12 – Deggendorf packaging: the evidence, not the resolution

*Gathered 2026-08-21. **Evidence only.** Nothing in
`data/taxonomy/regions/de-by-deggendorf.json` was changed, the CONTRADICTED
note was not touched, and `deg-packaging-sack` and `deg-packaging-wheelie` are
exactly as they were. Resolving them is the maintainer's decision — this note
exists so that decision has sources under it.*

**The question, deferred three times.** The pack asserts two kerbside packaging
rules — `deg-packaging-sack` (a *Gelber Sack*, confidence 0.95) and
`deg-packaging-wheelie` (a *Gelbe Tonne*, confidence 0.88). The 2026-08-17
sourcing pass found the operator routes packaging to a *Wertstoffinsel*
instead, and left both in place because removing a disposal rule is the
maintainer's call and because ZAW Donau-Wald covers a whole district, so a
yellow sack might exist in *some* municipality within it.

**That last possibility is now closed.**

---

## What the operator says

**Source:** ZAW Donau-Wald / AWG, <https://www.awg.de/gelbe-tonne> —
retrieved **2026-08-21**.

> „Im Dezember 2023 wurde durch die Verbandsversammlung beschlossen, dass die
> sogenannten Leichtverpackungen (LVP) bis Ende 2027 weiterhin auf den
> Recyclinghöfen und Recyclingzentren eingesammelt werden."

> „Sollte die Umstellung beschlossen werden, könnte die Gelbe Tonne ab 2028 in
> der Region eingeführt werden."

Three things follow, and they are about the whole association area rather than
one town:

1. **Light packaging is collected at recycling centres**, by association
   decision, **until the end of 2027**.
2. **A *Gelbe Tonne* does not exist today.** It is a possible future — "könnte
   … ab 2028" — conditional on a decision.
3. **The page does not mention a *Gelber Sack* at all.**

**Coverage.** ZAW Donau-Wald serves the districts of **Regen, Deggendorf,
Freyung-Grafenau and Passau, plus the city of Passau**
(<https://www.awg.de/service-beratung/faq-haeufige-fragen/>, retrieved
2026-08-21). The decision is the association's, so it binds the member
municipalities — which answers the question the CONTRADICTED note left open:
**the "some municipality in the district might still have a Gelber Sack"
escape hatch does not survive an association-wide decision to collect LVP at
recycling centres.**

## What the municipality says

**Source:** Stadt Deggendorf,
<https://www.deggendorf.de/leben/umwelt-natur/entsorgung-recycling> —
retrieved **2026-08-21**.

> „An den Recyclinghöfen des ZAW z.B. in Fischerdorf können mehr als 30
> verschiedene Abfälle abgegeben werden, u.a. Verpackungen"

The city names no yellow bag and no yellow bin. It directs residents with
packaging to the recycling centres.

## And it names the container colours, which the pack says nobody does

This was not what the search was for, and it is the more immediately useful
find. The pack's notes record that **"no source states any container colour"**.
One does, verbatim:

> „Das Trennsystem in Deggendorf umfasst die Restmüll-, Bio- und Papiertonne."

> „In den Abfuhrplänen sind alle Wochentage eingetragen, an denen jeweils die
> **graue Restmülltonne**, die **braune Biotonne** und die **blaue
> Papiertonne** geleert werden."

> „In Wohnnähe stehen **grüne Wertstoffinseln** für Glas und Dosenschrott."

Same page, same retrieval date. That is the *municipality* naming grey, brown
and blue for the three household bins, and green for the glass islands —
exactly the mapping the pack currently carries without a citation.

**It is not written into the pack here.** Adding a source to a published rule
is a pack edit, and pack edits are the maintainer's. What this note does is
remove the reason the gap existed.

## What this does and does not settle

| | |
|---|---|
| Is there a **Gelber Sack** in the ZAW Donau-Wald area? | **No source found says yes.** The operator's own packaging page does not mention one; the city does not mention one |
| Is there a **Gelbe Tonne**? | **Not today.** Possible **from 2028**, conditional on a decision |
| Where does packaging go **now**? | **Recyclinghöfe / Recyclingzentren**, by association decision, until **end of 2027** |
| Could a single municipality differ? | The decision is the **association's**, covering four districts and the city of Passau |
| Do the two pack rules describe reality? | **Both describe a kerbside collection that does not exist**, on this evidence |
| Are the container colours sourced? | **Yes, now** — grey / brown / blue / green, quoted above |

**One thing this note cannot do.** It records an absence of evidence for the
Gelber Sack, which is strong here — the operator's own page on this exact
subject omits it — but it is still an absence. A negative about a whole
district is harder to prove than a positive, and nothing found says outright
"there is no Gelber Sack anywhere in the ZAW area".

**One thing worth watching.** The association was due to decide in 2025 how LVP
collection continues after 2027, and local media covered a "Ja oder Nein"
vote. **The outcome of that vote was not established here** — the video item
returned only its headline and no body text. If the Gelbe Tonne was approved,
`deg-packaging-wheelie` becomes a rule that is wrong *now* and right *from
2028*, which the pack format has no way to express and which is a genuinely
interesting problem for a `valid_from` field it does not have.

## Sources

- ZAW Donau-Wald, [Gelbe Tonne](https://www.awg.de/gelbe-tonne) — retrieved 2026-08-21
- ZAW Donau-Wald, [FAQ](https://www.awg.de/service-beratung/faq-haeufige-fragen/) — retrieved 2026-08-21
- Stadt Deggendorf, [Entsorgung & Recycling](https://www.deggendorf.de/leben/umwelt-natur/entsorgung-recycling) — retrieved 2026-08-21
- Niederbayern TV Deggendorf, ["Ja oder Nein – Entscheidung zur Gelben Tonne beim ZAW Donau-Wald"](https://deggendorf.niederbayerntv.de/mediathek/video/ja-oder-nein-entscheidung-zur-gelben-tonne-beim-zaw-donau-wald/) — headline only; body not retrievable, outcome **not established**
