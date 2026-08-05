---
sc: "1.4.1"
technique: "use-of-colour"
title: "Colour as the only visual means of conveying information"
applies_when:
  element_tag: [main, body, section, div, article, nav, p, span, a, ul, ol, li, table]
signals:
  - field: sr_computed_style
    look_for: "a link whose colour, weight, decoration and font all match the text it sits inside — no non-colour cue distinguishes it; or two sets of items differing only in computed colour"
  - field: element_html
    look_for: "prose that identifies items by colour ('the green ones are safe'), or class names carrying meaning (.safe/.poisonous, .error/.ok) with no text equivalent on the item itself"
  - field: sr_transcript
    look_for: "items announced identically to one another even though the prose says they differ — the distinction never reaches the reader"
---
## Violation criteria (1.4.1 Use of Colour)
Flag `inaccessible` under `1.4.1` when colour is the ONLY visual means of conveying
information, indicating an action, prompting a response, or distinguishing an
element:
- A **link inside a block of text** that is distinguished from the surrounding
  prose by colour alone. Read `sr_computed_style`: if the link's
  `text-decoration-line` is `none` AND its `font-weight`/`font-style`/`font-size`
  match the surrounding text, then colour (or nothing at all) is the only thing
  setting it apart. A link that differs from its context in **no** visual property
  is the same failure in its most complete form.
- **Meaning carried by a colour class with no text equivalent** — items marked
  `.safe`/`.poisonous`, `.valid`/`.error`, `.available`/`.sold-out` where the item's
  own text does not say which it is, so a reader hears an undifferentiated list.
- **Prose that identifies content by colour** ("the green mushrooms are OK to eat",
  "required fields are shown in red") where the items themselves carry no
  non-colour indicator. Note the boundary: if the sentence identifies a component
  by a sensory characteristic *in an instruction*, 1.3.3 owns that; 1.4.1 owns the
  case where colour encodes a state or category across a set of items.

## Reading the evidence
`sr_computed_style` is measured from the rendered page and outranks any guess from
a class name. **Do not infer a failure from a class name alone** — `.unobvious-link`
and `.poisonous` are author labels, not measurements, and a class named for a
defect proves nothing about how the page actually renders. If that section is
absent and the CSS is not in the markup, the distinction cannot be seen from this
capture: return `insufficient_evidence`.

## Pass criteria
- A link in prose carries a non-colour cue — an underline
  (`text-decoration-line: underline`), a bold weight, an icon, or a border — in
  addition to any colour difference.
- Colour-coded items also carry the distinction in text, in an icon with a text
  alternative, or in an announced state.
- Colour is used **redundantly**, alongside a cue that survives being read aloud.

## Examples
- INACCESSIBLE: `<p>Find out more about <a href="…">Doctor Who</a></p>` where the
  computed style shows the `<a>` at the same colour and weight as the `<p>` with
  `text-decoration-line: none` — nothing marks it as a link.
- INACCESSIBLE: `<li class="safe">Chanterelle</li>` / `<li class="poisonous">Amanita</li>`
  after prose saying the green ones are safe — the transcript announces both as
  plain list items.
- ACCESSIBLE: an in-text link that computes to `text-decoration-line: underline`,
  or renders bold against non-bold prose.
