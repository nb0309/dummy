---
sc: "3.2.2"
technique: "on-input-context-change"
title: "Changing a setting causes an unannounced change of context"
applies_when:
  element_tag: [body]
  requires_column: [sr_input_context]
signals:
  - field: sr_input_context
    look_for: "PRIMARY. Every component with a SETTING had it changed, one at a time: `{components, changedVia, truncated}`. Four fields are unambiguous changes of context — `focusMovedTo`, `navigatedTo`, `opened`, `submitted`. `mutations` is the ambiguous one, carrying `addedNodes` markup and `attributeTargets`. **`advisory` is what decides the criterion**: `describedBy` (announced with the control), `precedingText` (text before it in its group), `label` (its name, which is NOT advice), `hasText`. A change of context here is only a failure when no advisory warned of it. Also `note`, present when a component could not be measured because focusing it already changed context — that is 3.2.1's finding, not this one's."
  - field: element_html
    look_for: "CORROBORATION and cause: which EVENT the handler is bound to. `change`/`input` is 3.2.2; `focus` is 3.2.1; `click` on a button or link is a user request and out of scope for both. Also the warning text itself and how it is wired — an `aria-describedby` pointing at it, or a bare paragraph beside it — and whether it sits before or after the control in source order."
  - field: parent_html
    look_for: "the <html> element, so the <head> scripts are here. A delegated `change` listener on the form or document, which nothing inside the body would explain, shows up here."
  - field: sr_transcript
    look_for: "whether a warning is actually ANNOUNCED, and where in the reading order it falls. A warning that a screen reader reaches only after the control has already been operated has not advised anyone in time — 3.2.2 says 'before using the component'."
---
## Violation criteria (3.2.2 On Input)
**3.2.2 On Input is Level A and is in scope for this page.**

Changing the setting of any user interface component must not automatically cause a
change of context **unless the user has been advised of the behaviour before using the
component**.

Four recorded signals are changes of context by definition:

1. **`navigatedTo`** — the page navigated.
2. **`opened`** — a window or tab was opened.
3. **`submitted`** — a form was submitted.
4. **`focusMovedTo`** — focus was moved somewhere the user did not put it.

## First, the gate: a change of context here is only HALF a failure
This is where 3.2.2 parts company with 3.2.1, and getting it wrong flags conforming
pages. On focus, a change of context is simply a defect. On input, the criterion
**permits** it when the user was warned first. So the finding is never the change alone
— it is the change **plus the absence of an advisory**.

Read the `advisory` block for the offending component and judge the text on its own
terms:

- **`describedBy`** — strongest. Attached with `aria-describedby`, so it is announced as
  part of the control and cannot be missed on the way past.
- **`precedingText`** — weaker but real. Text before the control in its group is read
  before it, which is what "before using the component" asks for.
- **`label`** — **not advice.** A control's name identifies it; it says nothing about
  what changing it will do. It is reported separately and must never be counted as a
  warning.
- **`hasText: true` does not mean "advised".** It means there is text worth reading. A
  hint saying "We only use this to send you updates" sets it true and warns nobody. Ask
  whether the wording actually says this control will move, submit, or navigate.

Confirm in `sr_transcript` that the warning is announced, and in `element_html` that it
sits **before** the control. A warning printed underneath is not a warning.

## Then, the ambiguous half
A component that only mutated the DOM changed **content**, not necessarily context.
Revealing conditional fields when a checkbox is ticked, or updating a result count as
the user types, is ordinary and correct — focus stays, nothing navigates. Read
`addedNodes` and ask whether the page now *means* something different: a swapped-out
content region with a new heading and new links is a change of context even though
nothing navigated; two extra fields under the box that revealed them are not.

Flag `inaccessible` under `3.2.2` when a component shows one of the four unambiguous
changes on input **and** no advisory warns of it, or when a mutation on input replaces
the page's subject matter without warning.

## Pass criteria
- No component changed context when its setting changed.
- A component did change context, **and** an advisory before it says so — the exception
  is met, and the page conforms even though the behaviour is identical to a failing one.
- The change of context happens on **activating a button or link** instead, which is a
  user request. (Those are not probed at all, deliberately.)
- The only changes were revealed content, updated counts, or styling, with focus intact.

## Insufficient evidence
- **`truncated: true`** — the cap was reached and later components were never tried.
- **`settingChanged: false`** — the probe could not alter that control's setting (a
  single-option `<select>`, a control with no value), so it was never exercised.
- `changedVia` is `"dispatched"`. The events are synthetic, so a handler gated on
  `event.isTrusted` never ran. If `element_html` shows such a guard, say the page was
  not exercised rather than reading silence as a pass.
- A component carrying a **`note`** was skipped because focusing it changed context
  before its setting could be changed. Report that under 3.2.1 and return no 3.2.2
  finding for it.

## Scope boundary
- A change of context on **receiving focus** is **3.2.1 On Focus**. The probe already
  excludes it — each component is focused and left to settle before recording starts —
  so anything reported here was caused by the setting changing, not by focus arriving.
- A change of context the user **requested** by activating a button or link is permitted;
  3.2.5 Change on Request governs whether it should be automatic at all.
- Whether the control's state is exposed to assistive technology is **4.1.2**.
- Whether the user is warned in a way that is *findable* is a labelling question (3.3.2)
  if the text exists but is not associated; judge the 3.2.2 exception on whether it
  reaches the user in time, and note the association problem separately.

## Examples
- INACCESSIBLE: a jump-menu `<select>` navigating on `change`, with no advisory →
  `navigatedTo: "/renew"`, `advisory.hasText: false`. A keyboard user arrowing through
  the options is taken away on the first one they land on.
- INACCESSIBLE: filter checkboxes calling `form.submit()` on `change` → `submitted`, no
  advisory; three filters mean three page loads and everything typed above is lost.
- INACCESSIBLE: delivery radios calling `window.open` on `change` → `opened`, no
  advisory. A link to the same terms beside each option would have been fine.
- INACCESSIBLE: date boxes moving focus to the next once full → `focusMovedTo` on input.
  Focusing them does nothing, so 3.2.1 has no finding; the defect is entirely 3.2.2's.
- INACCESSIBLE: a `<select>` whose `change` handler replaces the content region with a
  different heading, body and links → mutation only, nothing navigated, but the page now
  means something else and nobody was told.
- ACCESSIBLE: **the same jump menu with a warning.** `navigatedTo: "/renew"` exactly as
  the failing fixture, but `advisory.describedBy` reads "Selecting a service takes you
  straight to that service's page." The measurement is identical; the exception is met.
- ACCESSIBLE: the same select with the navigation moved to a **Go** button → nothing at
  all happens on input. The better fix, and it needs no warning.
- ACCESSIBLE: a checkbox revealing two conditional address fields → nodes added, focus
  held, nothing navigated. Content changed, context did not.
- ACCESSIBLE: typing updating a result count in a `role="status"` live region → the
  count is announced without moving the user anywhere.
- ACCESSIBLE: a form with no scripts → no component changes anything on input.
