---
sc: "2.4.6"
technique: "headings-labels"
title: "Heading or label does not describe its topic or purpose"
applies_when:
  element_tag: [body]
  requires_column: [sr_headings_labels]
signals:
  - field: sr_headings_labels
    look_for: "PRIMARY. The rotor view: `{headings, labels, links}`, every entry carrying what the reader ANNOUNCES for it. Read each list AS A LIST — out of document order, ignoring the page around it — because that is how assistive-tech users consume them: a headings menu, a form-controls list. Each heading carries `introduces` (the content it heads) and each label its `tag`/`type` and `underHeading`. Ask two separate questions of every entry: does it identify itself among its peers, and is it TRUE of what it introduces? Judge HEADINGS and LABELS only — `links` is listed for background and is 2.4.4's to decide."
  - field: sr_transcript
    look_for: "SECONDARY. The reading-order walk. An item can read perfectly well here — anchored by the paragraph before it — and still be useless in the rotor list. Use this to confirm what surrounding context a sighted or in-flow reader gets, which is exactly the context the list takes away."
  - field: element_html
    look_for: "CORROBORATION. The markup behind an entry: whether a heading's text comes from nested markup or aria-label, and whether a label is a <label for> or an aria-label."
  - field: parent_html
    look_for: "the <html> element, for anything in <head> (page <title>) that establishes what the page as a whole is about, against which the h1 can be judged"
---
## Violation criteria (2.4.6 Headings and Labels)
**2.4.6 Headings and Labels is Level AA and is in scope for this page.**

Headings and labels must **describe topic or purpose**. Two things have to hold, and
they fail independently:

1. **It identifies itself among its peers.** In a list of headings stripped of
   context, each entry must be distinguishable. Three sections headed "Overview"
   are individually fine and collectively useless.
2. **It is true of what it introduces.** A heading can be specific, unique and
   still simply wrong about the content beneath it.

## How to read the rotor view
Some of this is objective and has already been computed for you in the evidence:
duplicate headings, duplicate labels, and repeated link text resolving to
**different** destinations. Treat those as established.

The rest is the judgement, and it is the substance of this criterion:

- **Genericness.** "Section 1", "More information", "Details", "Other" name a
  position or a category rather than a topic. Labels have their own version of
  this: a label naming a **data type** rather than a **purpose** — "Number",
  "Date", "Type" — identifies nothing on its own. Ask what the entry would tell
  someone who heard only it.
- **Accuracy.** Compare each heading's announced text against its `introduces`.
  A heading reading "Payment details" whose section content is "Street address,
  Town or city, Postcode" is a failure even though the heading is perfectly
  specific and unique — a user who jumps to it lands somewhere else entirely.
  Nothing but this comparison can catch that.

Flag `inaccessible` under `2.4.6` when any of the following holds:

- **Duplicate headings over different content.** The same announced heading text
  introduces materially different sections, so the headings list cannot be
  navigated by.
- **A generic or placeholder heading** that names its position or nothing at all
  rather than its topic.
- **A heading that does not match its `introduces` content** — specific but untrue.
- **A label that names a data type, not a purpose**, and depends on a nearby
  heading to be understood. Check `underHeading`: if the label only makes sense
  once you add it, the label is not doing its job.
- **Identically-labelled controls that do different things** — several buttons all
  announced "button, Click here" where one requests a statement and another
  cancels a claim irreversibly.

## Link text — NOT judged here
The rotor view lists `links` because a links list is part of how readers navigate,
and repeated link text is worth seeing while you read the page. But **do not report
any finding about a link from this row**, under `2.4.4` or any other key.

Link purpose is **WCAG 2.4.4 Link Purpose (In Context)**, and "in context" is the
operative half: 2.4.4 lets the sentence, paragraph, list item or table cell around
a link be what makes it unambiguous. Four "Read more" links going to four different
articles **pass** 2.4.4 when each ends its own article's paragraph — what they fail
is 2.4.9 (Link Only), which is Level AAA and out of scope.

This view cannot tell those two cases apart. It records `underHeading`, a
nearest-preceding heading, which is *not* programmatically determined link context
at all, and it does not capture the sentence or block that is. Judging link purpose
from it would decide a Level A criterion by the wrong standard.

Pages are captured for 2.4.4 separately, with `--sc 2.4.4`, which collects that
context. Leave it to that capture.

## Pass criteria
- Every heading is distinguishable from the others in the list, and describes the
  content it actually introduces.
- Labels name what the field is **for**, so each identifies its control on its own.
- Controls that do different things are labelled differently.
- An `aria-label` supplying a more descriptive name than the visible text is fine —
  it is the announced form this criterion is judged on.

## Insufficient evidence
- A page with fewer than two headings and no labels: there is no list to be
  ambiguous within, and nothing to compare.
- A heading whose `introduces` is **empty** — there is no content to check it
  against, so accuracy cannot be assessed. Say so rather than guessing.
- Text whose descriptiveness genuinely depends on domain knowledge the capture
  cannot supply (a product name, a form reference). Do not flag specialist
  vocabulary merely for being unfamiliar.
- The `h1`'s `introduces` spans the whole page and is truncated, so judge the `h1`
  against the page's subject rather than against that excerpt in detail.

## Scope boundary
Four neighbours are close, and this skill judges only **descriptiveness**:
- **1.3.1 `heading-structure`** owns skipped levels, headings faked with `<b>`/CSS,
  and empty heading elements — *semantics and hierarchy*. A perfectly descriptive
  heading at the wrong level is 1.3.1's problem, not this one. Do not flag 2.4.6
  for a skipped level.
- **3.3.2** owns whether a label is **provided** at all. A control with no label is
  3.3.2's; a control with a *useless* label is this skill's.
- **4.1.2** owns whether an accessible name is **exposed** to assistive tech. If
  nothing is announced, that is 4.1.2. If something is announced but says nothing,
  that is 2.4.6.
- **2.4.4** owns link purpose entirely, and is captured separately — see the
  section above. Never emit a `2.4.4` key from this row.

## Examples
- INACCESSIBLE (2.4.6): three `<h2>Overview</h2>` headings introducing Universal
  Credit, PIP and Attendance Allowance → announced identically, so the headings
  list cannot distinguish them.
- INACCESSIBLE (2.4.6): `<h2>Payment details</h2>` whose `introduces` is
  "Street address Town or city Postcode" → specific, unique, and untrue of its
  section.
- INACCESSIBLE (2.4.6): `<h2>Section 1</h2>`, `<h2>More information</h2>` → these
  name a position and a category, not a topic.
- INACCESSIBLE (2.4.6): labels "Number", "Date", "Type" → data types, meaningful
  only next to their heading; announced alone they identify nothing.
- INACCESSIBLE (2.4.6): three `button, Click here` controls that report a change,
  request a statement, and permanently cancel a claim.
- NOT A FINDING HERE: four `link, Read more` entries with hrefs
  `/news/passport-fees`, `/news/test-centres`, `/news/winter-fuel`,
  `/news/tax-deadline`. Same text, four destinations — and still possibly a pass,
  because the paragraph around each one may name its article. That is 2.4.4's
  question and needs the `--sc 2.4.4` capture. Report nothing for it here.
- ACCESSIBLE: headings "Universal Credit" / "Personal Independence Payment" /
  "Attendance Allowance" → each names its own section.
- ACCESSIBLE: labels "Passport number", "Date of birth", "Date you want the licence
  to start" → each states a purpose.
- ACCESSIBLE: `<h2>Delivery address</h2>` introducing "Street address Town or city
  Postcode" → the heading is true of its content.
