---
sc: "1.3.1"
technique: "form-control-grouping"
title: "Related form controls grouped with fieldset/legend"
applies_when:
  element_tag: [form, fieldset, main, body, section, div, article, input, legend]
signals:
  - field: parent_html
    look_for: "a group of related radio buttons or checkboxes addressing one prompt, NOT wrapped in <fieldset>/<legend>"
  - field: element_html
    look_for: "loose <h3>/<h4>/<p> used as a group prompt above detached inputs; a <fieldset> with a missing or empty <legend>"
  - field: sr_transcript
    look_for: "checkbox/radio inputs announced with no enclosing group and no group label"
---
## Violation criteria (1.3.1 for form groups)
Flag `inaccessible` under `1.3.1` when a set of related controls that answer a
single prompt is not programmatically grouped:
- A **group of radio buttons or checkboxes** for one question is **not enclosed
  in a `<fieldset>`** with a prompt-defining `<legend>`; instead the prompt is a
  loose `<h3>/<h4>/<p>` above detached inputs.
- A `<fieldset>` **without a `<legend>`**, or with an **empty `<legend>`**, so the
  group has no accessible name.

Look at `parent_html`, not just the single input — the grouping defect lives at
the container level. If the parent shows several sibling checkboxes/radios under
one heading with no `<fieldset>`, flag the row.

## Note on the capture
Interactive checkboxes/radios may be announced generically; rely on the DOM
structure (`element_html`/`parent_html`), not on the literal word the transcript
uses for the control.

## Pass criteria
- Related radios/checkboxes are wrapped in `<fieldset><legend>…</legend>…` (visible
  in `element_html`/`parent_html`) and `sr_transcript` announces a group with an
  accessible name.

## Examples
- INACCESSIBLE: `<h4>Which waste do you transport?</h4>` followed by loose
  `<input type="checkbox">` items (no fieldset).
- INACCESSIBLE: `<fieldset><legend></legend>…` (empty legend).
