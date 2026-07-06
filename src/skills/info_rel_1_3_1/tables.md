---
sc: "1.3.1"
technique: "table-relationships"
title: "Data table structure and header relationships"
applies_when:
  element_tag: [table, main, body, section, div, article]
signals:
  - field: element_html
    look_for: "the raw table markup: data cells with no <th> at all; <th> cells missing a valid scope (or headers/id); an empty <th>; a <caption> missing; a <table> nested inside another <table> or inside a <th>; rows with an inconsistent number of cells; a <th> holding a repeating data VALUE (not a column/row label)"
  - field: sr_transcript
    look_for: "the cell-by-cell walk: data cells announced as 'cell' rather than 'columnheader'/'rowheader'; row/column headers NOT re-announced when moving between cells; rows read with no associated header context"
  - field: parent_html
    look_for: "a layout table imposing table semantics on non-tabular surrounding content"
---
## Violation criteria (1.3.1 for data tables)
Flag `inaccessible` under `1.3.1` when a **data** table fails to encode its
row/column relationships programmatically. Read the raw markup in `element_html`
and confirm against the `sr_transcript` cell walk:
- Table has data cells but **no `<th>`** header cells — every cell announces as
  `cell` in `sr_transcript` (should be `columnheader`/`rowheader`).
- Header cells lack a valid `scope` (or `headers`/`id`) so headers are not
  associated with their data cells; navigating rows does not re-announce headers.
- An **empty `<th>`** (empty table header) that leaves a row/column unlabelled.
- A table used purely for **layout** (e.g. nav links beside body copy) that
  imposes table semantics (rows/cells announced) on non-tabular content.
- Missing `<caption>` where the table needs an accessible name to be understood.
- A table **nested inside another table** (or inside a `<th>`) producing a
  confusing, ambiguous reading structure.
- Rows with an **inconsistent number of columns**, or scattered **empty cells**,
  that break the row/column mapping.
- **Data values mis-marked as `<th>` with no `scope`** (a "double header" row):
  inspect the raw `element_html` directly. If multiple leading `<th>` cells per
  data row carry no `scope` and their text values **change per row** (e.g. street
  names, not column titles), that is markup authored as data mistakenly tagged
  `<th>` — flag it even if the `sr_transcript` happens to announce them as
  headers (the browser applies a best-effort header-inference guess that the raw
  markup does not justify).

## Pass criteria
- Genuine data tables expose `<th>` with correct `scope`, an optional
  `<caption>`, consistent columns, and the `sr_transcript` announces
  `columnheader` / `rowheader`; navigating cells re-announces the relevant
  headers.
- `<th>` cells with **no `scope`** are only acceptable when the raw markup
  confirms they are genuine single-level column headers (the first row) or are
  otherwise disambiguated via `headers`/`id` — not when they sit mid-table
  holding row-varying data.

## Examples
- INACCESSIBLE: `<table>` of names/ages using only `<td>` → `sr_transcript` reads
  every `cell "…"`, no `columnheader`.
- INACCESSIBLE: `<table>` wrapping a nav `<ul>` and a `<h2>`/`<p>` (layout table).
- INACCESSIBLE: header row `<th>Road</th><th>Junction</th>…`, then a data row
  `<th>Regent Street</th><th>Oxford Street</th><td>307</td>…` — the raw
  `element_html` shows `<th>` with no `scope` on "Regent Street"/"Oxford Street"
  whose values change every row (real data, not labels).
- ACCESSIBLE: `<table><caption>…</caption>…<th scope="col">Name</th>…` →
  `sr_transcript` announces `columnheader "Name"`.
