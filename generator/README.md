# Dataset generator

Scalable capture pipeline that turns GDS WCAG audit HTML fixtures into a
per-element labeled dataset. Headless **Chromium (Playwright)** +
**axe-core** + **@guidepup/virtual-screen-reader**. Output columns are identical
to `../dataset.csv`, so it plugs straight into the `src/` classifier.

## Run

```bash
cd generator
node capture.mjs                       # default (inaccessible) suites -> ../dataset_generated.{csv,jsonl}
node capture.mjs --no-sr               # fast: skip the screen reader (static features only)
node capture.mjs --dir "tests/wcag 1.1.1" --out images_only

# 4.1.3 has both defect and pass fixtures; capture each with its label:
node capture.mjs --dir "tests/wcag 4.1.3/fail" --label inaccessible --out ds_413_bad
node capture.mjs --dir "tests/wcag 4.1.3/pass" --label accessible   --out ds_413_good

# 3.3.1 additionally needs --sc to switch on the form sweep:
node capture.mjs --sc 3.3.1 --dir "tests/wcag 3.3.1/fail" --label inaccessible --out ds_331_bad
node capture.mjs --sc 3.3.1 --dir "tests/wcag 3.3.1/pass" --label accessible   --out ds_331_good
```

`--label` applies to the **whole run**, not per `--dir`, which is why pass and
defect fixtures are captured separately and merged afterwards (into
`../4.1.3_dataset.csv`, `../3.3.1_dataset.csv`). The `--dir` walk is flat: point
it at `…/fail` and `…/pass` individually, not at their parent.

## 4.1.3 fixture markers

Status-message fixtures carry two markers, both stripped by `lib/normalize.js` so
they can never reach a feature column:

- `data-status-target` — the region the probe watches. **Required**, and it must
  be in the DOM at load: `aria-live` only announces a change to a region that was
  already registered. Leave it **empty** — 4.1.3 is about a message *added or
  changed* after load, so a pre-rendered message is not a status message at all
  (a screen reader just reads it as ordinary body copy on the way past).
- `data-status-trigger` — the control the probe clicks to make the page write the
  status through its own code path. Optional: fixtures without one (the static
  `tests/wcag 4.1.3` suite) fall back to the probe replaying the region's existing
  text as a synthetic mutation, which is why *those* fixtures do pre-render it.

Two known limits of the underlying virtual reader:
- `role="progressbar"` is not a live region, so a value change raises no
  announcement and the probe reads SILENT on a valid progressbar. The 4.1.3 skill
  falls back to markup for that one case.
- Its live-region path does not prune hidden subtrees, so it would announce from
  inside `display:none`. `statusAnnouncementProbe()` corrects this by discarding
  announcements when the region is hidden from the a11y tree after the update.

## 3.3.1 fixture markers

Error-identification fixtures carry two markers, both stripped by
`lib/normalize.js`. Stripping matters more here than for 4.1.3: the DOM is
snapshotted *after* the click, so these markers sit inside the captured form, and
`data-error-fill`'s value would otherwise leak the provoking input into a feature
column.

- `data-error-trigger` — the control `lib/interact.js` clicks (the submit
  button). **Its presence is what opts a page into the interaction pass**, so a
  page without one is never touched.
- `data-error-fill="<value>"` — seed a control with a value that fails the page's
  own validation. Optional, repeatable. `interact.js` mirrors the value to the
  `value` **attribute** as well as the property, because assigning `.value` alone
  does not show up in `outerHTML` — the evidence would show an empty field beside
  an error message.

Unlike 4.1.3, 3.3.1 needs no live region and no extra column: it is judged from
`element_html` / `parent_html` / `sr_transcript`, so `src/skills/error_id_3_3_1.md`
is a pure drop-in with no Python change.

Flags:
- `--dir <path>`  input suite folder, relative to the repo root; repeatable.
  Default: `tests/SC 1.3.1`, `tests/wcag 1.1.1`, `tests/wcag 4.1.3/fail`.
- `--sc <value>`  opt into a criterion's extra sample sweep. Only `3.3.1` does
  anything today (it adds `form` to the candidate set); unset for every other
  suite. There is no inference from folder or file names.
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
| 4.1.3 | `[role=status/alert/log/progressbar/marquee/timer]`, `[aria-live]`, `output`, `progress` — plus status messages authored with **no** live-region markup, which fall through to the fallback content block |
| 3.3.1 | `form` — **only under `--sc 3.3.1`**. The whole form is the sample, because the SC needs the field, its label and the error text judged together; a bare error `<p>` in isolation cannot show whether the item in error is identified. The form suppresses everything inside it, so an error summary carrying `role="alert"` does not also surface as a second, evidence-poor row. |

Media/images nested inside an interactive control escalate to that control
(e.g. an image-only link is captured as the `<a>`). Containers suppress their
leaf/media descendants but **not** nested tables/lists (those are legitimate
separate samples).

To add a new criterion, extend the `SEL` map in `lib/extract.js` and add a skill
under `../src/skills/` (auto-discovered — no registry to edit). Keep the new
selector **opt-in behind `--sc`** unless it genuinely cannot collide: adding it
to the default `CANDIDATES` steals the fallback content block from every page it
matches, and for 4.1.3 the *absence* of that block is the defect signal.

## Modules

- `capture.mjs` — entry: suites → per-page capture → rows → CSV/JSONL.
- `lib/extract.js` — sample selection + raw HTML/parent/context capture.
- `lib/interact.js` — 3.3.1: fills + submits the form before extraction so the
  error state exists in the snapshot. No-op without `data-error-trigger`.
- `lib/aria.js` — `ariaSnapshot()` → `ax_role`/`ax_name`/`ax_level`/`ax_subtree`.
- `lib/axe.js` — axe-core in-page, violations mapped to each sample.
- `lib/vsr.js` — drives the virtual screen reader (transcript + reading order).
- `lib/rows.js` — schema, SC/label resolution, CSV/JSONL writers.
- `lib/{server,csv,normalize}.js` — static server, CSV encoder, HTML cleaner.

Dependencies resolve from the shared `d2/node_modules` (Playwright, axe-core,
virtual-screen-reader already installed there); no local install needed.
