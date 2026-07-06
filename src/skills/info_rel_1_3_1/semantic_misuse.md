---
sc: "1.3.1"
technique: "semantic-misuse"
title: "Misused or missing semantic structure"
applies_when:
  element_tag: [main, body, section, div, article, ol, ul, p, nav, span]
  ax_role: [main, text, region, article, list]
axe_ids: [aria-roles, aria-valid-attr-value, region, landmark-unique, empty-heading]
signals:
  - field: element_html_raw
    look_for: "invalid/nonsensical ARIA role names; <article> wrapping non-article content; empty <p>; content with no structural markup"
  - field: ax_role
    look_for: "role that does not match the content's meaning, or a generic/absent role where structure is expected"
  - field: ax_subtree
    look_for: "structure that misrepresents relationships (wrong landmark/role) or exposes no relationships at all"
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
  lists, or landmarks to convey the structure.

## Careful — do NOT over-flag
- An **empty `<p>`** or an empty inline element with no content is typically a
  harmless code nit, not a WCAG A failure. Only flag if the emptiness actually
  drops information a user needs. Prefer `accessible` (or note low confidence)
  for trivially-empty elements unless the surrounding context proves lost meaning.

## Pass criteria
- Roles are valid and match the content; structural relationships (sections,
  lists, landmarks) are expressed with correct semantic elements.

## Examples
- INACCESSIBLE: `<ol role="somethingInvalid">…` (invalid role name).
- INACCESSIBLE: `<article>` wrapping a generic nav `<ul>` of links.
- LIKELY ACCESSIBLE: `<main><p></p></main>` (empty paragraph — trivial).
