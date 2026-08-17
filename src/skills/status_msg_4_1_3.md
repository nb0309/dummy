---
sc: "4.1.3"
technique: "status-messages"
title: "Status message not exposed as a live region"
applies_when:
  element_tag: [output, progress, div, p, span, section, aside, main, body, article]
  requires_column: [sr_status_announcement]
signals:
  - field: sr_status_announcement
    look_for: "PRIMARY. The interaction probe triggered the status update (clicking the page's own control where the fixture has one) and recorded what the reader said. SILENT (no announcement) => the update is not conveyed without focus => 4.1.3 violation. A 'polite: <text>' / 'assertive: <text>' announcement of the message => it IS a working live region => pass. Only exception: a value-driven role=progressbar can read silent under this probe — corroborate with element_html there."
  - field: element_html
    look_for: "CORROBORATION. A success/confirmation, error, progress/loading, or results-count message whose element has NO role=status|alert|log|progressbar|marquee|timer and NO aria-live (or aria-live=off); or a live region present but suppressed via display:none / hidden / aria-hidden=true"
  - field: parent_html
    look_for: "whether an ancestor wrapper carries the live-region role/aria-live instead of the message element itself (that would satisfy 4.1.3); or a message injected into a container that is not itself a registered live region"
  - field: sr_transcript
    look_for: "SECONDARY only. This is the STATIC walk and does NOT fire a live-region announcement, so silence here is expected — do not treat it as proof; use sr_status_announcement for the dynamic behaviour"
---
## Violation criteria (4.1.3 Status Messages)
**4.1.3 Status Messages is Level AA and is in scope for this element.**

A **status message** is text that informs the user of the outcome of an action,
the waiting/progress state of a process, or the existence of an error, and that
appears **without moving keyboard focus** to itself. To be perceivable to a
screen-reader user it must be programmatically exposed as a **live region** —
via a role (`role="status"`, `role="alert"`, `role="log"`,
`role="progressbar"`, `role="marquee"`, `role="timer"`), an `aria-live`
attribute (`polite`/`assertive`), or a native live element (`<output>`,
`<progress>`).

**Lead with the interaction probe (`sr_status_announcement`).** The capture
started the screen reader, drove the status update through the page's own code
path (clicking the control that produces the message), and recorded what was
announced. Because the update happens after load, this measures the thing 4.1.3
is actually about: a message that is *added or changed* is announced only if it
lands in a live region that was already registered:
- **SILENT** (empty / "the region was updated but the reader announced NOTHING")
  ⇒ the status change is not conveyed to assistive tech without moving focus ⇒
  flag `inaccessible` under `4.1.3`. This holds even when `element_html` *looks*
  like it has a live region but it is suppressed (`display:none` /
  `aria-hidden`), because the probe proves it was not announced.
- **ANNOUNCED** as `polite: <text>` / `assertive: <text>` carrying the message ⇒
  it IS a working live region ⇒ `accessible` for this skill.
- The one exception: a value-driven `role="progressbar"` may read SILENT under
  this probe even though it is a valid mechanism (`progressbar` is not itself a
  live region, so an `aria-valuenow` change raises no announcement) — there,
  defer to `element_html` markup rather than the probe.

Then corroborate with the raw `element_html` / `parent_html` — a status message
is **not** exposed when:
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
- `sr_status_announcement` shows the message announced (`polite: …` /
  `assertive: …`) — the region behaves as a live region and is not suppressed.
- Or (probe silent for a value-driven `role="progressbar"` only) the
  `element_html` carries a correct, non-suppressed `role="progressbar"` with value
  attributes.
- Choice of politeness is appropriate to urgency (errors → `alert`/`assertive`;
  routine confirmations/counts → `status`/`polite`), but a correct, non-suppressed
  live-region mechanism that actually announces is enough to pass this skill.

## Insufficient evidence
- If it cannot be determined from the capture whether the text is a genuine
  *status message* (dynamically presented feedback) rather than ordinary static
  body copy — e.g. no surrounding action/form context and no wording that
  signals success/error/progress/results — return `insufficient_evidence`
  rather than guessing.

## Examples
- INACCESSIBLE: `<div class="banner">Your application has been submitted</div>`
  → no role/`aria-live`; probe `sr_status_announcement` is SILENT.
- INACCESSIBLE: `<p class="error-message">There is a problem: enter a valid
  email address</p>` → needs `role="alert"`; probe SILENT.
- INACCESSIBLE: `<div role="status" style="display:none">Your changes have been
  saved</div>` → correct role but hidden, so the probe is SILENT (never
  announced) even though the markup looks right.
- ACCESSIBLE: `<div role="status">Your application has been submitted</div>` →
  probe announces `polite: Your application has been submitted`.
- ACCESSIBLE: `<div aria-live="polite">5 results found</div>` → probe announces
  `polite: 5 results found`. `<div role="progressbar" aria-valuenow="60" …>` may
  read SILENT under the probe → pass on the markup instead.
