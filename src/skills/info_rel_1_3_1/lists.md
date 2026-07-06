---
sc: "1.3.1"
technique: "list-structure"
title: "List semantics (ul/ol/li, dl/dt/dd)"
applies_when:
  element_tag: [ul, ol, li, dl, dt, dd, main, body, section, div, article]
signals:
  - field: element_html
    look_for: "list-looking content built from text + <br> instead of <ul>/<ol>; orphan <li>/<dt>/<dd>; a nested <ul>/<ol> placed directly inside a parent list instead of inside an <li>"
  - field: parent_html
    look_for: "an <li>/<dt>/<dd> whose parent is NOT a <ul>/<ol>/<dl> (orphan), or a nested list mis-parented as a sibling of <li>"
  - field: sr_transcript
    look_for: "items announced as plain text (e.g. '* apple') rather than 'listitem, level 1, position 1'"
---
## Violation criteria (1.3.1 for lists)
Flag `inaccessible` under `1.3.1` when list relationships are not encoded:
- **List not marked up as a list**: visually a list (bullets/asterisks, line
  breaks) but built from text and `<br>` — no `<ul>/<ol>/<li>`. `sr_transcript`
  reads plain lines (`* apple`) with no `listitem` semantics.
- **Improperly nested lists**: a nested `<ul>/<ol>` placed directly inside a
  parent `<ul>/<ol>` (as a sibling of `<li>`) instead of inside an `<li>`.
- **Orphan `<li>`**: a list item with no `<ul>`/`<ol>` parent.
- **Orphan `<dt>`/`<dd>`**: definition-list items not contained in a `<dl>`
  (axe rule `dlitem`), so term/definition relationships are lost.

## Pass criteria
- Lists use `<ul>/<ol>` with `<li>` children (nested lists inside an `<li>`), or
  `<dl>` with `<dt>/<dd>` pairs; `sr_transcript` announces `list`/`listitem` (or
  `term`/`definition`) with correct nesting.

## Examples
- INACCESSIBLE: `<main>* apple <br>* orange <br>* banana</main>` (fake list).
- INACCESSIBLE: a `<dt>`/`<dd>` rendered outside any `<dl>` (orphan).
- ACCESSIBLE: `<ul><li>apple</li><li>orange</li></ul>` → `listitem, position 1 …`.
