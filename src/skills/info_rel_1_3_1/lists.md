---
sc: "1.3.1"
technique: "list-structure"
title: "List semantics (ul/ol/li, dl/dt/dd)"
applies_when:
  element_tag: [ul, ol, li, dl, dt, dd, main, body, section, div, article]
  ax_role: [list, listitem, term, definition, main, text]
axe_ids: [list, listitem, dlitem, definition-list]
signals:
  - field: element_html_raw
    look_for: "list-looking content built from text + <br> instead of <ul>/<ol>; orphan <li>/<dt>/<dd>; wrongly nested lists"
  - field: ax_subtree
    look_for: "content that reads as a list visually but exposes no 'list'/'listitem' roles, or list/term/definition items with no valid list/dl parent"
  - field: sr_reading_order
    look_for: "items announced as plain text (e.g. '* apple') rather than 'listitem, level 1, position 1'"
---
## Violation criteria (1.3.1 for lists)
Flag `inaccessible` under `1.3.1` when list relationships are not encoded:
- **List not marked up as a list**: visually a list (bullets/asterisks, line
  breaks) but built from text and `<br>` — no `<ul>/<ol>/<li>`. `sr_reading_order`
  reads plain lines (`* apple`) with no `listitem` semantics.
- **Improperly nested lists**: a nested `<ul>/<ol>` placed directly inside a
  parent `<ul>/<ol>` (as a sibling of `<li>`) instead of inside an `<li>`.
- **Orphan `<li>`**: a list item with no `<ul>`/`<ol>` parent.
- **Orphan `<dt>`/`<dd>`**: definition-list items not contained in a `<dl>`
  (axe rule `dlitem`), so term/definition relationships are lost.

## Pass criteria
- Lists use `<ul>/<ol>` with `<li>` children (nested lists inside an `<li>`), or
  `<dl>` with `<dt>/<dd>` pairs; `ax_subtree` shows `list`/`listitem` (or
  `term`/`definition`) with correct nesting.

## Examples
- INACCESSIBLE: `<main>* apple <br>* orange <br>* banana</main>` (fake list).
- INACCESSIBLE: a `<dt>`/`<dd>` rendered outside any `<dl>` (orphan).
- ACCESSIBLE: `<ul><li>apple</li><li>orange</li></ul>` → `listitem, position 1 …`.
