---
sc: "2.1.2"
technique: "keyboard-trap"
title: "Keyboard focus cannot be moved away from a component"
applies_when:
  element_tag: [body]
  requires_column: [sr_keyboard_trap]
signals:
  - field: sr_keyboard_trap
    look_for: "PRIMARY. The escape ladder: `{stops, outcome, cycle, region, reverse, escape}`. `outcome` says how the forward Tab sweep ended — `escaped` (focus left the page: no trap), `stalled` (the same control twice: focus is pinned), `cycled` (an already-visited control returned: focus is looping), `cap` (inconclusive). `reverse` and `escape` record whether Shift+Tab and then the Escape key got focus back out. Read the outcome FIRST, then the recoveries: the outcome alone never decides this criterion."
  - field: element_html
    look_for: "CORROBORATION, and the only place the CAUSE is visible: a `keydown` handler calling `preventDefault()` on the Tab key; a wrap that focuses the first control when Tab is pressed on the last; a `focusin`/`blur` handler that pulls focus back; whether an `Escape` branch exists at all. Also the instruction text and `aria-keyshortcuts` that decide the 'advised of the method' clause, and whether the region is a `role=\"dialog\"`/`aria-modal` (where containing focus is CORRECT) or an ordinary widget (where it is not)."
  - field: parent_html
    look_for: "the <html> element, so the <head> scripts are here. A trap is almost always JavaScript, and this is where a document-level key or focus handler will be found when nothing inside the body explains the behaviour."
  - field: sr_transcript
    look_for: "whether an instruction for leaving the component is actually ANNOUNCED. The probe's `region.advisory` finds text sitting beside the controls, but text that a reader never reaches has not advised anyone of anything. Confirm here before accepting an advisory as sufficient."
---
## Violation criteria (2.1.2 No Keyboard Trap)
**2.1.2 No Keyboard Trap is Level A and is in scope for this page.**

If keyboard focus can be moved *to* a component using a keyboard, then focus must be
able to move *away* from that component using only a keyboard — and if that takes
more than unmodified arrow or Tab keys, the user must be **advised of the method**.

## First, the gate: containment is not the defect
This is the one page-level criterion where the obvious signal is the wrong one.
A modal dialog is **supposed** to cycle Tab within itself while it is open; that is
the ARIA authoring practice, not a bug. A grid, a tree or a text editor is entitled
to consume Tab for its own purposes. What 2.1.2 forbids is keeping focus with **no
way out**.

So `cycled` and `stalled` are **not findings on their own**. They only tell you focus
is being held. What decides the criterion is whether anything released it.

**The evidence block states that resolution in its FIRST observation, as `ESCAPABLE`
or `NOT ESCAPABLE`. That line is decisive for the mechanical half of this criterion —
read it before the detail underneath it, and do not let the loop, the stall or the
blocked Shift+Tab talk you out of it.** Those three are what a *conforming* modal
dialog looks like; they appear on passing and failing pages alike.

| `outcome` | `reverse.exited` | `escape.exited` | verdict |
|---|---|---|---|
| `escaped` | — | — | `accessible` — Tab alone left the page |
| `stalled`/`cycled` | true | — | not a trap: the component can be left backwards |
| `stalled`/`cycled` | false | true | `accessible` — Escape is the documented way out |
| `stalled`/`cycled` | false | false | **trap**, unless an advertised method excuses it |
| `cap` | — | — | `insufficient_evidence` |

## Then, the advisory clause
The bottom row is the only one needing judgement. When no key in the ladder released
focus, check whether the page tells the user what would:

- `region.advisory` — text inside the region that belongs to no control, which is
  where an instruction like "press Escape to leave the calendar" is written.
- `region.describedBy` — the region's and the controls' `aria-describedby` text.
- `region.keyshortcuts` — an `aria-keyshortcuts` value is an explicitly advertised
  key, and the probe's fixed ladder may simply not have pressed it.
- `sr_transcript` — **confirm the advisory is actually announced.** An instruction
  the reader never reaches has advised nobody, and a keyboard-only user of a screen
  reader is exactly who this clause protects.

An advisory that names a method is a pass **only if it names a method**. Generic
prose that happens to sit next to the widget ("Choose a date", "Enter your promotion
code") is not advice about moving focus away.

Flag `inaccessible` under `2.1.2` when:

- Focus is pinned on one control (`stalled`) and neither Shift+Tab nor Escape moves
  it — a `keydown` handler is calling `preventDefault()` on Tab with no release.
- Focus loops over a set of controls (`cycled`), no recovery key works, and there is
  no instruction and no `aria-keyshortcuts` naming one — including when the region is
  a `role="dialog"`: a modal with a focus trap and no Escape handler and no close
  control is a trap, dialog or not.
- A `focusin`/`blur` handler returns focus to a field (validation "jail"), so no key
  reaches anything else.
- A widget consumes Tab in **both** directions and advertises no alternative.

## Pass criteria
- `outcome: escaped` — Tab walked the page and focus left the document.
- Focus is contained but `reverse.exited` is true: the component can be backed out of
  with Shift+Tab.
- Focus is contained but `escape.exited` is true — the standard dialog pattern.
  `escape.regionHidden: true` (the dialog closed) makes this unambiguous, but focus
  simply moving outside the trapped set is enough.
- A widget that handles Tab itself but releases focus while doing so (a picker that
  closes and moves focus on to the next field).
- A composite widget that consumes Tab but announces a working alternative and the
  alternative is corroborated by `element_html` and `sr_transcript`.

## Insufficient evidence
- **`outcome: cap`** — the sweep neither left the page nor repeated a stop, so it
  never established anything. A page with more focusable components than the cap
  produces exactly this. Say so and return `insufficient_evidence`.
- **Fewer than two stops with `outcome: escaped`** — one focusable component that
  releases focus immediately is not enough to be about anything, but it is also not a
  trap; prefer `accessible` unless something is holding focus.
- An `aria-keyshortcuts` naming a key the ladder never pressed (`Control+M`), with no
  visible or announced instruction. The component may well be escapable; the capture
  cannot show it. Report what is missing rather than flagging it.
- Content in an `<iframe>`, `<object>` or `<embed>`: `activeElement` in the top
  document is the container element, so a trap *inside* it is indistinguishable from
  a stall *on* it. Say which one the markup suggests and stop there.

## Scope boundary
- Whether the ORDER of the stops preserves meaning is 2.4.3 (Focus Order). A trapped
  page usually has a terrible order too; do not report it here.
- Focusable content the sweep never reaches at all is 2.1.1 (Keyboard).
- Whether the focused element is visibly indicated is 2.4.7 (Focus Visible). This
  ladder says nothing about focus styling.
- A control with no accessible name at a stop is 4.1.2's question. Note it if it
  makes the ladder unreadable, but flag it under 4.1.2.

## Examples
- INACCESSIBLE: a `role="dialog" aria-modal="true"` whose keydown handler wraps Tab
  from the last control to the first and Shift+Tab from the first to the last, with
  no `Escape` branch → `cycled` over 2 controls, `reverse.exited: false`,
  `escape.exited: false`. Correct containment, no exit.
- INACCESSIBLE: a `<textarea>` whose handler tests `event.key === "Tab"` and calls
  `preventDefault()` to insert an indent → `stalled` on that one control. Testing
  `key` alone blocks Shift+Tab as well, so both directions are dead.
- INACCESSIBLE: a `role="grid"` calendar consuming Tab in both directions, arrow-key
  driven, with no instruction and no `aria-keyshortcuts` → `stalled`, and
  `region.advisory` is empty. Arrow keys inside are fine; the silence is not.
- INACCESSIBLE: a document-level `focusin` handler refocusing an invalid email field
  → `stalled`, and the field cannot even be left to read the rest of the form.
- INACCESSIBLE: a `role="toolbar"` wrapping Tab across its three buttons → `cycled`
  over 3, no recovery, and unlike a dialog there is no reason to contain focus at all.
- ACCESSIBLE: the same wrapping dialog, plus an `Escape` branch that hides it and
  returns focus to its opener → `cycled`, but `escape.exited: true` and
  `escape.regionHidden: true`. The cycle is identical to the failing dialog's; the
  exit is the whole difference.
- ACCESSIBLE: the same grid, plus an Escape handler moving focus to the Continue
  button and the text "Use the arrow keys to choose a date, then press Escape to
  leave the calendar" inside the grid, with `aria-keyshortcuts="Escape"` on the cells
  → `stalled`, `escape.exited: true`, advisory names the method.
- ACCESSIBLE: a `role="radiogroup"` with roving tabindex where arrow keys move the
  selection and Tab is never intercepted → `outcome: escaped`.
- ACCESSIBLE: a date picker open at load whose Tab handler closes it and moves focus
  to the next field → `escaped`; handling Tab is allowed, keeping focus is not.
- ACCESSIBLE: a plain form with no scripts → `escaped` after every control.
