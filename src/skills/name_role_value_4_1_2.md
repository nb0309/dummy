---
sc: "4.1.2"
technique: "name-role-value"
title: "Custom UI component missing or stale role, name, or state"
applies_when:
  element_tag: [div, span, input, select, button, a, li, ul, ol, main, body]
signals:
  - field: sr_transcript
    look_for: "PRIMARY. The STATIC walk of the element. Does the reader announce a role at all (e.g. 'checkbox', 'switch', 'slider'), an accessible NAME alongside it (not just the bare role word), and — for stateful roles — a state or value ('checked' / 'not checked' / 'on' / 'off' / a numeric value)? A role-bearing widget that reads as plain text, or reads a role with no name, or reads a role with no state where one is required, is the core 4.1.2 signal."
  - field: sr_role_state_value
    look_for: "SECONDARY, only present for role/state/value candidates (checkbox/switch/radio/slider/combobox/listbox/option/tab/menuitemcheckbox/menuitemradio/spinbutton roles, native checkbox/radio/range inputs, select, aria-pressed, aria-expanded+aria-controls). An interaction probe: `{before, after}`, each `{phrase, html}`, from clicking the control once. DECISIVE failure pattern: `before.phrase === after.phrase` (nothing was announced as different) while `before.html !== after.html` (something visibly changed, e.g. a CSS class) — the state change never reached the accessibility tree. `null` means this row is not a control (not probed) — judge purely on sr_transcript/element_html instead. A slider/spinbutton showing no change under this click-only probe is NOT itself damning — those are typically keyboard-driven; corroborate with element_html's aria-valuenow/min/max instead."
  - field: element_html
    look_for: "CORROBORATION. The role attribute (present/absent/valid enumerated role); the state/value attributes required by that role (aria-checked for checkbox/switch/menuitemcheckbox/menuitemradio, aria-selected for option/tab, aria-valuenow+aria-valuemin+aria-valuemax for slider/spinbutton, aria-expanded for a disclosure trigger) and whether their VALUES are valid (aria-checked must be true/false/mixed, never an arbitrary string); the accessible-name source (aria-label, aria-labelledby, a wrapping/associated <label>, or visible text content) — or its total absence."
  - field: parent_html
    look_for: "whether a <label for> or a labelling element referenced by aria-labelledby actually exists and contains real text (not aria-hidden, not empty) — this is often the only place the accessible name can be confirmed for a bare custom-control div/span"
---
## Violation criteria (4.1.2 Name, Role, Value)
**4.1.2 Name, Role, Value is Level A and is in scope for this element.**

For every UI component, the **role** must be programmatically determinable,
the **name** (what the control is called) must be programmatically
determinable, and any **state, property, or value that can be set by the
user** must be both programmatically settable and exposed to assistive
technology — and when the user changes it, that change must be exposed too,
without requiring the user to do anything further.

Flag `inaccessible` under `4.1.2` when any of the following holds:

- **No role at all.** A widget built from a bare `<div>`/`<span>` with a click
  handler and no `role` attribute (and no native semantics, e.g. not an
  `<input>`/`<button>`/`<select>`) exposes nothing to the accessibility tree —
  a screen reader reads it as plain text or skips it entirely, never
  announcing it as an interactive control of any kind.
- **Role present, but no accessible name.** `role="checkbox"` /
  `role="switch"` / etc. with no `aria-label`, no `aria-labelledby` pointing at
  real visible text, and no wrapping/associated `<label>` — the reader can only
  ever say "checkbox, not checked" with nothing to say *which* checkbox.
  Text that exists but is marked `aria-hidden="true"` or lives in a sibling
  the control has no reference to does not count.
- **Role present, but the required state/value is missing.** A stateful role
  (`checkbox`, `switch`, `radio`, `menuitemcheckbox`, `menuitemradio`) with no
  `aria-checked`; `option`/`tab` with no `aria-selected`; `slider`/`spinbutton`
  with no `aria-valuenow` (and no `aria-valuemin`/`aria-valuemax`) — the role
  is announced, but there is nothing for the reader to say about its state.
- **State/value present but invalid.** `aria-checked` set to anything other
  than `true`/`false`/`mixed` (e.g. `"yes"`) — assistive tech cannot reliably
  interpret it, so the exposed state is effectively broken even though the
  attribute exists.
- **State exposed but never updated on interaction — the decisive case the
  `sr_role_state_value` probe exists for.** The control visibly responds to a
  click (a CSS class toggles, a checkmark appears) but the underlying
  `aria-checked`/`aria-pressed`/`aria-expanded`/`aria-selected` attribute is
  never touched by the handler. The probe's `before.phrase` and
  `after.phrase` come back identical while `before.html`/`after.html` differ —
  proof the visual and the accessible states have diverged. This is a genuine
  4.1.2 violation even though the *initial* markup looks perfectly correct.

## Pass criteria
All of the following:
- A valid ARIA role is exposed (native semantics from `<input
  type="checkbox">`/`<button>`/`<select>` count as much as an explicit `role`
  attribute).
- An accessible name is present and resolves to real, visible text (`<label
  for>`, `aria-labelledby` referencing real content, `aria-label`, or plain
  text content for a native `<button>`).
- Any required state/value attribute is present with a valid value.
- Where `sr_role_state_value` is populated: `after.phrase` differs from
  `before.phrase` in the way the interaction implies (e.g. "not checked" →
  "checked", "collapsed" → "expanded") — proving the update reaches assistive
  tech, not just the screen. A `slider`/`spinbutton` reading unchanged under
  the click-only probe is not a failure on its own; check its
  `aria-valuenow`/min/max in `element_html` instead.

## Insufficient evidence
- A role-bearing element with no click handler, no keyboard handler, and no
  visual affordance suggesting it is meant to change state — it may simply be
  a static, non-interactive use of a stateful role (unusual, but the capture
  cannot prove intent either way). Return `insufficient_evidence` rather than
  assuming a missing-state-update defect.
- If the accessible name appears to be supplied only via a CSS
  `content:`/background-image technique, it will not appear in `element_html`
  or `sr_transcript`; say what's missing rather than guessing it doesn't exist.

## Examples
- INACCESSIBLE: `<div class="fake-checkbox" onclick="toggle(this)"></div>` →
  no role, no state, no name; `sr_transcript` reads it as ordinary text or
  nothing at all.
- INACCESSIBLE: `<div role="switch" tabindex="0" aria-label="Notifications"
  onclick="toggle(this)">` with the handler only flipping a CSS class → role
  and name are fine, but there is no `aria-checked` at all, so no state is
  ever exposed.
- INACCESSIBLE: `<div role="checkbox" tabindex="0" aria-checked="false"
  onclick="this.classList.toggle('checked')">` (no `aria-checked` update in
  the handler) → `sr_role_state_value` shows `before.phrase === after.phrase`
  while the `checked` class appears in `after.html` — the state change never
  reached the accessibility tree.
- INACCESSIBLE: `<div role="checkbox" aria-checked="false"></div><span
  aria-hidden="true">I agree to the terms</span>` → role and state are fine,
  but there is no accessible name (the only nearby text is `aria-hidden`).
- INACCESSIBLE: `<div role="switch" aria-checked="yes" aria-label="Enable
  dark mode">` → `"yes"` is not a valid `aria-checked` value.
- ACCESSIBLE: `<input type="checkbox" id="marketing"><label
  for="marketing">Email me about new features</label>` → native role, name,
  and state all handled by the browser.
- ACCESSIBLE: `<div role="switch" tabindex="0" aria-checked="false"
  aria-labelledby="notifLabel" onclick="this.setAttribute('aria-checked',
  this.getAttribute('aria-checked')!=='true')">` → `sr_role_state_value` shows
  `after.phrase` announcing the changed state.
