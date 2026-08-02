# Claude Design handoff

Two files go up as guidelines, plus two prompts. That is the whole handoff.

| File | Role |
|---|---|
| [DESIGN-FOUNDATION.md](DESIGN-FOUNDATION.md) | The creative brief – product, people, feeling, references, principles, real constraints, quality bar |
| [../docs/02-waste-taxonomy.md](../docs/02-waste-taxonomy.md) | Domain facts – what a waste stream is, what a region pack is, why "unknown" exists |
| [DECISIONS.md](DECISIONS.md) | What the design answered and what was ratified – written **after** the first round, not sent up as input |

Deliberately **not** here: a palette, a type scale, a token file, a component
inventory, or per-screen state tables. Those were here in an earlier draft and
were wrong – see [Why this is short](#why-this-is-short).

---

## How the two projects work

Claude Design has two project types, and the type is fixed at creation.

**1. Design system** – a project holding real, rendered components plus
guideline documents. It can be created two ways:

- *From a brief*, when no component library exists yet. **This is our case** –
  `web/` is empty, so Claude Design invents the system.
- *Synced up from existing code*, when a library already exists. That is what
  `PROJECTS/12-kaffeelisten` does: `.design-sync/config.json` points at real
  `.tsx` files and pushes them into a design-system project, with
  `guidelinesGlob` sending the briefs up alongside. Worth reading as the
  eventual round-trip, but it is the opposite direction from where we are now.

**2. Prototype** – a normal project where the app is designed. A design system
may be bound to it at creation, or not bound at all.

For Smart Bin Recognition the order is: **design system first, then a prototype
bound to it, then import down into `web/`** via the MCP link. That is the
direction `PROJECTS/08-THD-Room-Finder` went – its `src/components/` mirror a
Claude Design source, and its `src/styles/tokens/` came down from it.

---

## Step 1 – the design system

Create a **design system** project. Attach `DESIGN-FOUNDATION.md`.

> Read DESIGN-FOUNDATION.md. It is a creative brief, not a specification – it
> describes the product, the people and the bar, and deliberately leaves the
> visual system to you.
>
> Build the design system for Smart Bin Recognition: a camera-first web app that
> tells someone what a waste bin is and what may go in it, in their own
> language, anywhere. The person using it is standing outdoors in bad light,
> holding rubbish in one hand, and cannot read the word printed on the lid.
>
> You have complete freedom over palette, typography, scale, shape, motion,
> iconography and the component set. I have opinions but no requirements about
> any of them.
>
> Three things are genuinely fixed, because they come from users rather than
> taste: it must work in nine languages including right-to-left Arabic and
> Devanagari; it must be legible in direct sunlight and usable one-handed on an
> old phone; and meaning must never be carried by colour alone.
>
> One thing I would like you to take seriously as a design problem rather than
> a decision I have already made: the objects this app looks at are already
> colour-coded in the real world – blue lids, brown lids, green glass banks,
> yellow sacks. There is a relationship to be found between the colour of the
> interface and the colour of the thing it is pointed at. I do not know what the
> right answer is. Find one.
>
> Show me the foundations and a component set you think this product needs. If
> the brief and the best design disagree, follow the design and tell me why.

## Step 2 – the prototype

Create a **prototype** project bound to the design system. Attach
`DESIGN-FOUNDATION.md` and `docs/02-waste-taxonomy.md`.

> Design the Smart Bin Recognition app using the bound design system.
>
> Someone points their phone at a bin. Every bin in frame is identified – often
> several at once, sometimes a bank of six containers. Each gets an answer: what
> it is, what it is called locally, what may go in it, what may not, and the
> mistakes people actually make. In their language.
>
> Often we will not know. In a city we have not covered yet, "we don't know this
> bin" is the most common outcome for months. That screen matters more than the
> happy path, and it is where contributing starts.
>
> Laptops and tablets get no camera interface at all – not disabled, simply
> absent. They get the planning surface instead: a map of bins with how recently
> each was confirmed, a searchable rules browser, and tools for contributors.
>
> The screen list in the brief is a starting point. Restructure the flow if you
> see a better one.
>
> The states are the real work: searching, low confidence, needing a clarifying
> question, unknown, stale, offline, connecting, camera denied, submitted but
> not yet published. Recognition runs on a server over a streamed connection, so
> connection states are ordinary and should feel calm rather than alarming.

## Step 3 – import

Pull the result into `web/` through the MCP link, then record the component
vocabulary and styling idiom in a conventions file – the equivalent of
Kaffeelisten's `.design-sync/conventions.md`, which is what makes later code
sessions build *with* the system instead of around it.

---

## Why this is short

The first version of this handoff specified a monochrome palette with hex
values, a type scale, motion durations, radii, an exact component list and a
per-screen state table. Its prompt said *"the attached specification is
authoritative – follow it rather than improving on it."*

That is an engineer telling a designer how to do their job. It would have
produced exactly the design already imagined here and nothing better – which is
the one thing a tool this capable should never be used for.

The distinction worth keeping: **constrain the problem, not the solution.**

- *A constraint:* Arabic is a launch language. Users are outdoors, one-handed.
  Desktop has no camera. Six bins can appear at once. – Facts about the world.
- *Not a constraint:* the interface is monochrome; body text is 15 px; boxes
  ease in over 120 ms. – Design decisions wearing a requirement's clothes.

The model for this is `PROJECTS/12-kaffeelisten/docs/design-foundation.md`,
which sets mood, references with a learn-from/do-not-copy split, colour *roles*
rather than values, and a quality bar written as outcomes.
