# Claude Design handoff

Everything needed to hand this project to Claude Design. Two projects, in order:
a **Design System**, then a **Prototype** with that system assigned.

```
handoff/
├── DESIGN-SYSTEM.md   → attach to the Design System project
├── PROTOTYPE.md       → attach to the Prototype project
├── tokens.css         → the token contract; also the source of truth for web/
└── README.md          → this file, including both prompts
```

Both markdown files are **self-contained**. They do not link back into `docs/`,
because Claude Design will not follow those links.

---

## Step 1 – Design System

Create a **Design System** project. Attach `DESIGN-SYSTEM.md` (and `tokens.css`).
Paste:

> Build a design system for **Smart Bin**, a civic utility web app that identifies
> waste bins from a phone camera and explains what may be thrown in them, in the
> user's own language.
>
> The attached specification is authoritative – follow it rather than improving on
> it. The single most important rule is in §2: **the interface is monochrome, and
> the only colour anywhere in the product is the colour of the bin being looked
> at.** No brand colour, no accent colour, no gradients, no coloured buttons.
> Structure comes from typographic weight, hairline rules and whitespace – never
> from boxes, borders or shadows. There is exactly one shadow in the entire system.
>
> Users are outdoors, one-handed, often in bright sun or rain, on phones up to six
> years old, reading their second or third language. So: high contrast, 48 px
> minimum targets, body text never below 15 px, generous line height.
>
> Four things I will check first, so please treat them as requirements rather than
> polish:
> 1. **Logical CSS properties only** (`margin-inline-start`, never `margin-left`).
>    Arabic is a launch language and the system must mirror cleanly. Any physical
>    direction property is a bug.
> 2. **Colour is never the only signal.** Every bin colour is paired with a text
>    label and a form-factor icon.
> 3. **True dark mode** (`#000` surface), not dark grey – it is used outdoors at
>    night and on OLED screens.
> 4. **No emoji as iconography.** Line icons, single weight, legible at 20 px.
>
> Deliver the primitives and composites listed in §4, with all their states, plus
> the icon set. Show every component in light and dark, and show at least the
> result card mirrored for RTL.
>
> Please avoid anything that reads as "eco branding" – leaves, recycling arrows,
> green palettes, sustainability gradients. The monochrome rule exists partly to
> make that impossible.

## Step 2 – Prototype

Create a **Prototype** project. **Assign the Smart Bin design system.** Attach
`PROTOTYPE.md`. Paste:

> Design the **Smart Bin** app using the assigned design system. The attached spec
> is authoritative.
>
> The product: someone who has just moved to a new country points their phone at a
> waste bin and is told what it is and what may go in it, in their own language.
> They are standing outside holding rubbish. One answer, fast, trustworthy.
>
> Three things about this app that are easy to get wrong:
>
> 1. **Inference happens on a server, not the phone.** So scanning needs a
>    connection and the design must own that honestly – there is a connecting
>    state, sometimes a "waking up" state (~30 s), and under load the service
>    degrades in visible steps down to tap-to-scan. Offline is a designed state
>    with a plain message, never a red error banner. The rules browser still works
>    offline; the camera and map do not.
>
> 2. **A scan ends.** Once the answer is stable the stream stops and the result
>    locks. That resolved, calm state is the normal successful path – please design
>    it as a destination, not as a paused video.
>
> 3. **"We don't know this bin yet" is a good result.** In a new city it is the
>    most common one for months, and it is the entry point to the contribution flow
>    that makes the product improve. It must feel useful and dignified, never like
>    a failure.
>
> Two hard requirements: **multiple bins must be handled simultaneously** – a bank
> of six containers renders as six boxes and six cards (the previous version of
> this project could only do one at a time, and it was its most visible flaw) – and
> **devices without a rear camera must show no camera UI at all**, not disabled,
> absent. Desktop instead gets the richer surface: map, registry, rules search,
> moderation.
>
> Work through §4 screen by screen, and treat the state tables as the actual
> deliverable – a screen designed only in its happy path is not done. Please
> include dark mode throughout and an Arabic RTL proof of at least the scan result
> and the desktop map.

---

## Then

Claude Design returns a link. Connect it over the MCP server and import into
`web/`. Constraints that apply to the imported code are in
[`../web/README.md`](../web/README.md) – chiefly: `domain/` imports no framework,
tokens instead of hard-coded colour, and logical CSS properties only.

## Why this shape

The user's earlier instinct was right: a `docs/design/` directory is the wrong
handoff surface. Claude Design reads what is attached, not a repository tree, and
a brief split across several linked files silently loses whatever is not
followed. Hence two self-contained files and two prompts, kept deliberately short
enough to actually be read.
