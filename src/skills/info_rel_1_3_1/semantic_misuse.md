---
sc: "1.3.1"
technique: "semantic-misuse"
title: "Misused or missing semantic structure"
applies_when:
  element_tag: [main, body, section, div, article, ol, ul, p, nav, span]
signals:
  - field: element_html
    look_for: "invalid/nonsensical ARIA role names; a role that does not match the content's meaning; <article> wrapping non-article content; empty <p>; content with no structural markup"
  - field: parent_html
    look_for: "surrounding structure that misrepresents relationships (wrong landmark/role) or exposes no relationships at all"
  - field: sr_transcript
    look_for: "a role/landmark announced that contradicts the content, or an undifferentiated blob announced with no structural relationships"
---
## Violation criteria (1.3.1 for semantic misuse)
Flag `inaccessible` under `1.3.1` when markup conveys structure/relationships that
do not match the content, or omits needed structure:
- **Invalid ARIA role names** (e.g. `role="group"` misspelled, or a made-up role)
  so the exposed role is wrong or dropped (axe `aria-roles`).
- **`<article>` used for non-article content** (e.g. a plain nav list), imposing
  an "article" relationship that misrepresents the content.
- **Content with no structural markup** — visually distinct sections/relationships
  presented as an undifferentiated blob (`unorganised content`) with no headings,
  lists, or landmarks to convey the structure. Read the counts in **STRUCTURE
  OBSERVATIONS**, which reports blocks of prose against headings, lists and
  landmarks. **Four or more blocks of prose organised by one heading or none, with
  no list and no sectioning element, is the threshold for this bullet** — at that
  length a reader has no way to move around the content or to know where one
  topic ends and the next begins. Say so under `1.3.1` and cite the counts.

## Careful — do NOT over-flag
- An **empty `<p>`** or an empty inline element with no content is typically a
  harmless code nit, not a WCAG A failure. Only flag if the emptiness actually
  drops information a user needs. Prefer `accessible` (or note low confidence)
  for trivially-empty elements unless the surrounding context proves lost meaning.
- This caution is about **empty elements only**. It does not soften the
  unorganised-content bullet above: a page of prose that meets the threshold there
  is a finding, not a nit.

## Pass criteria
- Roles are valid and match the content; structural relationships (sections,
  lists, landmarks) are expressed with correct semantic elements.

## Examples
- INACCESSIBLE: `<ol role="somethingInvalid">…` (invalid role name).
- INACCESSIBLE: `<article>` wrapping a generic nav `<ul>` of links.
- LIKELY ACCESSIBLE: `<main><p></p></main>` (empty paragraph — trivial).
