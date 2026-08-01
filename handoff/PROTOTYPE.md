# Smart Bin – Prototype Spec

> Attach this file to a **Claude Design → Prototype** project, with the
> *Smart Bin* design system assigned.
> Self-contained: the product, its screens, and every state that must exist.

---

## 1. The product in one line

Point your phone at a waste bin; it tells you what the bin is and what goes in
it, in your language, anywhere.

**Who:** someone who has recently moved to a new country. Colour coding for bins
is not standardised – it changes by country, by state, sometimes by contractor
within one city – and the official rules are a PDF in a language they do not
read. They are outside, holding rubbish, and need one answer now.

## 2. How it works (enough to design it)

Inference runs **on a server**, not on the phone. The app captures camera frames,
compresses them, and streams them over a WebSocket; the server returns detections
and the app draws boxes.

This has direct design consequences and they are not optional:

- **Scanning requires a connection.** Offline is a designed, honest state.
- There is a **connecting** state, and sometimes a **waking up** state (~30 s) when
  the service has been idle.
- Under load the service **degrades in visible steps**: full live → reduced rate →
  tap-to-scan only → short queue. Each step is stated in plain language.
- A scan is a **task with an end**: once the same answer holds for ~3 consecutive
  frames, streaming stops and the result locks. Design for this – it is the
  normal, successful path, not an edge case.

Two models run server-side. One finds bins ("is there a bin, and where"); the
other identifies them ("what kind"). They can disagree, and that disagreement is
what produces the **"we don't know this bin yet"** result – which is a good,
useful outcome, not a failure.

## 3. Device tiers

Detected by capability probe, never by user-agent.

| Tier | Condition | Gets |
|---|---|---|
| **Scanner** | rear camera available | Live streaming scan. Primary surface. |
| **Viewer + capture** | front camera only (tablets, some laptops) | Still capture / upload. No live loop. |
| **Viewer** | no camera, or permission denied | **No camera UI at all** – map, registry, rules search, contributor tools |

**Desktop must never show a camera affordance.** Not greyed out, not behind a
tooltip – absent. In exchange the desktop surface is genuinely richer: map with
filters, last-verified timestamps, edit history, moderation queue.

## 4. Screens

Legend: 📱 mobile · 🖥 desktop · ◐ both. **The states are the work** – a screen
designed only in its happy path is not done.

### 4.1 ◐ First run

Three steps, skippable, no carousel.
1. **Language** – endonyms only (`Deutsch`, `العربية`, `Українська`). No flags, no
   translated language names. First, because the user may not read the default.
2. **What this does** – one sentence, one illustration.
3. **Camera permission** – asked in context, one line of reason, skippable.

*States:* default · permission denied · offline on first run · unsupported browser.

### 4.2 📱 Scanner – the primary screen

Camera fills the frame. Chrome is minimal and bottom-weighted.

- Detection boxes drawn in **the bin's own colour**, eased into place, each with a
  short label in the user's language.
- Collapsed bottom sheet: count + one-line summary ("2 bins found"). Drag or tap
  to expand into result cards.
- Top-left language, top-right a quiet status affordance. Nothing else.

*States:*

| State | Behaviour |
|---|---|
| Connecting | brief, quiet. Not a blocking spinner. |
| **Waking up** | service was idle; honest message + rough expectation (~30 s) |
| Searching | nothing detected. "Point at a bin." No spinner. |
| One bin | box + collapsed sheet naming it |
| Multiple bins | every bin boxed and labelled; "6 bins found" |
| Low confidence | box drawn grey, not colour; label hedges |
| Unknown | dashed grey box; "Not sure yet" → § 4.5 |
| **Locked** | stable result reached, streaming stopped. Calm, resolved. A clear "scan again" control. |
| Reduced rate | service busy; stated plainly, still working |
| Tap-to-scan | live loop off; single explicit capture control |
| **Offline** | "Scanning needs a connection." Offer the rules browser. Not a red error. |
| Slow connection | degraded gracefully, stated |
| Camera denied | scanner replaced entirely by rules browser. No dead camera UI. |

### 4.3 ◐ Result card

1. **Colour chip** – solid, the bin's colour. The only colour in view.
2. **Stream name** – large, bold, user's language.
3. **Local name** – smaller, secondary: *Papiertonne*. Both, always: the user must
   match the word on the bin *and* understand it.
4. **✅ Goes here** – item list, icon + label.
5. **❌ Does not go here** – same treatment.
6. **⚠ Commonly confused** – the two or three mistakes people actually make.
7. **Footer** – "checked 3 days ago", source citation, "report a problem".

*States:* confident (asserts) · medium (hedges) · low (asks) · **disambiguation**
(glass bank: "which slot are you at?" with three colour options) · unknown ·
stale · pending (submitter-only, clearly marked).

### 4.4 📱 Multi-bin result

A bank of six containers → six cards, each with its own colour chip, each mapped
to its box by position and colour. Selecting a card highlights its box; selecting
a box scrolls to its card.

*States:* 2 bins · 6+ bins · mixed known/unknown in one frame · same stream
repeated (collapse to one card with a count: "3 × residual").

### 4.5 ◐ Unknown bin

**Not an error.** In an uncovered city this is the most common result for months,
and it is the entry point to the contribution loop that makes the product improve.

- Honest headline: "We don't know this bin yet."
- What we *can* say – form factor, measured colour. Partial knowledge proves the
  app is working rather than broken.
- Nearest guess, explicitly framed as a guess, never as advice.
- Primary action: **"Help identify it"** → § 4.6.
- Secondary: browse all bin types for this area.

### 4.6 📱 Contribute

Short, structured fields only – nothing free-text.

1. Confirm form factor (pre-filled) · 2. Confirm colours (pre-filled) ·
3. How many here? (stepper) · 4. Access: open / in a shed / locked / unsure ·
5. Photo – **opt-in**, with a plain statement of what happens to it · 6. Submit.

*States:* default · offline (queued – normal, not an error) · rate-limited (plain,
not scolding) · submitted/pending · bot check (rare, unobtrusive).

### 4.7 ◐ Rules browser

The text-only route to every rule. Required for accessibility, and it is the
entire app for someone with no camera. **Works offline.**

Search by item ("coffee grounds", "pizza box") → which bin, here. Browse by bin
type → full accepted/rejected lists. Region selector naming the current area and
its source.

*States:* default · no results · region not covered · offline.

### 4.8 🖥 Map

Desktop centrepiece. **No camera anywhere on this surface.**

Bins pinned by type, coloured by bin colour, on a deliberately desaturated
basemap so the pins are the only colour. Filter by type, access, freshness. Pin →
result card + history. Inline confirm / report-gone controls.

*States:* default · nothing nearby · region uncovered · location denied (fall back
to place search) · offline (cached area only, stated) · dense cluster.

### 4.9 🖥 Contributor / moderation

Queue of pending bins with evidence. Approve / reject / merge / split / retire.
Region rule editor. Edit history. **Debug view: both models' boxes overlaid**, so
a contributor can see *why* a location is failing.

Dense, keyboard-first, utilitarian – the one place information density beats
whitespace, still in the same monochrome language.

### 4.10 ◐ Settings

Language · theme · region · downloaded data (size, clear) · privacy statement ·
about (credits the origin as a TH Deggendorf computer-vision project).

## 5. Cross-cutting states

Design once, reuse everywhere:

- **Connection** – connecting · waking up · connected · slow · busy · offline.
  One consistent, quiet, persistent indicator. Never alarming.
- **Staleness** – consistent visual weakening plus a relative timestamp. A bin
  verified yesterday and one last seen eight months ago must not look alike.
- **Loading** – skeletons, never spinners; never blocking.
- **Empty** – always paired with the one useful action available.
- **Error** – plain sentence, one recovery action, no apology, no emoji.
- **Pending contribution** – clearly "yours, not published yet".

## 6. Deliverables

1. Scanner, every state in § 4.2 – including **locked**, **waking up**, **busy**, **offline**
2. Result cards: confident · hedged · disambiguation · unknown · stale
3. Multi-bin layout – the six-container bank
4. Unknown-bin screen and the contribute flow
5. Rules browser
6. Desktop map + registry, camera-free
7. First run + language picker
8. Dark mode for all of the above
9. **RTL proof** – at minimum the scan result and the desktop map, mirrored in Arabic
10. Moderation/debug view (rough is fine)

Working wordmark: **Smart Bin**. A wordmark using the italic + underline accent
from the system would be welcome.

## 7. Hard constraints

- Scanning needs a connection; **the rules browser must not**.
- No camera UI on devices without a rear camera.
- Multiple bins simultaneously – non-negotiable, it is the headline improvement
  over the predecessor.
- RTL + Devanagari at v1, not retrofitted.
- Never assert a disposal rule the system is not sure about. "We don't know" is
  always available and always well-designed.
