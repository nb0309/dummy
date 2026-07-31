---
sc: "1.3.3"
technique: "sensory-characteristics"
title: "Instructions identify a component by a sensory characteristic alone"
applies_when:
  element_tag: [body]
  requires_column: [sr_sensory_reference]
signals:
  - field: sr_sensory_reference
    look_for: "PRIMARY, but read it as a CANDIDATE LIST rather than as findings. `{references, candidates, truncated}`. Each reference carries the `sentence`, its `categories` (shape/size/position/orientation/colour/sound), the `matched` words, `resolvedCategories` vs `unresolvedCategories`, `namesInSentence` (accessible names of real components appearing in that same sentence) and `resolved` (measured geometry for position claims, computed colour for colour claims). The detector is a word lexicon: it cannot tell an instruction from ordinary prose, and it says so."
  - field: element_html
    look_for: "the whole page, so this is where you confirm what a candidate sentence is actually doing: is it an instruction, and does it identify a component? Also the NON-SENSORY alternatives the probe does not model — a `required` attribute, an asterisk or a \"(required)\" suffix beside a colour-coded label, an `aria-label` on the thing being pointed at, a heading naming the region."
  - field: parent_html
    look_for: "the <html> element, so the <head> stylesheet is here. Useful for seeing WHY something renders where it does (a `flex-direction: row-reverse` explains a panel that is first in source and last on screen) — but trust the probe's measured rect over your own reading of the CSS, because the rect is the rendered result and the CSS is only its cause."
  - field: sr_transcript
    look_for: "what a screen reader actually announces walking the page. This is the test that matters for this criterion: if the instruction says \"the green button\" and the transcript announces only \"button, Confirm\", then the instruction names something the listener never hears. Conversely a name that IS announced is a usable identifier."
---
## Violation criteria (1.3.3 Sensory Characteristics)
**1.3.3 Sensory Characteristics is Level A and is in scope for this page.**

Instructions for understanding and operating content must not rely **solely** on
sensory characteristics of components — shape, colour, size, visual location,
orientation, or sound.

## First, the gate: a lexicon hit is not a finding
This section's detector is a **word list**, and it is the crudest signal in this whole
evidence set. It matches ordinary prose constantly:

- "You have the **right** to appeal" — an entitlement, not a position.
- "See **below** for our address" — points at a section, not a component.
- "A **large** number of appeals" — a quantity.
- "**Green** belt land", "considered in the **round**" — a proper noun and an idiom.

So work through candidates in this order, and expect to dismiss most of them in a
clause:

**1. Is this sentence an instruction, and does it identify a component?** If it is
narrative prose, a heading, a policy statement, or a reference to a document section
rather than a control, 1.3.3 does not apply. Say so and move on. Do **not** flag it.

**2. Only if it survives: is the sensory characteristic the SOLE identifier?**
Mentioning colour, shape or position is *not* the defect and never was. "Press the
green **Confirm** button" is exemplary — the colour helps the people who can see it and
the name serves everyone else. Relying on the characteristic *alone* is the defect.

## Then, the evidence
- **`namesInSentence`** is the closest thing to a mechanical test. Empty means no
  component's accessible name appears in that sentence, so if it *is* an instruction,
  the sensory characteristic is all it offers. Non-empty is weaker than it looks: check
  the name is being used to identify the component and is not a coincidence — in "press
  the red button to **discard** it" the word matches a button named "Discard", but it is
  a verb, not a reference.
- **Resolved position** is measured from the rendered layout, not from source order. A
  panel can be first in the DOM and on the right of the screen; the resolution accounts
  for that and your reading of the CSS should not override it.
- **Resolved colour** is the computed value after cascade. If a colour reference
  resolves to nothing, the sentence may not be about a component at all.
- **Unresolved categories — shape, size, orientation, sound — carry no corroboration.**
  Nothing in a page represents a sound; whether an author meant a given element by
  "round" is not measurable. Judge these from `element_html` and the transcript alone,
  and be willing to say the capture cannot settle it.
- **Look for the alternative the probe does not model.** A red label is fine if the
  input also carries `required`, or the label text ends "(required)", or an asterisk is
  explained. Check `element_html` before concluding colour is load-bearing.

Flag `inaccessible` under `1.3.3` when a sentence instructs the user to find or operate
something and identifies it only by shape, colour, size, position, orientation or sound,
with no name, no text marker and no programmatic alternative anywhere.

## Pass criteria
- The instruction names its referent as well as describing it sensorily — a button's
  accessible name, a region's label, a heading.
- The sensory cue is redundant with a text or programmatic equivalent (`required`
  alongside a red label; "(required)" in the label text).
- No instruction on the page identifies anything sensorily.
- Every lexicon match is ordinary prose that identifies no component.

## Insufficient evidence
- **`truncated: true`** — prose beyond the cap was never scanned.
- A sensory reference whose category is **unresolved** and whose referent cannot be
  identified from the markup either. Say what is missing rather than guessing which
  element was meant.
- Content that renders differently at another viewport: the geometry is measured at one
  width, so a "left/right" claim about a responsive layout holds only for that width.
- A sound cue with no DOM representation at all — you can see that no non-auditory
  equivalent exists, but not what the sound is or when it fires.

## Scope boundary
- Information conveyed by **colour alone with no instruction involved** is **1.4.1 Use
  of Color** — a status shown only as a red dot, a required field marked only by colour
  with no sentence about it. Report that under `1.4.1`, not here. The two overlap often
  and can both apply to one page; use the key that matches what you are describing.
- Whether the *label* of a control is adequate is 2.4.6; whether a control has a name at
  all is 4.1.2. 1.3.3 is about the INSTRUCTION, not the component.
- Whether the reading order makes the instruction land before what it describes is
  1.3.2.

## Examples
- INACCESSIBLE: "press the green button to submit" with two same-shaped buttons →
  `namesInSentence: []`, colour resolves to a Confirm button. Nothing in the sentence
  names it and nothing else distinguishes the two.
- INACCESSIBLE: "use the links on the right to narrow these results" → position resolves
  to three links at the right of the page, none named in the sentence. Note they are
  *first* in source order: the layout is `row-reverse`, which is exactly why the measured
  rect and not the DOM is the evidence.
- INACCESSIBLE: "select the round icon to save" with icon buttons carrying no accessible
  names → shape is unresolved, and the transcript announces only "button", so there is
  nothing for a listener to match "round" against.
- INACCESSIBLE: "fields shown in red are required", with no `required`, no asterisk and
  no text marker → the only carrier of a mandatory field is the label's colour.
- INACCESSIBLE: "drop your files onto the large panel below" and "wait for the beep" →
  two unresolved characteristics, two unnamed panels, and no visual equivalent for the
  sound anywhere.
- ACCESSIBLE: "press the green **Confirm** button" → identical page and identical
  colours to the first example, and it conforms because the sentence names the button.
- ACCESSIBLE: "use the **Refine results** panel on the right" → the position is a
  helpful extra; the panel's `aria-label` is the identifier that works without it.
- ACCESSIBLE: "fields shown in red and marked (required) must be filled in", with
  `required` on the inputs and "(required)" in the label text → colour is redundant
  three times over.
- ACCESSIBLE: a page of prose containing "the right to appeal", "see below for our
  address" and "a large number of appeals" → four lexicon matches, no instruction among
  them, no component identified. Dismiss and return `accessible`.
- ACCESSIBLE: instructions that name every field and control they refer to → no matches
  at all.
