---
sc: "1.3.1"
technique: "table-relationships"
title: "Data table structure and header relationships"
applies_when:
  element_tag: [table, main, body, section, div, article]
  ax_role: [table, grid, main]
axe_ids: [empty-table-header, td-has-header, th-has-data-cells, scope-attr-valid, table-fake-caption, td-headers-attr]
signals:
  - field: table_cell_structure
    look_for: "a <th> with NO-SCOPE whose text is a repeating data VALUE (not a column/row label) — the browser's inferred ax_subtree role for this cell cannot be trusted"
  - field: ax_subtree
    look_for: "data cells announced as 'cell' rather than 'columnheader'/'rowheader'; missing caption"
  - field: sr_cell_walk
    look_for: "matrix walk where row/column headers are NOT re-announced when moving between cells"
  - field: sr_headers_announced
    look_for: "rows read with no associated header context"
  - field: axe_wcag131_violations
    look_for: "axe-core table structure findings"
---
## Violation criteria (1.3.1 for data tables)
Flag `inaccessible` under `1.3.1` when a **data** table fails to encode its
row/column relationships programmatically:
- Table has data cells but **no `<th>`** header cells — every cell announces as
  `cell` in `ax_subtree`/`sr_cell_walk` (should be `columnheader`/`rowheader`).
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
  check `table_cell_structure` directly — do **not** rely on `ax_subtree` alone
  here. Browsers apply a best-effort header-inference algorithm that will
  confidently assign a `columnheader`/`rowheader` role to a `NO-SCOPE` `<th>`
  even when its text is actually a repeating data value, not a label. If
  `table_cell_structure` shows multiple leading `th[NO-SCOPE]` cells per data
  row whose text values change per row (e.g. street names, not column titles),
  that is markup authored as data mistakenly tagged `<th>` — flag it even if
  `ax_subtree` looks clean.

## Pass criteria
- Genuine data tables expose `<th>` with correct `scope`, an optional
  `<caption>`, consistent columns, and `ax_subtree` shows `columnheader` /
  `rowheader` roles; navigating cells re-announces the relevant headers.
- `<th>` cells with **no `scope`** are only acceptable when `table_cell_structure`
  confirms they are genuine single-level column headers (the first row) or are
  otherwise disambiguated via `headers`/`id` — not when they sit mid-table
  holding row-varying data.

## Examples
- INACCESSIBLE: `<table>` of names/ages using only `<td>` → `ax_subtree` shows
  every `cell "…"`, no `columnheader`.
- INACCESSIBLE: `<table>` wrapping a nav `<ul>` and a `<h2>`/`<p>` (layout table).
- INACCESSIBLE: header row `<th>Road</th><th>Junction</th>…`, then a data row
  `<th>Regent Street</th><th>Oxford Street</th><td>307</td>…` — `table_cell_structure`
  shows `th[NO-SCOPE]"Regent Street"` and `th[NO-SCOPE]"Oxford Street"` changing
  every row (real data, not labels), even though `ax_subtree` inferred
  `columnheader "Regent Street"` / `rowheader "Oxford Street"` for them.
- ACCESSIBLE: `<table><caption>…</caption>…<th scope="col">Name</th>…` →
  `ax_subtree` shows `columnheader "Name"`.
