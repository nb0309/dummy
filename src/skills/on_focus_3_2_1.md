---
sc: "3.2.1"
technique: "on-focus-context-change"
title: "Receiving focus initiates a change of context"
applies_when:
  element_tag: [body]
  requires_column: [sr_focus_context]
signals:
  - field: sr_focus_context
    look_for: "PRIMARY. Every focusable component was focused on its own and what changed was recorded: `{components, focusedVia, truncated}`. Per component, FOUR fields are unambiguous changes of context — `focusMovedTo` (focus went elsewhere), `navigatedTo` (the page changed), `opened` (a window was opened), `submitted` (a form was submitted). A FIFTH, `mutations`, is not: it carries `added`/`removed`/`attributes` counts plus `addedNodes` (the markup of what appeared) and `attributeTargets` (what was changed, with its role/id). Any of the four means a failure. Mutations alone mean you have to read what appeared and decide."
  - field: element_html
    look_for: "CORROBORATION, and where the CAUSE is: a `focus`/`focusin` listener, an inline `onfocus`, and crucially WHICH EVENT it is bound to. A handler on `change`, `click` or `input` is out of scope here however drastic its effect — that is 3.2.2 or 3.2.5. Also the thing the mutation produced: a `<p class=\"hint\">` and a `role=\"dialog\"` are both 'one node', and only the markup tells them apart."
  - field: parent_html
    look_for: "the <html> element, so the <head> scripts are here. Handlers attached at document level, or a script that wires focus behaviour to many controls at once, will be visible here when nothing inside the body explains it."
  - field: sr_transcript
    look_for: "what a reader announces walking the page as captured. Useful for judging whether content that appeared on focus would even be noticed, and whether it reads as supplementary help or as a new region taking over."
---
## Violation criteria (3.2.1 On Focus)
**3.2.1 On Focus is Level A and is in scope for this page.**

When any user interface component **receives focus**, it must not initiate a **change
of context** — a change of user agent, viewport, focus, or content that changes the
meaning of the page.

Four things the probe records are changes of context by definition. Any one of them,
on any component, is a failure:

1. **`focusMovedTo`** — focus was moved somewhere else. The user tabbed to a control
   and ended up elsewhere with no explanation.
2. **`navigatedTo`** — the page navigated. Reaching the component took the user off
   the page.
3. **`opened`** — a window or tab was opened.
4. **`submitted`** — a form was submitted.

## First, the gate: a change of CONTENT is not a change of context
This is the trap in 3.2.1 and the reason most of the evidence exists. Components
routinely change the page when focused, and it is **correct**:

- a hint or help text appearing below the field;
- a tooltip showing;
- a combobox expanding its listbox in place, with focus staying on the input;
- the field or its wrapper being highlighted;
- a character counter appearing.

All of those produce DOM mutations. **None is a 3.2.1 failure.** Flagging them would
condemn most well-built forms, so a `mutations`-only result is never enough on its own.

A mutation *becomes* a change of context when what appeared takes over rather than
assists. Read `addedNodes` and `attributeTargets` and ask what actually showed up:

- a `role="dialog"`/`aria-modal="true"` element becoming visible — almost always a
  change of context, especially with `focusMovedTo` alongside it. Note this case
  produces **no added node at all**: the dialog was already in the DOM and only its
  `hidden`/`class`/`style` changed, so the attribute target is the entire signal.
- page content being replaced, a region swapped out, results reloaded — the meaning of
  the page changed.
- versus a `<p class="hint">`, an `<li role="option">`, a class change — supplementary
  or presentational, and fine.

Flag `inaccessible` under `3.2.1` when any component shows one of the four
unambiguous changes, or when a mutation on focus amounts to the page changing meaning.

## Pass criteria
- Every component held focus, and nothing navigated, opened or submitted.
- The only changes were supplementary content (a hint, a tooltip, listbox options) or
  presentational (classes, styling, highlighting).
- A combobox expanded on focus **and focus stayed on the input** — the ARIA authoring
  practice, not a defect.
- Nothing changed at all.

## Insufficient evidence
- **`truncated: true`** — the probe hit its component cap, so components beyond it were
  never focused. A clean result does not cover them; say so.
- **No focusable component on the page** — nothing for the criterion to apply to.
- `focusedVia` is `"programmatic"`. A handler gated on `event.isTrusted` or on
  `:focus-visible` does not run for programmatic focus, so a page whose `element_html`
  shows such a guard has **not** been exercised by this probe. Report what was not
  testable rather than reading silence as a pass.
- A change of context on a timer longer than the probe's settle window would also be
  missed. If `element_html` shows a `setTimeout` in a focus handler, say so.

## Scope boundary
- A change of context on **changing a setting** — `change`, `input`, selecting an
  option, ticking a box — is **3.2.2 On Input**, not 3.2.1. Report it under `3.2.2`.
  The distinction is the event, not the severity: the same jump-menu navigation is a
  3.2.1 failure on `focus` and a 3.2.2 question on `change`.
- A change of context the user **explicitly requested** (activating a link or button)
  is allowed, and is 3.2.5's territory only when it is automatic and unrequested.
- The **order** focus moves in is 2.4.3. Focus that cannot be moved away at all is
  2.1.2. Judge only what happens *when a component receives focus* here.
- A component grabbing focus **on page load** is not this criterion either — nothing
  "received focus" through user action.

## Examples
- INACCESSIBLE: a jump-menu `<select>` with a `focus` listener setting
  `location.href` → `navigatedTo` is set; a keyboard user tabbing past the control is
  taken off the page and can never reach the fields below it.
- INACCESSIBLE: a card-number field whose `focus` handler calls
  `securityCode.focus()` → `focusMovedTo` is the security code. The user tabs to one
  field and lands in another.
- INACCESSIBLE: a checkbox whose `focus` handler calls `window.open("/terms")` →
  `opened` lists the URL. A link to the same terms would have been fine; doing it on
  focus is not.
- INACCESSIBLE: focusing an address field un-hides a `role="dialog" aria-modal="true"`
  and focuses inside it → `mutations.attributes` shows `hidden` changing on the dialog
  and `focusMovedTo` is a control inside it. **Zero nodes added** — the attribute
  target is the evidence.
- INACCESSIBLE: a filter form whose sort `<select>` calls `form.submit()` on focus →
  `submitted` names the form; tabbing through discards what the user typed above.
- ACCESSIBLE: focusing a passport field appends a `<p class="hint">` below it → one
  node added, focus held, nothing else. Content changed, context did not. **This is
  the case that must not be flagged.**
- ACCESSIBLE: focusing a field adds an `active` class to its wrapper → attribute
  changes only, purely presentational.
- ACCESSIBLE: a `role="combobox"` that expands its listbox and flips `aria-expanded`
  to `true` on focus, with focus remaining on the input → three `role="option"` nodes
  added, `focusHeld` true. The most visible mutation in a passing page, and still not a
  change of context.
- ACCESSIBLE for 3.2.1: the same jump menu wired to `change` instead of `focus` →
  nothing at all happens on focus. Whether navigating on `change` is itself a defect is
  3.2.2's question; report it there, not here.
- ACCESSIBLE: a form with no scripts → no component changes anything.
