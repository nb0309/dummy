# Dataset generator

Scalable capture pipeline that turns GDS WCAG audit HTML fixtures into a
per-element labeled dataset. Headless **Chromium (Playwright)** +
**axe-core** + **@guidepup/virtual-screen-reader**. Output columns are identical
to `../dataset.csv`, so it plugs straight into the `src/` classifier.

## Run

```bash
cd generator
node capture.mjs                       # both default suites -> ../dataset_generated.{csv,jsonl}
node capture.mjs --no-sr               # fast: skip the screen reader (static features only)
node capture.mjs --dir "tests/wcag 1.1.1" --sc 1.1.1 --out images_only
```

Flags:
- `--dir <path>`  input suite folder, relative to the repo root; repeatable.
  Default: `tests/SC 1.3.1` and `tests/wcag 1.1.1`.
- `--sc <value|auto>`  success criterion. `auto` (default) infers it from the
  folder name (`SC 1.3.1` → `1.3.1`), then from the filename category.
- `--label <value>`  ground-truth label for every row (default `inaccessible`;
  these suites are all-inaccessible examples).
- `--out <base>`  output base name written to the repo root (default
  `dataset_generated`) → `<base>.csv` (+ BOM, Excel-safe) and `<base>.jsonl`.
- `--no-sr`  skip the virtual screen reader.

## How it scales across criteria

`lib/extract.js` is the one seam that decides which elements become samples. It
does a single document-order sweep over a candidate set covering:

| WCAG SC | elements captured |
|---|---|
| 1.1.1 | `img`, `svg`, `canvas`, `picture`, `input[type=image]`, `[role=img]` |
| 1.2.1 | `audio`, `video`, `object`, `embed`, `iframe` |
| 1.3.1 | `table`, `ul`/`ol`/`dl`, orphan `li`/`dt`/`dd`, fallback content block |

Media/images nested inside an interactive control escalate to that control
(e.g. an image-only link is captured as the `<a>`). Containers suppress their
leaf/media descendants but **not** nested tables/lists (those are legitimate
separate samples). To add a new criterion, extend the `SEL` map in
`lib/extract.js` and the `CATEGORY_SC` map in `lib/rows.js`.

## Modules

- `capture.mjs` — entry: suites → per-page capture → rows → CSV/JSONL.
- `lib/extract.js` — sample selection + raw HTML/parent/context capture.
- `lib/aria.js` — `ariaSnapshot()` → `ax_role`/`ax_name`/`ax_level`/`ax_subtree`.
- `lib/axe.js` — axe-core in-page, violations mapped to each sample.
- `lib/vsr.js` — drives the virtual screen reader (transcript + reading order).
- `lib/rows.js` — schema, SC/label resolution, CSV/JSONL writers.
- `lib/{server,csv,normalize}.js` — static server, CSV encoder, HTML cleaner.

Dependencies resolve from the shared `d2/node_modules` (Playwright, axe-core,
virtual-screen-reader already installed there); no local install needed.
