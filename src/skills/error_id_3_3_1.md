---
sc: "3.3.1"
technique: "error-identification"
title: "Input error not identified, or not described in text"
applies_when:
  element_tag: [form]
signals:
  - field: element_html
    look_for: "PRIMARY. The capture drove the form's own validation before snapshotting, so this is the POST-SUBMIT markup and any error state is already rendered here. Look for a detected error conveyed with NO text (a red border/class, a bare coloured bar, an empty error container, an icon or svg with no accessible name); error text that never says WHICH field or WHAT is wrong; or error text present but not tied to its field (no aria-describedby, not inside the label, not adjacent, no summary naming the field)"
  - field: parent_html
    look_for: "whether an error summary or message sits OUTSIDE the form (in the surrounding <main>) and identifies the fields in error — that still satisfies 3.3.1"
  - field: sr_transcript
    look_for: "CORROBORATION. Walked after the same submit, so an error described in text is read out here. A form whose transcript names the fields but voices no error text — while element_html shows an error state — confirms the error is not available in text"
---
## Violation criteria (3.3.1 Error Identification)
**3.3.1 Error Identification is Level A and is in scope for this element.**

An **input error** is information supplied by the user that is not accepted. The
criterion has two prongs, and BOTH must hold whenever an input error is
**automatically detected**:
1. the **item that is in error is identified**, and
2. the **error is described to the user in text**.

## Note on the capture
`element_html` is the form **after** the capture filled the invalid values and
clicked submit through the page's own handler, so the error state you see is the
real, rendered one. A form showing no error state at all was either not driven
(no interaction markers) or genuinely accepted the input — do not invent an error
that is not there.

Flag `inaccessible` under `3.3.1` when an error is clearly detected but:
- The error is conveyed by **colour, border, or styling alone** — a
  `class="has-error"` / red outline / a coloured bar with no text. A revealed but
  **empty** error container (`<div class="field-error"></div>` with no text node)
  is the same defect: there is nothing to describe the error.
- The error is conveyed by an **icon with no text alternative** — an `<svg>` with
  no `<title>`/`aria-label`, an `<img alt="">`, or a symbol glyph in an
  `aria-hidden` span.
- An **error summary or message exists but does not identify the item in error** —
  "There is a problem with your submission", "Please check your answers" — text
  that never names the field or says what is wrong. This fails prong 1 even
  though text is present.
- **Error text exists but is not associated with its field** — placed far from
  the input with no `aria-describedby`, not inside the field's `<label>`, not
  adjacent to it, and not named in a summary. The error is described, but the
  item in error is never identified.

## Pass criteria
Both prongs are met. The error is **described in text**, and that text
**identifies the field**, by any of:
- an inline text message wired to the input with `aria-describedby`;
- an error summary that names each field in error (typically linking to it),
  alongside or instead of inline messages;
- the error text placed inside the field's own `<label>`, making it part of the
  accessible name;
- text unambiguously adjacent to a single labelled field.

`aria-invalid="true"` and a red border are good redundant reinforcement and are
common in passing markup, but neither is required by 3.3.1 and neither is
sufficient on its own — the **text** is what the criterion asks for.

**3.3.1 does not require the error to be announced.** A live region
(`role="alert"` / `aria-live`) is **not** needed to pass this skill: whether a
message is announced without moving focus is WCAG 4.1.3's question, judged by a
separate skill. Do not flag `3.3.1` merely because an error message lacks
`role="alert"`. Equally, 3.3.1 says nothing about *how to fix* the error (that is
3.3.3 Error Suggestion) or about labels/instructions given up front (3.3.2) —
judge only identification and text description.

## Insufficient evidence
- **A form showing no error state at all.** 3.3.1 only applies *once an error is
  detected*, and this capture cannot prove a submission was attempted. A form
  that silently rejected bad input looks identical to one that was never
  submitted: both are just a form. Even a retained invalid-looking value plus an
  empty result container is circumstantial, not proof. Return
  `insufficient_evidence` and say that no error state was captured — do **not**
  infer a violation from silence, and do **not** call it accessible either.
  (A page that really does reject input silently *is* a 3.3.1 failure, but this
  evidence cannot establish it.)
- If the error text appears to be supplied by CSS `content:` or a background
  image, it will not be in the HTML or the transcript; say what was missing
  rather than guessing.

## Examples
- INACCESSIBLE: `<input id="zcode" class="form-control has-error"><div class="field-error"></div>`
  → the error container is revealed but empty; only a red border and a 2px bar
  convey the error. No text.
- INACCESSIBLE: `<div class="summary">There is a problem with your submission.</div>`
  → text, but it never identifies which field or what is wrong.
- INACCESSIBLE: `<svg class="error-icon" width="16" height="16">…</svg>` beside a
  field → an icon with no accessible name is not a text description.
- INACCESSIBLE: `<p class="footnote">Enter a date in the format DD/MM/YYYY.</p>`
  rendered at the foot of a three-field form with no `aria-describedby` → the
  error is described but the item in error is not identified.
- ACCESSIBLE: `<p class="error-message" id="emailError">Error: Enter an email address in the correct format, like name@example.com</p>`
  with `<input id="email" aria-invalid="true" aria-describedby="emailError">` →
  described in text and tied to the field.
- ACCESSIBLE: an error summary listing `<a href="#email">Enter an email address in the correct format</a>`
  plus inline messages per field → both prongs met.
- ACCESSIBLE: `<label for="username">Username <span id="usernameError">Error: Username must be at least 6 characters long</span></label>`
  → error text inside the label is part of the field's accessible name.
- INSUFFICIENT: `<form onsubmit="subscribe(event)">…<input id="email" value="sam-at-example"><button type="submit">Subscribe</button><p id="done"></p></form>`
  → the value looks invalid and nothing was rendered, but the capture cannot show
  whether the form was ever submitted, so no input error is established.
