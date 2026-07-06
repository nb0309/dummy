---
sc: "1.3.1"
technique: "hidden-or-css-content"
title: "Content hidden from (or injected outside) the accessibility tree"
applies_when:
  element_tag: [main, body, section, div, article, a, span, p, button]
signals:
  - field: element_html
    look_for: "meaningful text inside an inline style=\"display:none\" / \"visibility:hidden\", an aria-hidden=\"true\" wrapper, or a hidden attribute — especially distinct context behind an interactive control (e.g. ' about football' inside a 'Read more' link)"
  - field: sr_transcript
    look_for: "an ambiguous phrase (e.g. just 'Read more') where the hidden context was dropped, or text present in the HTML that the screen reader never announces"
  - field: parent_html
    look_for: "the surrounding control/context confirming that the dropped text was needed to disambiguate the element"
---
## Violation criteria (1.3.1 for hidden content)
Flag `inaccessible` under `1.3.1` when meaningful information present in the raw
`element_html` is **not** available to assistive tech because it is hidden from
the accessibility tree:
- **The hidden-text trap**: `element_html` contains a span/element with
  `style="display:none"` / `style="visibility:hidden"` / `aria-hidden="true"` /
  `hidden` that carries **meaningful** text, and an interactive control
  (`<a>`/`<button>`) relies on it for distinct context (e.g. `" about football"`
  behind a "Read more" link). If `sr_transcript` announces only the ambiguous
  placeholder ("link, Read more") and never the hidden text, → `inaccessible`.
  `display:none`/`visibility:hidden`/`aria-hidden` remove content from the a11y
  tree (unlike a visually-hidden/clip technique, which keeps it).
- **Text in the HTML but never announced**: text clearly present in `element_html`
  that carries meaning but is entirely absent from `sr_transcript`.

## Insufficient evidence
The capture provides only the raw HTML and the transcript — it does **not**
resolve computed CSS. So if the technique implies content injected via a CSS
`::before`/`::after` `content:` rule, or text hidden by a **class-based**
`display:none` (where the rule lives in a stylesheet, not inline in
`element_html`), the proof is not in these three fields. In that case return
`insufficient_evidence` and say the injected/hidden text is not visible in the
raw HTML or the transcript. Do **not** guess at CSS you cannot see.

## Pass criteria
- All meaningful context is in the DOM and reflected in `sr_transcript` (the
  contextual phrase is actually announced).

## Examples
- INACCESSIBLE: `<a>Read more <span style="display:none"> about football</span></a>`
  → the hidden span's text is in `element_html`, but `sr_transcript` says only
  "link, Read more".
- INSUFFICIENT: the technique implies a `::after { content:"Pizza" }` rule — no
  "Pizza" appears in `element_html` or `sr_transcript`, so the injected text
  cannot be confirmed from this capture.
