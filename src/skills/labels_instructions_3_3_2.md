---
sc: "3.3.2"
technique: "labels-instructions"
title: "Form field missing a label, or an instruction that does not reach the user"
applies_when:
  element_tag: [form, fieldset, select, input, textarea, label]
  requires_column: [sr_label_instruction]
  requires_column_if_tag: []
signals:
  - field: sr_label_instruction
    look_for: "PRIMARY. One entry per field, each `{field, before, after}` with `{phrase, html}`. The reader read the field, a value was entered, then it read again. DO NOT judge on 'the phrase changed' — it always changes, because the entered value becomes one of the announced segments. The decisive test is SEGMENT LOSS: split `before.phrase` on ', ', drop the leading role word, and check each remaining segment still appears in `after.phrase`. A segment present BEFORE and missing AFTER is a label or instruction that existed only while the field was empty. Two further tells in `before.phrase`: a name announced with a literal 'placeholder ' prefix came from the placeholder attribute and is not a real label; a trailing 'required' segment is the only proof the field's mandatory state is exposed."
  - field: sr_transcript
    look_for: "SECONDARY, and the ONLY place group-level context appears — the probe reads each field in isolation, so a <fieldset>/<legend> never shows up there. A correctly grouped question reads as 'group, <legend>, <hint>' before its fields. Also the place an unassociated instruction gives itself away: it is announced as a loose 'paragraph'/bare text at the end of the form, never as part of any field's announcement."
  - field: element_html
    look_for: "CORROBORATION. Whether each control has a <label for> whose id actually exists, a wrapping <label>, aria-label or aria-labelledby; whether a format/constraint instruction exists anywhere in the form and whether it is wired to its field with aria-describedby; whether required-ness is stated in text or only implied by a CSS ::after asterisk / colour; whether a placeholder is doing a label's job."
  - field: parent_html
    look_for: "whether an instruction, legend or label that the field references lives outside the form itself, and whether it contains real visible text (not aria-hidden, not empty)"
---
## Violation criteria (3.3.2 Labels or Instructions)
**3.3.2 Labels or Instructions is Level A and is in scope for this element.**

When content **requires user input**, labels or instructions must be provided. A
label names what the field wants; an instruction states any format, constraint or
requirement the user cannot infer. Both must be available to everyone, and both
must still be available **once the field is in use** — not only while it is empty.

## Note on the capture
When `sr_label_instruction` is present, this form was captured with the 3.3.2
probe: for every field the reader announced it, a value was entered, and it
announced it again. Judge that by **segment loss**, never by "the phrase
changed" — the entered value always joins the announcement, so every field's
phrase differs.

When this row is a single control (`<select>`, `<input>`, `<textarea>`) and
`sr_label_instruction` is absent, judge from `element_html`, `parent_html` and
`sr_transcript` only: a control with no associated `<label for>` / wrapping
`<label>` / `aria-label` / `aria-labelledby`, or whose only name is a
placeholder, fails 3.3.2. Adjacent visible text that is not programmatically
tied to the control does not count as a label.

Flag `inaccessible` under `3.3.2` when any of the following holds:

- **No label at all.** A field whose `before.phrase` is the bare role word
  (`"textbox"`, with nothing after it) has no accessible name from any source. A
  visible `<label>` that is not associated — no `for`, not wrapping the input, or
  a `for` pointing at an id that does not exist — produces exactly this: sighted
  users see a labelled field, the accessibility tree has an anonymous one.
- **A placeholder doing the label's job.** `before.phrase` names the field with a
  literal `placeholder ` prefix, and that name is **gone** from `after.phrase`.
  The prompt was painted inside the box and is destroyed by the act of using the
  field — for everyone, not just screen-reader users.
- **An instruction that does not survive input.** A description present in
  `before.phrase` and missing from `after.phrase`: a hint wired to the empty
  state and removed on first keystroke. The markup passes inspection at rest and
  fails in use, which is precisely what the static transcript cannot show.
- **A required format or constraint that is never conveyed to the field.** The
  form states a rule ("Dates must be entered as DD/MM/YYYY") but no field's
  `before.phrase` carries it as a description, and `element_html` shows no
  `aria-describedby`. In `sr_transcript` the rule reads as a loose `paragraph`
  adrift at the end of the form. The instruction exists on the page; it never
  reaches the control it governs.
- **Required-ness signalled by colour or a decorative marker alone.** Mandatory
  fields marked only by a red `::after` asterisk, with no `required`, no
  `aria-required`, and no text saying what the marker means. No field's
  `before.phrase` ends in a `required` segment, and nothing in the text explains
  the convention.

## Pass criteria
- Every field that requires input announces a real name in `before.phrase`, and
  that name is **still present** in `after.phrase`.
- Any format, constraint or example is announced as part of the field's own
  phrase (via `aria-describedby`, or text inside a wrapping `<label>`), or — for
  a question answered by several controls — as part of the group in
  `sr_transcript` (`group, <legend>, <hint>`), and it likewise survives input.
- Mandatory fields state it in text and/or announce a `required` segment.
- An `aria-label` with no visible label is acceptable where the visual design
  genuinely carries the meaning (a search row beside a "Search" button), provided
  an instruction is still supplied where one is needed.

## Insufficient evidence
- **Group-level instructions and the field-scoped probe.** The probe reads each
  field in isolation, so a `<fieldset>`/`<legend>` and a hint attached to the
  *group* will not appear in any field's `before.phrase`. Do not read that
  absence as a missing instruction — check `sr_transcript` for a
  `group, <legend>, <hint>` announcement first, and only conclude the instruction
  is missing if it is absent there too.
- A field whose label or hint appears to be supplied by CSS `content:` or a
  background image will not be in `element_html` or the transcript; say what was
  missing rather than asserting it does not exist.
- A form of entirely self-evident controls with no format constraints may
  genuinely need no instruction beyond its labels — 3.3.2 requires labels **or**
  instructions as the content demands, not both everywhere.

## Scope boundary
3.3.2 judges only what is provided **before and during** input:
- **Error text after a failed submit is 3.3.1**, not this skill. Do not flag 3.3.2
  because a form lacks error messaging.
- **How to correct an error is 3.3.3.**
- **Whether related controls are grouped in a `<fieldset>`/`<legend>` is 1.3.1**
  (`form-control-grouping`). Here a legend matters only as a carrier of the
  group's label/instruction, not as a grouping mechanism.
- A missing accessible name on a *non-form widget* (a custom switch, a toggle) is
  4.1.2's question. This skill is about controls that take user input.

## Examples
- INACCESSIBLE: `<select onchange="location.href=this.value"><option>QUICKMENU
  -----></option>…</select>` with no `<label for>` / wrapping label /
  `aria-label` — a lone control row with no probe; adjacent "QUICKMENU" text is
  not programmatically tied to the field.
- INACCESSIBLE: `<input type="email" id="email" placeholder="Email address">` →
  `before` "textbox, placeholder Email address" → `after` "textbox,
  someone@example.com". The name is placeholder-derived and does not survive input.
- INACCESSIBLE: `<label>Full name</label><input type="text" id="fullname">` (no
  `for`, not wrapping) → `before` is the bare "textbox"; the label is decorative.
- INACCESSIBLE: `<label for="phone-number">Telephone number</label><input
  id="phone">` → `for` names an id that does not exist, so again a bare "textbox".
- INACCESSIBLE: a hint wired with `aria-describedby` that an `oninput` handler
  removes → `before` "Password, Must be at least 12 characters and include a
  number" → `after` "Password, Passw0rd!". The instruction is lost exactly when
  it is needed.
- INACCESSIBLE: `<p class="footnote">Dates must be entered as DD/MM/YYYY.</p>` at
  the foot of the form, no `aria-describedby` → fields announce
  "textbox, Appointment date" with no description; the rule reads as a stray
  paragraph in `sr_transcript`.
- INACCESSIBLE: `.required-field label::after { content: " *"; color: #d4351c; }`
  as the only mandatory-field signal → no `required` segment on any field and no
  text explaining the asterisk.
- ACCESSIBLE: `<label for="email">Email address</label><span id="emailHint">Enter
  it in the format name@example.com</span><input id="email"
  aria-describedby="emailHint">` → `before` "textbox, Email address, Enter it in
  the format name@example.com" → `after` keeps both around the entered value.
- ACCESSIBLE: `<label>Full name <span class="hint">Include any middle
  names</span><input id="fullname"></label>` → the wrapping label makes the
  instruction part of the accessible name, so it cannot be separated from it.
- ACCESSIBLE: `<fieldset aria-describedby="dobHint"><legend>Date of
  birth</legend><span id="dobHint">For example, 31 3 1980</span>…` →
  `sr_transcript` announces "group, Date of birth, For example, 31 3 1980"; the
  per-field phrases carry only "Day"/"Month"/"Year", which is expected here.
- ACCESSIBLE: `<label for="contact-name">Your name <span>(required)</span></label>
  <input id="contact-name" required>` → "textbox, Your name (required), required":
  stated in text and exposed as state.
