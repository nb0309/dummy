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

# 4.1.2 also has both defect and pass fixtures, captured the same way as 4.1.3:
node capture.mjs --dir "tests/wcag 4.1.2/fail" --label inaccessible --out ds_412_bad
node capture.mjs --dir "tests/wcag 4.1.2/pass" --label accessible   --out ds_412_good

# 3.3.2 reuses 3.3.1's form sweep, and adds the labels/instructions probe:
node capture.mjs --sc 3.3.2 --dir "tests/wcag 3.3.2/fail" --label inaccessible --out ds_332_bad
node capture.mjs --sc 3.3.2 --dir "tests/wcag 3.3.2/pass" --label accessible   --out ds_332_good

# 2.4.3 is page-level: one row per file, plus the focus-order Tab sweep:
node capture.mjs --sc 2.4.3 --dir "tests/wcag 2.4.3/fail" --label inaccessible --out ds_243_bad
node capture.mjs --sc 2.4.3 --dir "tests/wcag 2.4.3/pass" --label accessible   --out ds_243_good

# 2.4.4, page-level, with the link-purpose/context probe:
node capture.mjs --sc 2.4.4 --dir "tests/wcag 2.4.4/fail" --label inaccessible --out ds_244_bad
node capture.mjs --sc 2.4.4 --dir "tests/wcag 2.4.4/pass" --label accessible   --out ds_244_good

# 2.4.6 is page-level too, with the headings/labels rotor view:
node capture.mjs --sc 2.4.6 --dir "tests/wcag 2.4.6/fail" --label inaccessible --out ds_246_bad
node capture.mjs --sc 2.4.6 --dir "tests/wcag 2.4.6/pass" --label accessible   --out ds_246_good

# 1.3.2, also page-level, with the reading-order walk:
node capture.mjs --sc 1.3.2 --dir "tests/wcag 1.3.2/fail" --label inaccessible --out ds_132_bad
node capture.mjs --sc 1.3.2 --dir "tests/wcag 1.3.2/pass" --label accessible   --out ds_132_good

# 2.1.2, page-level, with the keyboard-trap escape ladder:
node capture.mjs --sc 2.1.2 --dir "tests/wcag 2.1.2/fail" --label inaccessible --out ds_212_bad
node capture.mjs --sc 2.1.2 --dir "tests/wcag 2.1.2/pass" --label accessible   --out ds_212_good

# 3.2.1, page-level, with the on-focus context probe:
node capture.mjs --sc 3.2.1 --dir "tests/wcag 3.2.1/fail" --label inaccessible --out ds_321_bad
node capture.mjs --sc 3.2.1 --dir "tests/wcag 3.2.1/pass" --label accessible   --out ds_321_good

# 3.2.2, page-level, with the on-input context probe:
node capture.mjs --sc 3.2.2 --dir "tests/wcag 3.2.2/fail" --label inaccessible --out ds_322_bad
node capture.mjs --sc 3.2.2 --dir "tests/wcag 3.2.2/pass" --label accessible   --out ds_322_good

# 1.3.3, page-level, with the sensory-characteristics scan:
node capture.mjs --sc 1.3.3 --dir "tests/wcag 1.3.3/fail" --label inaccessible --out ds_133_bad
node capture.mjs --sc 1.3.3 --dir "tests/wcag 1.3.3/pass" --label accessible   --out ds_133_good
```

`--label` applies to the **whole run**, not per `--dir`, which is why pass and
defect fixtures are captured separately and merged afterwards (into
`../4.1.3_dataset.csv`, `../3.3.1_dataset.csv`, `../3.3.2_dataset.csv`,
`../2.4.3_dataset.csv`, `../2.4.4_dataset.csv`, `../2.4.6_dataset.csv`,
`../1.3.2_dataset.csv`). The `--dir`
walk is flat: point it at `…/fail` and `…/pass` individually, not at their parent.

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

## 4.1.2 fixture markers

Name/role/value fixtures need no marker to be captured — `lib/extract.js`'s
`control` selector (`[role=checkbox/switch/radio/slider/combobox/listbox/
option/tab/menuitemcheckbox/menuitemradio/spinbutton]`, `input[type=checkbox/
radio/range]`, `select`, `[aria-pressed]`, `[aria-expanded][aria-controls]`)
picks them up directly, since a real role/type is required either way. One
optional marker, stripped by `lib/normalize.js`:

- `data-role-trigger` — the descendant to click when the sample element itself
  isn't the right click target. Optional: fixtures without one have the probe
  click the sample element directly (true for every fixture in
  `tests/wcag 4.1.2` today).

`lib/vsr.js`'s `roleStateValueProbe()` reads the element's spoken phrase +
outerHTML, clicks it, then reads both again — the `sr_role_state_value` column
holds `{before, after}`. A control whose `phrase` is identical before/after
while `html` differs means the click changed something visible without ever
reaching the accessibility tree — the core 4.1.2 defect this probe exists to
catch. One known limit: value-widgets like `role="slider"` are typically
keyboard- not click-driven, so the probe may show no change on a *valid*
slider — the skill falls back to markup (`aria-valuenow`/min/max) for that
case, the same way 4.1.3 falls back to markup for `role="progressbar"`.

## 3.3.2 fixture markers

**None.** Labels/instructions fixtures need no marker at all: the sample is the
whole `<form>` (the same `SEL.form` sweep 3.3.1 uses, now opened to `--sc 3.3.2`),
and `lib/vsr.js`'s `labelInstructionProbe()` finds its own fields with
`input:not([type=hidden|submit|button|reset|image]), select, textarea`.

For each field the probe reads the announced phrase, enters a type-appropriate
value, and reads again — `sr_label_instruction` holds one
`{field, before, after}` entry per field, each side `{phrase, html}`.

The decisive comparison is **segment loss, not inequality**. The phrase always
differs across the probe because the entered value becomes one of the announced
segments; what matters is whether a segment the reader used to say has *gone*:

```text
placeholder-only : "textbox, placeholder Email address"
                -> "textbox, someone@example.com"                 name LOST  => fail
label + hint     : "textbox, Email address, <hint>"
                -> "textbox, Email address, <value>, <hint>"       both kept  => pass
```

Three things the reader hands us for free, all confirmed against the fixtures:
- a name sourced from the `placeholder` attribute is announced with a literal
  `"placeholder "` prefix, and does **not** survive input — so the probe catches
  placeholder-as-label outright;
- native `required` is announced as a trailing `required` segment, which is the
  only positive proof a mandatory field exposes that state;
- `label[for=…]` **does** resolve with the read scoped to the field alone (name
  computation is document-wide), so the probe scopes there. Scoping to the
  field's wrapper instead announces the `<label>` element, not the input.

One known limit: the probe reads each field in **isolation**, so a
`<fieldset>`/`<legend>` and any hint attached to the *group* never appear in a
field's phrase — those show up only in the static `sr_transcript`, as
`group, <legend>, <hint>`. The skill is told to check there before concluding an
instruction is missing, the same way 4.1.3 falls back to markup for
`role="progressbar"`.

`html` is the field's **wrapper** (its parent, unless that is the form or body),
not the field alone — a label or hint lives beside the field, so a hint removed
on input is only visible one level up.

## 2.4.3 fixture markers

**None.** The probe drives the keyboard itself. 2.4.3 is the one **page-level**
criterion here: the finding lives in the *sequence* of focusable components across
the whole page, so under `--sc 2.4.3` `lib/extract.js` takes an early branch and
emits exactly one sample — `document.body` — skipping the candidate sweep entirely.

`<body>` deliberately, not `<main>`: the elements that matter most to focus order
(skip links, banner nav, footers) usually sit *outside* main, so capturing main
would omit the very evidence the criterion is judged on. It also makes
`parent_html` the `<html>` element, which carries the `<head>` stylesheet — so CSS
that reorders the page visually is visible alongside the DOM order it fights with.

`lib/vsr.js`'s `focusOrderProbe()` is the **only probe that is not a single
`page.evaluate`**. Native focus traversal happens only for trusted key events, so
`Virtual.press("Tab")` — which dispatches a synthetic event at the reader's own
cursor — does not move DOM focus at all. Playwright's keyboard does. So the probe
is a hybrid: Playwright presses Tab, and a small `page.evaluate` reads each stop.

`sr_focus_order` holds `{stops, complete, truncated, stalled}`. Per stop: the
announced `phrase`, `tag`/`role`/`name`, `tabindex`, `domIndex` (source order),
document-relative `rect`, `obscured`, and `controls`/`controlsRange`.

Three details that are easy to get silently wrong:

- **Geometry must be document-relative** (`rect.top + scrollY`). Tabbing scrolls the
  page, so raw `getBoundingClientRect()` values would encode scroll position rather
  than layout — corrupting exactly the signal the skill is meant to judge.
- **Termination**: after the last control the browser moves focus out of the
  document and `activeElement` falls back to `<body>`, after which the cycle
  restarts. `<body>` is therefore the end of the sweep. A stop that repeats the
  previous element instead means focus is not advancing — recorded as `stalled`, and
  attributed to 2.1.2, not 2.4.3.
- **`controlsRange`** is the controlled element's subtree as a `[first, last]`
  `domIndex` pair. `querySelectorAll("*")` is document order and a subtree is
  contiguous within it, so the range is exact — which makes "did focus actually go
  into the content this control revealed?" a mechanical check.

### What the sweep can and cannot settle

Measured against the ten fixtures, four signals are near-mechanical: tab-vs-visual
order, tab-vs-source order, positive `tabindex`, and `obscured` stops. Those catch
four of the five defect fixtures.

They do **not** catch everything, and the skill says so explicitly. A disclosure
whose revealed panel is appended at the end of the document has tab order matching
visual *and* source order perfectly — the defect is that the panel *belongs to* a
button several stops earlier. `controlsRange` mechanises that one case; the general
problem does not reduce to a measurement. Whether an order preserves **meaning** is
the judgement being handed to the model, so `src/evidence.py` renders these as
*observations* and states plainly that a clean result is not a pass.

## 2.4.6 fixture markers

**None**, and no interaction either — `headingLabelProbe()` is a plain read. Like
2.4.3 it is page-level (`<body>`, one row per file, via the same `PAGE_SC` branch in
`lib/extract.js`).

It reproduces the **rotor view**: every heading, form control, button and link with
what the reader *announces* for it, pulled **out of document order**. That framing is
the whole point. AT users do not only read top to bottom — they pull up a headings
menu or a form-controls list and read the entries stripped of the page around them.
A heading that reads fine in flow can be useless there: three sections all headed
"Overview", or a field labelled "Number" that only made sense because of a heading
above it. `sr_transcript` (reading order) hides this; the list exposes it.

`sr_headings_labels` holds `{headings, labels, links}`:

- `headings` — `{level, phrase, text, introduces}`. **`introduces`** is the content
  from that heading to the next heading of the same or higher rank, collapsed and
  truncated to 200 chars. This is what makes "does the heading describe its
  section?" answerable at all, and it is the only way to catch a heading that is
  specific, unique **and wrong** — `"Payment details"` introducing
  `"Street address Town or city Postcode"`. For an `<h1>` the section is the whole
  page, which is correct: an h1 does introduce everything under it.
- `labels` — the **controls** (`input` less hidden/submit/button/reset/image,
  `select`, `textarea`, `button`), not `<label>` elements: a control may be named by
  `aria-label` with no `<label>` at all, and it is the announced *name* 2.4.6 judges.
  Each carries `underHeading`, the visual context the rotor strips.
- `links` — `{phrase, text, href, underHeading}`. Listed for background only; see
  "Links are not judged here" below.

### What the rotor view can and cannot settle

Two signals are objective, and `src/evidence.py` computes them: duplicate headings
and duplicate control labels. Measured against the ten fixtures they catch two of
the five defect fixtures.

The rest is the criterion itself and is deliberately **not** mechanised: whether a
heading is *generic* ("Section 1", "More information") and whether it is *accurate*
about its section. A keyword blocklist would only fake that judgement, so the
evidence renders the objective findings as **observations** and states plainly that
a clean result is not a pass.

### Links are not judged here

Repeated link text resolving to different destinations **is** computed and rendered,
but explicitly as background, and the skill is told not to emit a finding for it.

The reason is that this view cannot settle the question. Link purpose is **2.4.4
Link Purpose (In Context)**, and "in context" does the work: 2.4.4 lets the sentence
or block around a link be what tells it apart. Four `"Read more"` links going to four
different articles **pass** 2.4.4 when each ends its own article's paragraph; what
they fail is 2.4.9 (Link Only), which is AAA and out of scope. The rotor records
`underHeading` — a nearest-preceding heading, which is not programmatically
determined link context at all — and never captures the sentence that is. Reporting
a 2.4.4 verdict from it decides a Level A criterion by the AAA standard.

Pages are captured for link purpose separately, with `--sc 2.4.4`, which collects
that context. See the next section.

## 2.4.4 fixture markers

**None**, and no interaction — `linkPurposeProbe()` is a plain read. Page-level
(`<body>`, one row per file, same `PAGE_SC` branch as 2.4.3 and 2.4.6).

Page-level is a deliberate choice for a criterion that is *about* a single element.
A link is one element, but "ambiguous" is a **comparison**: one `"Read more"` is only
a defect relative to the other three, and a per-link sample can never see them.

`sr_link_purpose` holds `{links, truncated}`, each link carrying:

- `phrase` / `text` / `href` — what the reader announces, the visible text, and where
  it goes.
- `ariaLabel`, `labelledBy`, `title`, `imgAlt` — **how the announced name is
  supplied**. Techniques ARIA7/ARIA8 pass this criterion by giving a name the visible
  text does not, and it is the announced form that is judged; `imgAlt` is recorded
  with `null` for a missing `alt`, which is why a reader falls back to the URL.
- `context` — `{sentence, block, blockTag, tableHeaders, describedBy}`, the
  **programmatically determined link context**.

### The context is the whole feature

WCAG limits that context to a **closed list**: text in the same sentence, paragraph,
list item or table cell, the header cell of a table cell containing the link, and
text wired to it by `aria-describedby`/`title`. The probe collects exactly those and
nothing else — deliberately, because the tempting extras (the heading above, the
neighbouring link, whatever sits next to it visually) are not offered to the user
alongside the link and must not be allowed to excuse it.

Two details are load-bearing:

- **`sentence` is captured separately from `block`** because they are separate items
  on WCAG's list and they routinely disagree. A link at the end of a six-sentence
  paragraph is disambiguated by the paragraph but not by its own sentence; a probe
  that only recorded the block would call that a pass without noticing it had a
  weaker one.
- **A block whose entire text *is* the link is recorded as no context.**
  `<p><a>Read more</a></p>` has an enclosing paragraph containing nothing but the
  link. Storing `"Read more"` as its own context would make a bare link look
  disambiguated by itself, which is precisely the defect in
  `fail/read-more-links-without-context.html`.

### What is objective and what is not

`src/evidence.py` computes three observations: one announced name serving several
destinations, a name on the closed F63/H30 action/position list ("click here", "read
more", "details", …), and a name that is a bare URL. **None of them is a verdict**,
and each is rendered *paired with the context that is allowed to rescue it* — because
2.4.4 permits every one of those phrases when the surrounding text supplies the
purpose.

That pairing is what the fixtures test. `fail/read-more-links-without-context.html`
and `pass/read-more-links-with-context.html` are the same four ambiguous links; only
the context differs, and it flips the answer. The failure mode this suite is built to
catch is a classifier that flags repeated link text on sight.

One defect is not mechanisable at all: a name that is unique, specific and
**untrue** of its destination (`"Download the 2024 price list"` →
`href="/contact-us"`). No duplicate check or phrase list reaches it — only comparing
the name against the `href` does. `fail/link-name-misdescribes-destination.html`
holds that case, and it is why the evidence closes by telling the model that a clean
observation list is not a pass.

Two scope boundaries are enforced in the evidence rather than left to the prompt: a
link that announces **no name at all** is called out as 4.1.2's finding (and 1.1.1's
where an image with no `alt` caused it), and identical text separated by distinct
contexts is called out as **2.4.9, out of scope**.

Table headers are resolved from `headers="…"` where present, otherwise positionally
(the `<th>`s of the cell's own row, plus the nearest `<th>` above it in the same
column). Positional indexing means a table using `colspan`/`rowspan` may attribute
the wrong column header, so headers are recorded as context and never as the
deciding evidence.

## 1.3.2 fixture markers

**None.** `readingOrderProbe()` is a plain read, page-level (`<body>`, one row per
file, same `PAGE_SC` branch as 2.4.3 and 2.4.6).

**Not a second copy of the 2.4.3 sweep.** The two are easy to conflate:

| | 2.4.3 Focus Order | 1.3.2 Meaningful Sequence |
|---|---|---|
| covers | only **focusable** components | **all** content, text included |
| driven by | pressing Tab | the reader's own virtual cursor |
| fails when | the keyboard path fights the visual path | the **reading** path fights the visual path |

A page of CSS-reordered prose containing no focusable elements has a perfect tab
order and an unreadable reading order.

The reading sequence is *already* captured — `sr_transcript` is exactly that. What
it lacks is **position**: a transcript reading "C, A, B" is indistinguishable from a
correct one without knowing where each phrase came from. Attaching position is the
probe's whole job. `sr_reading_order` holds `{steps, complete, truncated}`, each step
pairing an announced phrase with a document-relative rect, plus `domIndex`,
`nodeType` and `isLeaf`.

`traverse()` is deliberately **left untouched** — it produces `sr_transcript` on
every row of every dataset, so this is a separate walk that happens to record more.

Three things the spike established, all reflected in the probe:

- **The reader walks in DOM order, not visual order.** The entire signal depends on
  this; if the cursor followed visual position the two orders would agree on every
  page and the probe would be worthless. Verified before anything else was built.
- **`activeNode` may be a TEXT node**, so positioning resolves through
  `parentElement` first.
- **Each element yields two steps** — its role ("paragraph") then its text, sharing a
  `domIndex`. `isLeaf` is recorded so the consumer can dedupe and skip containers
  like `<body>`, whose rect spans the page and would distort any ranking.

### Both orderings, and why

`src/evidence.py` compares the walk against the visual order computed **two ways**:
row-major (across, then down) and column-major (down each column, then across).
Matching *either* is normally fine; matching **neither** is the finding.

This is not defensive over-engineering. A genuine `column-count: 2` article reads
down the left column then down the right, matching only the column-major ordering —
a row-major-only check would flag a perfectly good page. One pass fixture exists
purely to hold that line.

### What the walk can and cannot settle

Against the ten fixtures the geometry catches **four of the five** defect fixtures,
with **no false positives** on any of the five passes.

The fifth is instructive: a layout `<table>` holding two independent columns of prose
is read cell-by-cell across each row, which **matches row-major exactly** — the
geometry says it is fine. The defect is that row-wise is the wrong way to read it, so
two unrelated passages get interleaved a sentence at a time. Only reading the
announced sequence reveals that, so the skill is told that a row-major match does not
by itself clear the page.

The other thing left to the model is the criterion's own precondition: 1.3.2 applies
only where **the sequence carries meaning**. A grid of independent tiles read in a
different order loses nothing, so a mismatch there is reported and then argued down,
not flagged.

## 2.1.2 fixture markers

**None** — the probe drives itself, page-level (`<body>`, one row per file, the same
`PAGE_SC` branch as 2.4.3 / 2.4.6 / 1.3.2). But this suite differs from those three
in two ways that matter.

> Design rationale, including the two bugs the fixtures caught and why this criterion's
> evidence leads with a verdict where the others withhold one:
> [`docs/2.1.2-no-keyboard-trap.md`](../docs/2.1.2-no-keyboard-trap.md).

**Its fixtures require `<script>`.** No purely declarative markup can block Tab, so
every trap here is a key or focus handler, armed at load (listener attached, dialog
already open) so nothing has to be clicked first. One rule follows: the fixture's
self-annotation must be an **HTML comment**, which `normalize.js` strips. A `//`
comment inside `<script>` is **not** stripped, and would hand the model the verdict
inside its own evidence.

**It is the only page-level probe that mutates the page** — phase 3 presses Escape,
which legitimately closes a dialog. So `capture.mjs` buffers the per-sample
transcripts and runs `keyboardTrapProbe()` *after* that loop rather than beside the
read-only page probes above it. A transcript read after an Escape would describe a
different page from the one whose HTML was snapshotted.

### Containment is not the defect

This is the criterion where the obvious signal is the wrong one. A modal dialog is
*supposed* to cycle Tab within itself; that is the ARIA authoring practice, not a bug.
A grid is entitled to consume Tab. What 2.1.2 forbids is holding focus with **no way
out** — so a probe that stopped at "focus is looping" would flag every correctly-built
dialog on the web. Detecting the loop is only phase 1; the phases that try to *get
out* are what decide it:

1. **forward** — Tab from the top until one of four things happens
2. **reverse** — Shift+Tab, because a component you can back out of is escapable
3. **escape** — the Escape key, then Tab, the documented way out of every APG dialog

`sr_keyboard_trap` holds `{stops, outcome, cycle, region, reverse, escape}`, where
`outcome` classifies phase 1:

| `outcome` | condition | meaning |
|---|---|---|
| `escaped` | `activeElement` fell back to `<body>` | focus left the page unaided; phases 2–3 skipped |
| `stalled` | the same element twice in a row | focus pinned — `preventDefault()` on Tab |
| `cycled` | an already-visited element returned | focus looping inside a subset |
| `cap` | the cap reached with no repeat and no exit | **not a finding**; a page with more tabbables looks identical |

"Got out" means focus reached `<body>` **or** an element outside the trapped set —
leaving the *component* is what the SC asks for, not leaving the page.

### The advisory clause, and what the ladder cannot press

2.1.2 permits a non-Tab exit only if the user is *advised of the method*, so `region`
carries what that judgement needs: the enclosing widget's `tag`/`role`/`aria-modal`,
its `aria-keyshortcuts`, its and its controls' `aria-describedby` text, and
`advisory` — the region's text **minus every interactive element's text**, which is
where an instruction like "press Escape to leave the calendar" is written.

Two details there were each worth getting right, both confirmed against the fixtures:

- **The region is the nearest enclosing WIDGET role, not the nearest common
  ancestor.** For a single pinned grid cell the common ancestor is the `role="row"`
  one level up, while the instruction is attached to the `role="grid"` above it — so
  the advisory would be missed on the one pass fixture that turns on it.
- **Control text has to come out of the advisory.** Without that exclusion a
  calendar's advisory reads `"11 12 13 14"` on the passing and the failing fixture
  alike, and the signal disappears into noise.

The ladder presses only Tab, Shift+Tab and Escape. A widget escapable only by
`Ctrl+M` therefore reads here as a trap, which is why `keyshortcuts` is captured
beside it and the skill is told to abstain rather than flag when a key it never
pressed is advertised. Content inside an `<iframe>`/`<object>` is a second known
limit: `activeElement` in the top document is the container element, so a trap
*inside* it cannot be told from a stall *on* it.

### What the ladder can and cannot settle

Against the ten fixtures the mechanical part is complete: all five defect fixtures
come back non-`escaped` with every recovery failing, and all five passes are cleared —
three by `outcome: escaped`, two by `escape.exited: true`. The two that matter are
`modal-wraps-tab-but-escape-closes` and `grid-advises-escape-to-leave`: both are
**contained**, with the same containment as the fixtures that fail, and both conform.
Without phase 3 they would be indistinguishable from a trap, which is the entire
reason it exists.

What is left to the model is the wording — whether text beside a widget actually tells
a user how to leave it or merely happens to sit there ("Choose a date" is not advice)
— so `src/evidence.py` renders the advisory as an observation and states plainly that
a detected cycle is not by itself a violation.

## 3.2.1 fixture markers

**None**, and `<script>` required — as for 2.1.2, a change of context is a handler, and
the self-annotation must be an **HTML comment** so `normalize.js` strips it. Page-level
(`<body>`, one row per file, same `PAGE_SC` branch). Every handler armed at load.

> Design rationale, including the addressing bug the pass fixtures caught:
> [`docs/3.2.1-on-focus.md`](../docs/3.2.1-on-focus.md).

`focusContextProbe()` focuses **each** component in turn, on its own, and records what
changed. `sr_focus_context` holds `{components, focusedVia, truncated}`.

### Content change is not context change

The mirror image of 2.1.2's trap. There, *containing focus* looked like a defect and was
correct. Here, *changing content* looks like a defect and is **normal**: a hint
appearing, a tooltip showing, a combobox listbox expanding in place, a field being
highlighted — all ordinary, all correct, all producing DOM mutations. What fails is a
change of **context**. A probe reporting "the DOM changed on focus" would flag every
well-built form on the web.

So the recorded signals are split by how decidable they are, and the split is the whole
design:

| group | fields | decidable? |
|---|---|---|
| unambiguous | `focusMovedTo`, `navigatedTo`, `opened`, `submitted` | yes — each is a change of context by definition |
| ambiguous | `mutations` | no — rendered *with the markup of what appeared*, and handed to the model |

`mutations` therefore carries the delta and only the delta: counts, the `outerHTML` of
added nodes capped at 300 chars, and — for attribute changes — the **target's**
`tag`/`role`/`id`/`aria-modal` alongside the attribute name.

That last part is load-bearing, not decoration. A dialog already in the DOM that merely
becomes visible **adds no node at all**: the only trace is `hidden` coming off a
`role="dialog"` element. Without the target's identity on attribute records, the worst
defect in the suite would leave nothing to find. One fail fixture exists to hold exactly
that path.

### Three things that had to be got right

- **Focus is applied programmatically, not by tabbing.** Isolation is the point: 3.2.1
  asks what *this* component does when focused, and a Tab sweep cannot separate
  "component N stole focus" from "component N+1 was reached normally". Known limit: a
  handler gated on `event.isTrusted` or `:focus-visible` never fires, so the probe cannot
  see it — `focusedVia` records this so the skill can abstain rather than read silence as
  a pass.
- **Elements are addressed by Playwright ELEMENT HANDLE, not `domIndex`.** This is the
  one probe that must break with how the others address elements, because it is the one
  probe that provokes DOM changes. The moment a focus handler inserts a hint, every
  index after it shifts by one and the probe starts focusing the wrong elements —
  silently, and worst on the pages whose handlers are *benign*. Caught by the pass
  fixtures: `hint-revealed-on-focus` and `combobox-expands-on-focus` both reported false
  focus loss until the addressing was fixed.
- **`window.open` and `HTMLFormElement.prototype.submit` are overridden, not observed.**
  Programmatic focus is not a user gesture, so a real `window.open` would be blocked by
  the popup blocker and the probe would see nothing at all; recording the *attempt*
  survives that. And `form.submit()` fires **no** `submit` event — by design in HTML, it
  skips both validation and the event — so a capture-phase listener alone misses the
  commonest auto-submit idiom there is, and would record it only as a navigation.

`navigatedTo` is stored as a **path**, not an absolute URL: the static server binds an
ephemeral port, so the absolute form would differ on every capture and the dataset would
never diff clean against itself. Two independent captures are byte-identical.

### What the probe can and cannot settle

Against the ten fixtures the mechanical half is complete: each of the five defect
fixtures fires exactly one unambiguous signal, on the intended component, by a distinct
mechanism (focus moved / navigated / window opened / form submitted / dialog un-hidden);
none of the five passes fires any. Three passes come back mutation-only and two come back
entirely unchanged.

What is left to the model is which mutations matter. `hint-revealed-on-focus` adds a
node, `combobox-expands-on-focus` adds three and flips `aria-expanded`, and both conform
— while `modal-dialog-opens-on-focus` changes one attribute and does not. Only reading
what appeared separates them, which is why the markup is in the column.

## 3.2.2 fixture markers

**None**, `<script>` required, annotations in **HTML comments** only — as for 3.2.1,
whose probe this one is the sibling of. `inputContextProbe()` changes **each
component's setting** in turn and records what happened, with the same per-component
record shape as `sr_focus_context` so `src/evidence.py` renders both with the same
helpers.

> Design rationale, including the crossover leak the isolation check caught:
> [`docs/3.2.2-on-input.md`](../docs/3.2.2-on-input.md).

Shared with 3.2.1: `armContextRecorders()` (nothing in it was ever focus-specific) and
`visibleHandles(page, selector)`. 3.2.2 passes it `SETTABLE` rather than `FOCUSABLE` —
form controls and ARIA widgets that hold a value. **Buttons and links are deliberately
excluded**, and their absence is the criterion rather than an oversight: activating one
is a user *request*, which 3.2.2 permits outright and 3.2.5 governs.

### Focus first, arm second

The ordering the probe turns on. A setting cannot be changed without focus touching the
control first, so with the recorders armed any earlier **every 3.2.1 on-focus defect
would be recorded a second time here as an on-input defect** — same fixtures, nothing in
the data to say which criterion was at fault. Each component is therefore focused and
left to settle *before* recording starts.

One consequence is easy to miss and did in fact go wrong first time: `focusHeld` must be
measured against **whatever holds focus after the focus phase**, not against the
component's own handle. Focusing a control that steals focus leaves the handle unfocused
before the setting is ever changed, and comparing to the handle reports that as an
on-input focus change. The isolation check below caught exactly this, on two of five
fixtures.

### The advisory, and why `hasText` is not `wasAdvised`

3.2.2 is the only criterion here with an explicit exception: a change of context on
input conforms **if the user was advised of the behaviour beforehand**. So the same
measurement is a pass or a fail depending on the text beside the control, and `advisory`
captures three things separately:

| field | strength |
|---|---|
| `describedBy` | strongest — `aria-describedby`, announced with the control |
| `precedingText` | real but weaker — non-interactive text before it in its group |
| `label` | **not advice at all** — a name identifies a control, it does not warn about it |

Folding labels into the advisory was the first implementation and it destroyed the
signal: every control on every page has a label, so the flag went true for a bare no-JS
form and the one comparison this criterion turns on stopped separating. The flag is
called `hasText`, not `hasAdvised`, for the same reason — a hint reading "We only use
this to send you updates" sets it true and warns nobody. Whether wording actually warns
is a judgement, and it stays with the model.

Ordering is part of the SC ("*before* using the component"), so the `precedingText` walk
stops at the control. Text inside other controls is skipped, or a `<select>`'s own
options read back as advice — the same trap the 2.1.2 region capture hit.

### What the probe can and cannot settle

Against the ten fixtures every defect fires exactly one unambiguous signal by a distinct
mechanism (submitted / window opened / navigated / focus moved / content replaced), and
no passing fixture fires any. Captures are byte-identical across runs.

The pair that matters is `select-navigates-on-change` and
`select-navigates-on-change-with-warning`: **the same handler, the same navigation, the
same recorded measurement**, differing on nothing but `advisory`. One fails and one
conforms. That pair is the reason the advisory is captured rather than inferred, and it
is what the isolation between behaviour and exception is measured against.

## 1.3.3 fixture markers

**None, and no `<script>` either** — the first new suite since 2.4.6 that is pure markup
and CSS, because nothing has to *happen* for this defect to exist. Annotations stay in
HTML comments as always.

> Design rationale, including the two bugs the fixtures caught:
> [`docs/1.3.3-sensory-characteristics.md`](../docs/1.3.3-sensory-characteristics.md).

### A criterion that fails in prose

1.3.3 is shaped unlike anything else here. 2.1.2, 3.2.1 and 3.2.2 fail in **behaviour**;
2.4.3, 2.4.4, 2.4.6 and 1.3.2 fail in **structure**. This one fails in **language**:
"click the round button on the right" is a defect and "click the round Submit button on
the right" is not, and the markup is byte-identical either way.

That forces the page-level sample — an instruction and the component it points at are
different elements, often far apart, and the per-element sweep would capture the
component and drop the sentence that fails.

It also makes the probe's job narrow. Most of what this criterion needs is already in
`element_html` (the `<body>` sample carries the prose *and* the components) and
`parent_html` (the stylesheet). `sensoryReferenceProbe()` deliberately does not restate
any of that. It adds three things:

| | why |
|---|---|
| **resolved layout geometry** | what is actually left/right/above/below is the product of flex, grid, float and absolute positioning. CSS rules are not positions; only the rendered box is one. |
| **computed colour** | `class="go"` says nothing until the cascade runs. |
| `namesInSentence` | derivable, but it is the decisive test, and the probe already knows every component's real accessible name. |

One fail fixture exists purely to prove the first row is a measurement and not an
inference: `instruction-refers-to-position-only.html` uses `flex-direction: row-reverse`,
so the links the instruction calls "on the right" are the ones written **first** in
source. They resolve to `x=1044` against a page midline of `640`.

### The lexicon is crude, and one fixture proves it

`sr_sensory_reference` holds `{references, candidates, truncated}`. Detection is a word
list covering all six characteristics; **position and colour are resolved against
measurement, shape/size/orientation/sound are reported as text matches only**, and every
reference says which of its categories carry corroboration.

The list matches ordinary prose constantly. `position-word-is-not-an-instruction.html`
is built entirely out of such matches — "the **right** to appeal", "see **below** for our
address", "a **large** number of appeals", "**green** belt land", "in the **round**" —
and is a **pass**. Four candidates, no instruction among them, no component identified.
The evidence therefore presents references as candidates and makes the model answer two
questions in order: *is this an instruction identifying a component at all?* and only
then *is the sensory characteristic the sole identifier?*

`candidates` is deliberately wider than "controls": interactive elements, `<label>`s
(the usual carrier of a colour an instruction refers to), **and** named regions and
headings — without the last, "the Refine results panel on the right" has nothing to
match against and a conforming page reads as a failing one.

### What the scan can and cannot settle

Against the ten fixtures the decisive pair is
`instruction-names-button-by-colour` / `instruction-names-button-and-colour`: the same
two buttons, the same computed colours, the same sentence shape, and one word of
difference. `namesInSentence` is `[]` on one and `["Confirm"]` on the other, and that is
the whole distinction between a failure and a conforming page.

What is left to the model is everything the lexicon cannot know: whether a sentence is
an instruction, whether a name in a sentence is being used as a name (in "press the red
button to **discard** it" the word matches a button called "Discard", but it is a verb),
and whether "round" or "large" or "the beep" refers to anything at all.

Flags:
- `--dir <path>`  input suite folder, relative to the repo root; repeatable.
  Default: `tests/SC 1.3.1`, `tests/wcag 1.1.1`, `tests/wcag 4.1.3/fail`,
  `tests/wcag 4.1.2/fail`. Skipped entirely if `--url` is given instead (see below).
- `--url <address>`  seed a same-origin crawl of a live page/site instead of (or
  alongside) local fixtures; repeatable. See "Crawling live URLs" below.
- `--max-pages <n>`  cap on pages captured per `--url` seed (default `30`).
- `--sc <value>`  opt into a criterion's extra sample sweep. `3.3.1` and `3.3.2`
  both add `form` to the candidate set, and `3.3.2` additionally switches on the
  labels/instructions probe. `2.4.3` and `2.4.6` each replace the sweep entirely
  with a single page-level sample, switching on the focus-order Tab sweep and the
  headings/labels rotor view respectively; `1.3.2`, `1.3.3`, `2.1.2`, `3.2.1` and `3.2.2` do the same,
  switching on the reading-order walk, the sensory-characteristics scan, the
  keyboard-trap escape ladder, the on-focus context probe and the on-input context probe
  respectively. Unset for every other suite. There is no inference from folder or file
  names.
- `--label <value>`  ground-truth label for every row (default `inaccessible`;
  these suites are all-inaccessible examples).
- `--out <base>`  output base name written to the repo root (default
  `dataset_generated`) → `<base>.csv` (+ BOM, Excel-safe) and `<base>.jsonl`.
- `--no-sr`  skip the virtual screen reader.

## Crawling live URLs

`--url <address>` points the capture pipeline at a real, deployed page instead
of a local fixture. Unlike `--dir`, which walks a fixed folder of files, `--url`
**crawls**: it captures the seed page, reads every `<a href>` on it, and queues
same-origin links for capture too, breadth-first, until `--max-pages` is
reached or the queue empties. Every downstream step — DOM extraction, the
virtual screen reader, every `--sc` probe — is identical to fixture capture;
only how the page was reached differs, so `lib/extract.js` and `lib/vsr.js`
needed no changes at all.

```bash
node capture.mjs --url https://example.com --max-pages 15 --out live_site
node capture.mjs --url https://a.example --url https://b.example --max-pages 10
node capture.mjs --dir "tests/wcag 1.1.1" --url https://example.com --out mixed
```

- **Same-origin only.** Links are filtered to the seed's own origin (resolved
  *after* following any redirect, so `http://` seeds that redirect to `https://`
  still crawl correctly); external links are recorded nowhere and never queued.
- **`sample_id`/`source_file`** for a crawled row are derived from the page's
  URL (`lib/crawl.js`'s `urlToFile`) rather than a filename, e.g.
  `example.com_about::el3`.
- **No local server involved.** `--dir` fixtures are served off disk through the
  ephemeral static server (`lib/server.js`); `--url` targets are navigated to
  directly and never touch it.
- **Safety of the interaction probes on real pages:** the 3.2.1/3.2.2 context
  probes never let a real `window.open` or form submission happen — both are
  intercepted and only the *attempt* is recorded (see `lib/vsr.js`'s
  `armContextRecorders`) — and 3.3.1's `triggerErrors` is self-gated on a
  `data-error-trigger` marker that only this repo's own fixtures carry, so it's
  a no-op on real pages. The one probe that does perform a real interaction is
  4.1.2's role/state/value probe, which genuinely clicks real controls
  (checkboxes, toggles, etc.) to observe the accessible-name change — harmless
  on most pages, but only point `--url` at sites you're authorized to crawl and
  interact with at scale.

## How it scales across criteria

`lib/extract.js` is the one seam that decides which elements become samples. It
does a single document-order sweep over a candidate set covering:

| WCAG SC | elements captured |
|---|---|
| 1.1.1 | `img`, `svg`, `canvas`, `picture`, `input[type=image]`, `[role=img]` |
| 1.2.1 | `audio`, `video`, `object`, `embed`, `iframe` |
| 1.3.1 | `table`, `ul`/`ol`/`dl`, orphan `li`/`dt`/`dd`, fallback content block |
| 4.1.3 | `[role=status/alert/log/progressbar/marquee/timer]`, `[aria-live]`, `output`, `progress` — plus status messages authored with **no** live-region markup, which fall through to the fallback content block |
| 4.1.2 | `[role=checkbox/switch/radio/slider/combobox/listbox/option/tab/menuitemcheckbox/menuitemradio/spinbutton]`, `input[type=checkbox/radio/range]`, `select`, `[aria-pressed]`, `[aria-expanded][aria-controls]` |
| 3.3.1 | `form` — **only under `--sc 3.3.1`**. The whole form is the sample, because the SC needs the field, its label and the error text judged together; a bare error `<p>` in isolation cannot show whether the item in error is identified. The form suppresses everything inside it, so an error summary carrying `role="alert"` does not also surface as a second, evidence-poor row. |
| 3.3.2 | `form` — **only under `--sc 3.3.2`**. Same sample as 3.3.1 and for the same reason: a bare `<input>` cannot show whether the label beside it is actually associated with it, nor whether a hint elsewhere in the form is wired to it. |
| 2.4.3 | `body` — **only under `--sc 2.4.3`**, and it *replaces* the sweep rather than adding to it. Focus order is a property of the whole page, so the page is the sample and each file yields exactly one row. |
| 2.4.4 | `body` — **only under `--sc 2.4.4`**, same page-level branch. A link is a single element, but "ambiguous" is a comparison against the OTHER links, which a per-link sample cannot see; and the context that decides the criterion (a table's header cells) can sit far outside the link's own parent. |
| 2.4.6 | `body` — **only under `--sc 2.4.6`**, same page-level branch. Headings and labels are judged as a *set* (is each one distinguishable from its peers?), which no single element can show. |
| 1.3.2 | `body` — **only under `--sc 1.3.2`**, same page-level branch. The reading *sequence* is a property of the whole document, and covers all content, not just the focusable subset 2.4.3 sees. |
| 2.1.2 | `body` — **only under `--sc 2.1.2`**, same page-level branch. Whether focus can escape is a property of the page: the trap is wherever the keyboard ends up stuck, which no single element can be nominated in advance. |
| 3.2.1 | `body` — **only under `--sc 3.2.1`**, same page-level branch. *Any* component may change context when focused, and the effect (focus moving, the page navigating, a dialog opening elsewhere) lands outside the component that caused it, so the page is the sample. |
| 3.2.2 | `body` — **only under `--sc 3.2.2`**, same page-level branch and the same reasoning as 3.2.1, with the trigger changed from receiving focus to having a setting changed. |
| 1.3.3 | `body` — **only under `--sc 1.3.3`**, same page-level branch. An instruction and the component it points at are different elements, often far apart; the per-element sweep would capture the component and drop the sentence that fails. |

Media/images nested inside an interactive control escalate to that control
(e.g. an image-only link is captured as the `<a>`). Containers suppress their
leaf/media descendants but **not** nested tables/lists (those are legitimate
separate samples).

To add a new criterion, extend the `SEL` map in `lib/extract.js` and add a skill
under `../src/skills/` (auto-discovered — no registry to edit). Keep the new
selector **opt-in behind `--sc`** unless it genuinely cannot collide: adding it
to the default `CANDIDATES` steals the fallback content block from every page it
matches, and for 4.1.3 the *absence* of that block is the defect signal. `status`
and `control` (4.1.2) are both safe in the default set because they require an
explicit role/type to match at all.

If the new criterion's sample tag cannot be told apart from another suite's — as
with 2.4.3, whose `<body>` sample looks identical to the generic fallback block —
declare the probe column the skill cannot be judged without:

```yaml
applies_when:
  element_tag: [body]
  requires_column: [sr_focus_order]
```

`src/router.py` then drops that skill for rows with no data in the named columns,
so its rubric is not attached to every container row in every other dataset. Skills
without the key are unaffected. Note that `src/skills/loader.py` iterates every
`applies_when` value, so the key **must** be a YAML list — a bare string would be
split into characters.

## Modules

- `capture.mjs` — entry: suites → per-page capture → rows → CSV/JSONL.
- `lib/extract.js` — sample selection + raw HTML/parent/context capture.
- `lib/interact.js` — 3.3.1: fills + submits the form before extraction so the
  error state exists in the snapshot. No-op without `data-error-trigger`.
- `lib/aria.js` — `ariaSnapshot()` → `ax_role`/`ax_name`/`ax_level`/`ax_subtree`.
- `lib/axe.js` — axe-core in-page, violations mapped to each sample.
- `lib/vsr.js` — drives the virtual screen reader (transcript + reading order,
  the 4.1.3 status-announcement probe, the 4.1.2 role/state/value probe, the
  3.3.2 labels/instructions probe, the 2.4.3 focus-order Tab sweep — which also
  drives Playwright's keyboard, since synthetic key events cannot move native focus
  — the 2.4.6 headings/labels rotor view, the 1.3.2 reading-order walk, the 2.1.2
  keyboard-trap escape ladder, the 3.2.1/3.2.2 context probes, and the 1.3.3
  sensory-characteristics scan). The two context
  probes share their recorders (`armContextRecorders`), their element enumeration
  (`visibleHandles`) and their record shape, differing only in what triggers the change.
  The keyboard probes share one in-page stop reader,
  `readActiveStop()`, whose `geometry` flag selects 2.4.3's superset (position,
  `obscured`, `controlsRange`); its key order is deliberate, since that is what gets
  written into the column. `traverse()` (which produces `sr_transcript`) is
  deliberately never modified by any of them: every dataset's regression baseline
  depends on it.
- `lib/rows.js` — schema, SC/label resolution, CSV/JSONL writers.
- `lib/{server,csv,normalize}.js` — static server, CSV encoder, HTML cleaner.
  `normalize.js` also strips **HTML comments**: the fixtures annotate themselves
  with the defect they demonstrate, and a comment inside a captured element would
  otherwise hand the model the verdict as part of its own evidence.

Dependencies resolve from the shared `d2/node_modules` (Playwright, axe-core,
virtual-screen-reader already installed there); no local install needed.
