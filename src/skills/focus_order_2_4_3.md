---
sc: "2.4.3"
technique: "focus-order"
title: "Keyboard focus order does not preserve meaning or operability"
applies_when:
  element_tag: [body]
  requires_column: [sr_focus_order]
signals:
  - field: sr_focus_order
    look_for: "PRIMARY. The Tab sweep: `{stops, complete, truncated, stalled}`. Each stop carries the announced `phrase`, its `tabindex`, its `domIndex` (source order), its document-relative `rect` (where it sits on screen), `obscured` (whether something is painted on top of it), and `controls`/`controlsRange` (the subtree this control claims to reveal). Read the stops IN ORDER and ask the question 2.4.3 actually asks: would a person moving through the page this way still understand it and still be able to operate it?"
  - field: sr_transcript
    look_for: "The static walk IS the screen-reader reading order. Compare it against the tab order directly: a page where the reader reads A then B, but the keyboard reaches B then A, is telling you the two sequences disagree. This is the 'spoken context' half of the judgement and it needs no extra probe."
  - field: element_html
    look_for: "CORROBORATION, and the only place the CAUSE is visible: positive `tabindex` values; CSS that reorders visually (`order`, `flex-direction: row-reverse`, `position: absolute/fixed`); a revealed panel rendered far from the `aria-expanded` button that controls it; an `aria-modal` dialog with nothing inert behind it; whether a skip link is genuinely first."
  - field: parent_html
    look_for: "the <html> element, so the <head> stylesheet is here. This is where an `order:` or absolute-positioning rule that moves content visually will be found, when element_html only shows the DOM sequence it fights with"
---
## Violation criteria (2.4.3 Focus Order)
**2.4.3 Focus Order is Level A and is in scope for this page.**

If a page can be navigated sequentially and the navigation sequence affects
meaning or operation, focusable components must receive focus in an order that
**preserves meaning and operability**.

There is no mechanical test for "preserves meaning" — that is the judgement you
are being asked to make. The sweep gives you what a person would look at: the
order focus actually moved in, what was announced at each stop, where each stop
sits on screen, and where it sits in the source.

## How to read the sweep
Four things in the data are strong, near-mechanical evidence:

1. **Tab order vs visual order.** Sort the stops by position (top to bottom, then
   left to right) and compare with the tab sequence. A mismatch means the keyboard
   path and the visual path disagree.
2. **Tab order vs source order** (`domIndex`). Tab order normally follows source
   order; when it does not, something is overriding it.
3. **Positive `tabindex`.** Any value above 0 imposes an arbitrary sequence and is
   almost always the cause of a mismatch.
4. **`obscured: true`.** Focus landed on something with another element painted on
   top of it — content the user cannot see or click. Several consecutive obscured
   stops is the signature of an open modal with a live page behind it.

**A clean result on all four does NOT mean the order preserves meaning.** Two real
failures leave every one of those checks looking perfectly normal, and you must
check for them explicitly:

- **An open dialog the sequence reaches late.** `element_html` shows a visible
  `role="dialog"`/`aria-modal="true"`, but the early stops are content behind it.
  The obscured flag usually catches this — but if the overlay does not cover them,
  the geometry can look entirely reasonable while the user is still trapped
  answering a dialog they cannot reach.
- **Revealed content detached from its trigger.** A stop has `aria-expanded="true"`
  and `controls`/`controlsRange`. Check whether the NEXT stop's `domIndex` falls
  inside `controlsRange`. If it does not, the content that button just revealed is
  not where the user arrives — focus went off to unrelated controls first and the
  revealed content is reached later, or not at all. Visual and source order can
  both be perfectly consistent while this is true.

Flag `inaccessible` under `2.4.3` when any of the following holds:

- Tab order contradicts the visual reading order, so a keyboard user is moved
  around the page in an order that does not match what they can see.
- Positive `tabindex` values impose a sequence unrelated to the visual or source
  order (jumping into the middle of a form, then back to the top).
- A region drawn early on the page is reached last (or the reverse) because source
  order fights the layout — an absolutely-positioned banner or filter panel placed
  at the end of the DOM, or a control moved by `order:` in flex.
- Focus lands on content that is **obscured** — behind a modal overlay, off-screen,
  or otherwise covered.
- Content revealed by an expanded control is not reached from that control: the
  next stop is outside its `controlsRange`.
- The sequence separates a control from the context that gives it meaning, so what
  is announced at a stop no longer makes sense in the order it arrives.

## Pass criteria
- The tab sequence matches the visual reading order **and** the reader's reading
  order in `sr_transcript`.
- `tabindex` is only ever `0` (join the sequence in place) or `-1` (out of the
  sequence, focusable programmatically).
- No stop is `obscured`.
- Where a control reveals content, focus moves into that content next
  (`controlsRange` contains the next stop's `domIndex`).
- A skip link, if present, is the first stop — that is the only position where it
  is useful.
- An open modal is the first thing in the sequence, and the content behind it is
  removed from the sequence (`inert`, or not focusable).

## Insufficient evidence
- **`truncated: true`** — the sweep hit its cap, so the full sequence was never
  observed. Say so and return `insufficient_evidence`; do not judge the order from
  a partial sweep.
- **Fewer than two stops** — one focusable component, or none, is not a sequence.
  There is nothing for 2.4.3 to be about.
- Where the visual order is genuinely ambiguous — a grid or card layout that reads
  equally well by row or by column — say the intended order cannot be determined
  from the capture rather than inventing one and flagging against it.
- Reading position is measured from `rect`, so content positioned by transforms or
  painted by CSS may not sit where the numbers suggest. If the geometry looks
  implausible against the markup, trust the markup and say why.

## Scope boundary
- **`stalled: true` is a keyboard trap** — focus stopped advancing. That is 2.1.2
  (No Keyboard Trap), which has its own skill (`2.1.2/keyboard-trap`) and its own
  probe: escapability is decided by whether Shift+Tab or Escape releases focus, which
  this sweep never tries. Report the stall in your reason and attribute it to 2.1.2;
  do **not** flag 2.4.3 for it, and do not conclude it is a trap from this sweep
  alone. Likewise, focusable content the sweep never reaches at all is 2.1.1
  (Keyboard).
- Whether the focused element is **visibly indicated** is 2.4.7 (Focus Visible).
  This sweep says nothing about focus styling.
- Whether link *text* makes sense on its own is 2.4.4 (Link Purpose); whether
  headings and labels describe content is 2.4.6. Judge only the **order** here.
- A control with no accessible name at a stop is 4.1.2's question. Note it if it
  makes the sequence unintelligible, but flag it under 4.1.2, not 2.4.3.

## Examples
- INACCESSIBLE: `tabindex="3"/"1"/"2"` on three form fields → tab order is Phone,
  Best time, Your name while both the visual order (`y` 102, 177, 252) and source
  order say Your name first. Positive tabindex, and both comparisons inverted.
- INACCESSIBLE: `.actions { order: -1 }` puts the submit button at the top of a
  flex column but leaves it last in the DOM → the button is at `y=80`, above three
  fields at 147/222/297, yet it is the final stop. Visual order inverted, source
  order clean — the CSS in `parent_html` is the cause.
- INACCESSIBLE: a filter panel at `position: absolute; top: 0` written last in the
  DOM → its links are drawn at `y=16` but reached after every search result at
  `y=220`+.
- INACCESSIBLE: an `aria-modal` dialog placed last in the DOM with a live page
  behind it → stops 1–3 come back `obscured: true`; the user tabs three links they
  cannot see before reaching the dialog.
- INACCESSIBLE: an `aria-expanded="true"` button with `aria-controls="deliveryPanel"`
  whose panel is appended at the end of the document → the next stop after the
  button is a footer link, outside `controlsRange`; the radios it revealed come
  last. Visual and source order both look fine.
- ACCESSIBLE: a form with no `tabindex` where source order is visual order → tab,
  visual and source sequences all agree.
- ACCESSIBLE: `tabindex="0"` on a custom `role="switch"` in place, `tabindex="-1"`
  on a decorative glyph → the switch joins the sequence where it sits and the
  decoration stays out of it.
- ACCESSIBLE: a skip link first in the DOM and first on screen, targeting
  `<main id="main-content" tabindex="-1">` → it is the first stop, which is what
  makes it usable at all.
- ACCESSIBLE: an expanded disclosure whose panel immediately follows its button →
  the next stop's `domIndex` is inside `controlsRange`.
- ACCESSIBLE: an open dialog first in the DOM with `<main inert>` behind it → only
  the dialog's own controls appear in the sweep, none obscured.
