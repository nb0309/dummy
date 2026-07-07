---
sc: "4.1.3"
technique: "status-messages"
title: "Status message not exposed as a live region"
applies_when:
  element_tag: [output, progress, div, p, span, section, aside, main, body, article, ul, ol]
signals:
  - field: element_html
    look_for: "a success/confirmation, error, progress/loading, or results-count message whose element has NO role=status|alert|log|progressbar|marquee|timer and NO aria-live; or a live region that IS present but suppressed via display:none / hidden / aria-hidden=true"
  - field: parent_html
    look_for: "whether an ancestor wrapper carries the live-region role/aria-live instead of the message element itself (that would satisfy 4.1.3); or a message injected into a container that is not itself a registered live region"
  - field: sr_transcript
    look_for: "the message read as a plain paragraph (no 'status'/'alert'/'log'/'progressbar' role announced), or skipped entirely — versus the region announced with its live-region role"
---
## Violation criteria (4.1.3 Status Messages)
This skill authorises you to evaluate **4.1.3 Status Messages** for this element
even though the base instructions frame the classifier around Level A — treat
4.1.3 as in scope here.

A **status message** is text that informs the user of the outcome of an action,
the waiting/progress state of a process, or the existence of an error, and that
appears **without moving keyboard focus** to itself. To be perceivable to a
screen-reader user it must be programmatically exposed as a **live region** —
via a role (`role="status"`, `role="alert"`, `role="log"`,
`role="progressbar"`, `role="marquee"`, `role="timer"`), an `aria-live`
attribute (`polite`/`assertive`), or a native live element (`<output>`,
`<progress>`).

Flag `inaccessible` under `4.1.3` when the element is (or contains) a status
message that is **not** exposed this way. Read the raw `element_html` /
`parent_html` directly:
- A **success / confirmation** banner ("Your application has been submitted",
  "Saved", "Copied") rendered as a plain `<div>`/`<p>`/`<span>` with **no**
  live-region role and **no** `aria-live` — the screen reader is never told it
  appeared.
- A **form validation / error** message ("There is a problem…", "Enter a valid
  email") that is not a focus target and carries no `role="alert"` /
  `aria-live` — it will not be announced when it is inserted.
- A **results / status count** ("5 results found", "3 items in your basket")
  that updates in place with no `aria-live`/`role="status"` on the element or an
  ancestor.
- A **progress / loading / busy** indicator ("Loading…", a spinner, "Uploading
  60%") with no `role="progressbar"` (and value attributes), `role="status"`, or
  `aria-live`.
- A live region that **exists but is suppressed**: `display:none`,
  `hidden`, or `aria-hidden="true"` on the region (or an ancestor) removes it
  from the accessibility tree, so the message — even with `role="status"` — is
  never announced. This is still a `4.1.3` violation.

When the message element itself lacks the role, check `parent_html`: an
**ancestor** wrapper carrying `aria-live`/`role="status"` around the message
**does** satisfy 4.1.3 (the message is inside a registered live region) — do not
flag that case.

## Pass criteria
- The status message (or an ancestor that wraps it) carries an appropriate
  live-region role or `aria-live`, is **not** hidden from assistive tech, and the
  `sr_transcript` announces it with that role (e.g. `status`, `alert`,
  `progressbar`).
- Choice of politeness is appropriate to urgency (errors → `alert`/`assertive`;
  routine confirmations/counts → `status`/`polite`), but the mere presence of a
  correct, non-suppressed live-region role/property is enough to pass this skill.

## Insufficient evidence
- If it cannot be determined from the capture whether the text is a genuine
  *status message* (dynamically presented feedback) rather than ordinary static
  body copy — e.g. no surrounding action/form context and no wording that
  signals success/error/progress/results — return `insufficient_evidence`
  rather than guessing.

## Examples
- INACCESSIBLE: `<div class="banner">Your application has been submitted</div>`
  → no role/`aria-live`; SR reads it as plain text, so a mid-page update is
  silent.
- INACCESSIBLE: `<p class="error-message">There is a problem: enter a valid
  email address</p>` → needs `role="alert"`.
- INACCESSIBLE: `<div role="status" style="display:none">Your changes have been
  saved</div>` → correct role but hidden, so never announced.
- ACCESSIBLE: `<div role="status">Your application has been submitted</div>` →
  SR announces "status, Your application has been submitted".
- ACCESSIBLE: `<div aria-live="polite">5 results found</div>` and
  `<div role="progressbar" aria-valuenow="60" …>60% complete</div>`.
