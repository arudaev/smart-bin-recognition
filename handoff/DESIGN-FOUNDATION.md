# Design Foundation – Smart Bin Recognition

Creative brief for the Smart Bin Recognition UI/UX system.

Use this as the source of truth for design decisions and Claude Design sessions.
It describes the product, the people, and the bar. It deliberately does **not**
prescribe a palette, a type scale, a component list or a layout – those are the
design's to invent.

---

## Product identity

**What it is:** A camera-first web app that tells you what a waste bin is and
what may go in it, in your own language, anywhere.

**Who uses it:** Someone who has recently moved to a new country – a student, a
worker, a new arrival – standing outside, holding rubbish, unable to read the
word printed on the lid. Also longer-term residents looking for the nearest
glass bank, and contributors improving coverage for their town.

**Where it lives:** Primarily a phone, outdoors, one-handed. Secondarily a
laptop or tablet at a desk, where there is **no camera at all** and the job is
planning rather than acting.

**When it's used:** Briefly, at the moment of decision, often in bad light or
rain. Rarely more than a minute at a time.

The interface must feel like a calm public utility that happens to be modern –
not a startup demo, not an eco-brand, not a computer-vision showcase.

---

## The feeling we are after

A person who cannot read the local language is, at that moment, slightly
embarrassed and slightly stuck. The app should make that feeling go away in
about four seconds, without ever making them feel handled, taught, or
condescended to.

So: **quietly competent.** It knows the answer, gives it plainly, and gets out
of the way. When it does not know, it says so like an honest person would, and
that admission should feel like part of the product rather than a crack in it.

If a user's overwhelming impression is *"oh – that was easy"* and they never
think about the interface at all, the design has succeeded.

---

## Visual direction

**Mood:** Calm, precise, legible, confident. Editorial rather than app-like.
Civic infrastructure rather than consumer product. It should look like something
a city could plausibly adopt, and like something a designer made on purpose.

**Tone:** Plain, short, unhurried. Never cheerful, never apologetic.

**Signature opportunity:** the physical world this app points at is *already*
colour-coded – blue lids, brown lids, green glass banks, yellow sacks. That is
real, meaningful colour that exists before the design does. There is something
in the relationship between the colour of the interface and the colour of the
object it is looking at. What that relationship should be is an open design
question, and a genuinely interesting one.

---

## Reference direction

Inspiration only. Do not copy.

| Reference | Learn from | Do not copy |
|---|---|---|
| **The predecessor's own project deck** (`cv_garbage/_CV-Project.pdf` in the sibling `06-Painfully-Trivial` repo, and see below) | Typographic confidence, generous margins, structure carried by weight and scale rather than ornament, colour appearing only where it is real | Its literal monochrome, its slide layouts, its being a presentation |
| German municipal waste signage | Directness, pictogram discipline, being unambiguous at a glance in bad light | Bureaucratic coldness, German-only assumptions, institutional ugliness |
| Transit and wayfinding systems | Reading at speed, under stress, in poor conditions; colour used as a system rather than decoration | Literal transit iconography, map-network metaphors |
| Editorial and reference apps | Calm reading, clear hierarchy, trustworthy typesetting | Article/feed structures, long-form density |

**On the deck:** the maintainer likes it and it is worth studying – but it is a
14-slide black-and-white presentation, not a product. Treat it as evidence of
taste, not as a specification. Diverging from it with a reason is welcome.

**Anti-references – what this must never look like:** recycling-green eco
branding, leaves, arrows-in-a-triangle, earth tones, sustainability gradients;
AI/computer-vision aesthetics (scan lines, reticles, HUD overlays, neon
tracking boxes); generic SaaS dashboards; anything gamified.

---

## UI/UX principles

**1. Answer first.**
The identity of the bin and what goes in it lead. Everything technical –
confidence, connection state, how the answer was reached – is secondary and
must never be the first thing read.

**2. Their language, not the bin's.**
Local-language words appear only when they are printed on the physical object,
and always alongside a translation. The user needs to match the word they can
see *and* understand it. Both, always.

**3. Not knowing is a real answer.**
In a city we have not covered yet, "we don't know this bin" is the **most
common** result for months. It must feel useful and dignified, never like a
failure or an error, and it is the doorway into contributing.

**4. Honest about age.**
Bins move. Every fact drawn from the shared registry carries when it was last
confirmed, and something checked yesterday must not look identical to something
last seen eight months ago.

**5. Legible in the worst case.**
Direct sunlight, rain on the screen, a cracked five-year-old phone, one hand
because the other is holding rubbish. Design for that case, not for a press
screenshot.

**6. Never colour alone, never camera alone.**
Every meaning has a non-colour carrier, and every rule is reachable without a
camera. The people who most need this app include those who cannot use one.

---

## Real constraints

These come from users and hardware, not from taste. They shape the problem; how
to solve them is open.

- **Nine languages at launch**, including **Arabic (right-to-left)**, Hindi
  (Devanagari), Ukrainian and Russian (Cyrillic). A layout that only survives
  English and German is not finished. German compounds run ~40 % longer than
  English.
- **Devices with no rear camera must not see a camera interface** – not
  disabled, not hidden behind a tooltip, simply not there. In exchange they get
  the richer planning surface: map, registry, rules search, and for trusted
  contributors, moderation.
- **Several bins at once.** A bank of six containers is a normal input, not an
  edge case. The predecessor could only ever show one, and it was its most
  visible failure.
- **Scanning needs a connection; the rules browser does not.** Recognition runs
  on a server over a streamed connection, so connecting, waking, busy and
  offline are ordinary everyday states that all need to feel calm and honest.
- **Confidence varies and must be readable as such.** Sometimes the system
  should assert, sometimes hedge, sometimes ask a clarifying question – the
  glass bank with three colour-coded slots is the standard case for asking.
- **WCAG 2.2 AA**, full keyboard path on desktop, screen-reader-complete
  results, and generous outdoor tap targets.

---

## Copy direction

Plain, calm, short. The reader is mildly stressed and reading a second or third
language.

- Prefer: "Paper and cardboard." · "Not this one." · "We don't know this bin yet."
- Avoid: "Detection successful!" · "Oops! Something went wrong" · "Analyzing…"

No exclamation marks. **No emoji in the interface** – the predecessor used
🗑️ 🥬 📰 as its iconography and it undercut everything. Icons are drawn.

Never use the words *model*, *inference*, *confidence score*, *class*, or
*detection* in anything a user reads.

The product name is **Smart Bin Recognition**. A shorter consumer wordmark may
serve the app better; proposing one is in scope.

---

## Screens that need to exist

Descriptions, not specifications. Merge, split, rename or re-conceive them
freely if the flow is better for it.

**Phone**
| Screen | What it is for |
|---|---|
| First run | Choose a language, understand the app in one sentence, allow the camera. Three steps, skippable. |
| Scanner | Live camera, every bin in frame identified. The main surface. |
| Result | What this bin is, what it is called here, what goes in, what does not, the mistakes people actually make. |
| Several bins | The same, for a row of six containers, without becoming a wall of text. |
| Unknown bin | Honest, useful, and the entry point to contributing. |
| Contribute | A short structured report of a bin we do not know. Nothing free-text. |

**Laptop and tablet – no camera anywhere**
| Screen | What it is for |
|---|---|
| Map | Bins near a place, with how recently each was confirmed. |
| Rules browser | Search by item ("coffee grounds", "pizza box") or browse by bin. The text-only route to every rule. |
| Contributor tools | Review the queue, fix and publish entries. Dense and keyboard-first. |
| Settings | Language, theme, region, downloaded data, privacy. |

**States that need designing as carefully as the screens:** searching, nothing
found, low confidence, needs a clarifying question, unknown, stale, offline,
connecting, camera denied, submitted-but-not-yet-published, empty region.

---

## Quality bar

The design is done when:

- A person who reads no German gets a correct, understood answer in about four
  seconds, outdoors, one-handed, without instructions.
- "We don't know this bin yet" reads as helpful rather than broken.
- Six bins in one frame is legible and calm.
- The no-camera desktop surface stands on its own as a product, rather than
  feeling like the phone app with a hole in it.
- Every screen survives Arabic, mirrored, and Devanagari, at every size.
- It is readable in direct sunlight and comfortable at night.
- It looks like civic infrastructure a city would adopt – and like nothing else
  in the category.
- Nothing on screen mentions how the recognition works.
