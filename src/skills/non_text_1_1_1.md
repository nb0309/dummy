---
sc: "1.1.1"
technique: "non-text-content"
title: "Non-text content (images, image buttons, spacers)"
applies_when:
  element_tag: [img, input, svg, object, area, a, button]
  ax_role: [img, image, button, link, graphics-document, presentation, none]
axe_ids: [image-alt, input-image-alt, role-img-alt, area-alt, svg-img-alt, object-alt]
signals:
  - field: element_html_raw
    look_for: "img/input[type=image] with no alt, alt='', a filename as alt, or a generic/wrong alt"
  - field: sr_transcript
    look_for: "a raw filename read aloud, a bare 'image'/'graphic', or the control announced with no accessible name"
  - field: ax_name
    look_for: "empty or filename-like accessible name for a meaningful image"
---
## Violation criteria (1.1.1 Non-text Content)
Flag `inaccessible` under `1.1.1` when a meaningful, informative image or image
control lacks an adequate text alternative:
- `<img>` with **no** `alt` attribute, or `alt=""` on an image that conveys
  information or is a brand/logo (the `src` filename such as `bbc-blocks-dark.png`
  is a strong hint that it is meaningful).
- `alt` set to the **file name** (e.g. `alt="bbc-blocks-dark.png"`) or to a
  generic/placeholder value (`alt="click"`, `alt="image"`) that does not convey
  the content or purpose.
- `alt` that is **wrong/misleading** for the image (e.g. `alt="Twitter"` on a BBC
  logo).
- `<input type="image">` (image button) with missing or empty `alt`; these are
  interactive controls and require a text alternative describing the action.
- A **spacer / layout image** that is announced instead of hidden — a purely
  decorative image should be removed from the a11y tree (`alt=""` /
  `role="presentation"`), not read out.

## Pass criteria
- Meaningful image has a concise, accurate `alt` (e.g. `alt="BBC Logo"`) and the
  screen reader announces that name.
- A genuinely decorative image uses `alt=""` or `role="presentation"` and is
  **silently skipped** by the screen reader — silence here is correct, not a
  violation.

## Insufficient evidence
If whether the image is decorative vs meaningful cannot be determined from the
capture (no `src`, no surrounding context), return `insufficient_evidence`.

## Examples
- INACCESSIBLE: `<img src="…/bbc-blocks-dark.png">` (no alt) → SR reads only "image".
- INACCESSIBLE: `<input type="image" src="…/submit.png">` (no alt).
- ACCESSIBLE: `<img src="…/bbc-blocks-dark.png" alt="BBC Logo">` → "image, BBC Logo".
- ACCESSIBLE: `<img role="presentation" src="…/decoration.png">` → skipped (silence).
