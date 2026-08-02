# What changed in the flow, and why

The brief's screen list was a starting point and the prompt said so: *"restructure
the flow if you see a better one."* This is the design's own account of the seven
changes it made, kept verbatim in substance so the reasoning survives outside
Claude Design. Everything here is implemented in `web/src/features/`.

**1. The scanner is not a screen you leave.**
Answers arrive in a sheet over the live frame, and opening one grows the sheet
instead of navigating away. The user is holding the phone up against the object;
a screen change breaks the correspondence between the number on the tab and the
bin in front of them. "Result" is therefore a state of the scanner, not a
destination.

**2. "Several bins" is not a separate screen.**
It is the sheet's ordinary state. One bin in frame opens its answer immediately –
92% of the archive is a single bin, so the common case skips the list entirely.
Three or six list first. A dedicated bank screen would have re-created the
predecessor's split between "one bin" and "everything else".

**3. Three bins leads; six is labelled a probe.**
Of 466 labelled photographs, 430 hold one bin, 30 hold two, 6 hold three, and
none holds four or more. The three-bin frame is a real archive photograph. The
six-bin frame is a placeholder and says so in the sheet rather than pretending
to be evidence.

**4. Disambiguation is its own interaction, not weak confidence.**
The glass bank does not hedge. It asks which slot, with the three colours quoted,
and the answer rewrites the card in place and re-stamps it "you told us". A
`requires_disambiguation` rule and a `0.55` rule are different products of the
resolver and they read differently on screen.

**5. Coverage has three states, not two.**
Published, draft and no pack at all. Draft is the state every new city passes
through and it is expressed cheaply: an outlined `draft` tag in the register
voice next to the region, plus one plain sentence naming the operator whose
guidance has *not* yet been checked. Published carries the same sentence with a
retrieval date instead. No pack shows the general rules and says plainly that
the mapping to local containers is the part nobody has written down.

**6. Unknown is a level of the answer card, not a fallback.**
Same slot, same position, hatched, opening with the measured colours and the
form factor – the things that are true regardless of coverage – before it says
what it cannot say. It is the only screen where the contribute button is the
primary action.

**7. A submitted contribution claims nothing.**
After sending, the bin reappears in frame with its dashed marker and its card
reads "yours · not published". It shows what you reported – shape and colour –
not a stream, because a report is not an answer until a second person sees the
same thing.

## Where each state lives

Every state is reachable by ordinary use. The state director
(`web/src/dev/DirectorPanel.tsx`, development builds only) is the shortcut.

| State | How to reach it |
|---|---|
| Connecting, waking, searching | Plays automatically on the first scan (about 1.5 seconds) |
| Live, busy, offline | Director · Connection |
| Camera denied | Director · Camera |
| Nothing in frame | Offline and busy both fall back to it; the sheet keeps the rules route |
| Low confidence | Director · Lead answer · Most likely |
| Needs a clarifying question | Bins in frame · 1 |
| Unknown | Every bin in Plattling · bin 6 of the six-bin probe |
| Stale | Director · Lead bin is stale · or bin 2 of the three-bin frame |
| Submitted, not published | Contribute from an unknown bin, then return to the camera |
| Empty region | Coverage · No pack, on either surface |

## One thing the implementation changed

The prototype hand-authored each bin's answer per region. The imported client
does not: it builds an `Observation` from the frame – form factor plus the
colours measured off the pixels – and runs the real resolver against the real
`de-by-deggendorf` pack.

That costs one demonstration and buys a better one. In the three-bin frame the
second and third containers are both grey-on-black wheelie bins, so they now
resolve identically to *Restmüll* rather than to the different answers the
prototype showed. Two visually identical bins getting the same answer is the
honest outcome, and it is what the product will actually do.
