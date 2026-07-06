---
sc: "1.3.1"
technique: "hidden-or-css-content"
title: "Content hidden from (or injected outside) the accessibility tree"
applies_when:
  element_tag: [main, body, section, div, article, a, span, p, button]
  ax_role: [main, link, text, region]
signals:
  - field: css_generated_content
    look_for: "text injected via ::before/::after `content:` (e.g. a food name 'Pizza') that is meaningful but absent from the DOM and never announced by the screen reader"
  - field: hidden_content
    look_for: "meaningful text removed from the a11y tree via computed display:none / visibility:hidden (e.g. ' about football' inside a 'Read more' link)"
  - field: element_html_raw
    look_for: "distinct context inside display:none / visibility:hidden (inline or class-based); or a node whose visible text is inserted via CSS"
  - field: sr_transcript
    look_for: "an ambiguous phrase (e.g. just 'Read more') where hidden context was dropped, or missing text that the CSS was meant to add"
  - field: sr_reading_order
    look_for: "the full announced order to confirm the contextual phrase is absent"
---
## Violation criteria (1.3.1 for hidden / CSS content)
Flag `inaccessible` under `1.3.1` when meaningful information is not available to
assistive tech because of how it is hidden or inserted. The capture now resolves
computed CSS for you — inspect the two dedicated evidence sections first:
- **CSS-generated content**: the `css_generated_content` field lists text injected
  via `::before`/`::after` `content:`. If it carries **meaning** (e.g. a food name
  `"Pizza"` completing "My favourite food is ") and that text is **absent** from
  `sr_transcript`/`sr_reading_order`, the sighted user reads content the screen
  reader never gets → `inaccessible`. (Purely decorative glyphs like `">"`/`"v"`
  on a disclosure widget are **not** a violation.)
- **The hidden-text trap**: the `hidden_content` field lists text removed from the
  a11y tree via computed `display:none` / `visibility:hidden` (inline OR
  class-based). If an interactive control (`<a>`/`<button>`) relies on such a span
  for distinct context (e.g. `" about football"` behind a "Read more" link) and
  the transcript announces only the ambiguous placeholder, → `inaccessible`.
  `display:none`/`visibility:hidden` remove content from the a11y tree (unlike a
  visually-hidden/clip technique, which keeps it).

## Insufficient evidence
Only when **both** `css_generated_content` and `hidden_content` are empty *and* the
technique still implies content is injected/hidden by CSS you cannot see (e.g. a
rule on an element outside the captured scope), return `insufficient_evidence` and
say which computed field was empty. Do **not** abstain when the injected/hidden
text is right there in those fields — decide on it.

## Pass criteria
- All meaningful context is in the DOM and reflected in `sr_transcript` /
  `sr_reading_order` (the contextual phrase is actually announced).

## Examples
- INACCESSIBLE: `<a>Read more <span style="display:none"> about football</span></a>`
  → `hidden_content` lists `span [display:none] hides text: " about football"`,
  and the transcript says only "link, Read more".
- INACCESSIBLE: `<p id="css-generated-text">My favourite food is </p>` where
  `css_generated_content` lists `p#css-generated-text ::after injects text:
  "Pizza"` — the food name is shown to sighted users but never announced.
- INSUFFICIENT: neither computed field is populated yet the technique implies a
  CSS rule out of scope — say which field was empty.
