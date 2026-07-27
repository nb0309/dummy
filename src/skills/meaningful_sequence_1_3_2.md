---
sc: "1.3.2"
technique: "meaningful-sequence"
title: "Reading sequence does not match the meaningful sequence"
applies_when:
  element_tag: [body]
  requires_column: [sr_reading_order]
signals:
  - field: sr_reading_order
    look_for: "PRIMARY. The reader's own cursor walk, each step pairing what was announced with the document position it came from. The evidence already reports whether the reading order matches the ROW-major visual order, the COLUMN-major one, or NEITHER. 'Neither' is strong evidence of a defect. But note carefully: matching one of them does NOT clear the page — a layout table read cell-by-cell across rows matches row-major perfectly while interleaving two unrelated passages into nonsense. Read the announced phrases IN SEQUENCE and ask whether they still make sense in that order."
  - field: sr_transcript
    look_for: "the same walk without positions. Best used to read the content as continuous prose: if the passage contradicts itself, refers forward to something not yet said, or answers a question before asking it, the sequence is broken regardless of what the geometry says."
  - field: element_html
    look_for: "CORROBORATION. The DOM sequence itself, and the structures that decouple it from the visual one: a layout <table> holding independent columns of prose, content written in one order and positioned in another."
  - field: parent_html
    look_for: "the <html> element, so the <head> stylesheet is here. This is where the cause lives: `order:` on a flex child, `float`, `position: absolute/fixed`, `grid-auto-flow`, `direction`. A reading/visual mismatch with one of these in the stylesheet has its explanation."
---
## Violation criteria (1.3.2 Meaningful Sequence)
**1.3.2 Meaningful Sequence is Level A and is in scope for this page.**

When the sequence in which content is presented **affects its meaning**, a correct
reading sequence must be programmatically determinable.

## First, the gate: does the sequence carry meaning here?
This criterion applies **only** where order matters. Establish that before treating
any mismatch as a defect. Order carries meaning in:

- continuous prose, where each sentence builds on the last;
- numbered or dependent steps ("Step 2" means nothing before "Step 1");
- a form, where fields follow a logical progression;
- a heading and the content it introduces; a question and its answer; a figure and
  its caption; an introduction that frames what follows.

Order does **not** carry meaning in a grid of independent tiles, a card deck of
unrelated services, a set of sibling promos — nothing refers to anything else, and
reading them in a different order loses nothing. A geometric mismatch there is
**not** a 1.3.2 failure. Say so and return `accessible` rather than flagging it.

## Then, the evidence
The walk is compared against both visual orderings, and there are three outcomes:

- **Matches NEITHER** — the sequence a reader hears is not the sequence on screen
  under any reasonable way of reading the layout. Where the gate above is met, this
  is the violation.
- **Matches COLUMN-major** — normal and healthy for a multi-column layout, a
  side-by-side article and aside, or a column-filled grid. Not a defect on its own.
- **Matches ROW-major** — the ordinary case, and usually fine. **But this does not
  by itself clear the page.** See below.

Flag `inaccessible` under `1.3.2` when the sequence carries meaning and:

- **Reading order matches neither ordering.** CSS `order`, `float`, or absolute
  positioning presents prose in one sequence while exposing another; numbered steps
  are announced out of order; an introduction painted at the top is read last,
  after the detail it was meant to frame.
- **A layout table interleaves independent passages.** Two or more columns of
  continuous prose placed in a `<table>` for layout are read cell-by-cell **across
  each row**, so a sentence from column one is followed by an unrelated sentence
  from column two. The geometry check reports this as matching row-major, because
  it does — the defect is that row-wise is the wrong way to read it. Detect it by
  reading the announced sequence: alternating, unrelated subjects with no thread
  running through them.
- **Content is separated from what it belongs to** — a caption read before its
  figure, an aside read before the article it annotates, a heading detached from
  its section.

## Pass criteria
- Reading order matches the row-major **or** column-major visual order, and the
  announced sequence reads coherently end to end; **or**
- the content is genuinely order-independent, so the criterion does not apply.

## Insufficient evidence
- **`truncated: true`** — the walk hit its cap, so the full sequence was never
  observed. Do not judge order from a partial walk.
- Fewer than about three content steps: too little to establish a sequence.
- A layout whose intended reading order is genuinely ambiguous, with no prose thread
  to settle it. Say the intended order cannot be determined rather than inventing
  one and flagging against it.
- Positions come from layout rectangles, so content moved by transforms may not sit
  where the numbers suggest. If the geometry contradicts the markup, trust the
  markup and say why.

## Scope boundary
- **2.4.3 Focus Order** owns the **keyboard** sequence; this owns the **reading**
  sequence. They are different criteria over different content — 2.4.3 sees only
  focusable components, this sees all content including plain text. A single CSS
  reorder can break both at once: that is genuine co-occurrence, **not** overlap, so
  report the 1.3.2 finding on its own merits and do **not** defer to 2.4.3.
- **1.3.1 Info and Relationships** owns *what* the relationships are — headings,
  lists, tables, groupings. This owns their **order**. A correctly marked-up list
  presented in the wrong sequence is 1.3.2's.
- **2.4.6 Headings and Labels** owns whether a heading's *text* describes its
  content. This owns whether it is read in the right *place*.

## Examples
- INACCESSIBLE: three paragraphs of prose with `order: 1/2/3` applied so the DOM
  runs third-first-second → the reader is told "once you have done both of the
  above" before either step has been mentioned. Matches neither ordering.
- INACCESSIBLE: "Step 1 / Step 2 / Step 3" shown in order but written 3, 1, 2 →
  announced out of sequence, and the steps are dependent.
- INACCESSIBLE: an introduction at `position: absolute; top: 0` written last in the
  DOM → the fees are read before the sentence saying which applications they apply
  to, reversing the meaning of everything before it.
- INACCESSIBLE: a floated sidebar written first → "this does not apply to Ireland"
  is announced before anything it could fail to apply to.
- INACCESSIBLE: two independent columns of prose in a layout `<table>` → announced
  "you may ask for a review…", "you must tell us within one month…", "a review is
  free…", alternating between two unrelated passages. **Reports as matching
  row-major**; the defect is visible only in the announced sequence.
- ACCESSIBLE: a `column-count: 2` article → matches column-major, which is exactly
  what a multi-column layout should do. Not a defect.
- ACCESSIBLE: flex placing an aside beside an article with no `order` → the aside
  still follows the article in the reading sequence.
- ACCESSIBLE: a grid of four unrelated service tiles filled column-wise → even if
  the order differs from a row-major sweep, no tile refers to another, so the
  sequence does not affect meaning and the criterion does not apply.
