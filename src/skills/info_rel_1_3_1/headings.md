---
sc: "1.3.1"
technique: "heading-structure"
title: "Heading semantics and hierarchy"
applies_when:
  element_tag: [main, body, section, div, article, h1, h2, h3, h4, h5, h6, p, span, b, strong]
signals:
  - field: parent_html
    look_for: "heading levels that skip downwards (e.g. h1 then h3) or are out of logical order"
  - field: element_html
    look_for: "visually-styled 'heading' text using <b>/<strong>/<p>/font-size instead of <h1>-<h6>; an empty heading element"
  - field: sr_transcript
    look_for: "announced heading levels and their order (e.g. 'heading, …, level 1' then 'level 3')"
---
## Violation criteria (1.3.1 for headings)
Flag `inaccessible` under `1.3.1` when visual heading structure is not conveyed
semantically:
- **Skipped levels**: heading levels jump downward out of order (e.g. `<h1>` →
  `<h3>`, or `<h2>` → `<h5>`). Check `parent_html`/`sr_transcript` for the full
  sequence, not just the captured element in isolation.
- **Text formatting used as a heading**: text that is visually a heading but
  marked up with `<b>`, `<strong>`, `<p>`, or CSS font-size instead of an
  `<h1>`–`<h6>`, so no `heading` role is announced in `sr_transcript`.
- An **empty heading** element conveying no text.

## Pass criteria
- Headings use `<h1>`–`<h6>` in a logical, non-skipping order; `sr_transcript`
  shows correctly-levelled `heading` announcements.

## Examples
- INACCESSIBLE: parent shows `<h1>…</h1>` then `<main><h3>Heading 3</h3>` (skips h2).
- INACCESSIBLE: `<p style="font-size:2em"><b>Section title</b></p>` acting as a heading.
