---
sc: "2.4.4"
technique: "link-purpose-in-context"
title: "Link purpose cannot be determined from the link text or its context"
applies_when:
  element_tag: [body]
  requires_column: [sr_link_purpose]
signals:
  - field: sr_link_purpose
    look_for: "PRIMARY. Every link with what the reader ANNOUNCES for it, its `href`, how its name is supplied (`ariaLabel`/`labelledBy`/`title`/`imgAlt`), and its `context`: `sentence`, `block`, `tableHeaders`, `describedBy`. Read the announced name FIRST and ask whether it names a destination. Only if it does not, fall to the context — and then ask whether that context names the destination, not merely whether it exists."
  - field: sr_transcript
    look_for: "SECONDARY. The reading-order walk over the page. Use it to confirm what a link's neighbours actually say when read in flow, and to see whether several ambiguous links land close enough together to be confused with one another."
  - field: element_html
    look_for: "CORROBORATION. The page markup behind a link: whether an `aria-label` overrides the visible text, whether an image inside the link carries the alt that becomes the name, whether a `title` is the only thing distinguishing two links."
  - field: parent_html
    look_for: "the <html> element, for the <head> — the page <title> establishes what 'here' and 'this page' would refer to, and whether a link's destination is the page it is already on."
---
## Violation criteria (2.4.4 Link Purpose (In Context))
**2.4.4 Link Purpose (In Context) is Level A and is in scope for this page.**

A link passes when its purpose can be determined **either**:

1. from the **announced name alone**, **or**
2. from the announced name **together with its programmatically determined
   context**.

Two consequences follow, and most mistakes on this criterion come from missing one
of them:

- **A generic name is not automatically a failure.** "Read more" at the end of a
  paragraph that says what it is about is a *pass*. The name being weak only moves
  the question to the context; it does not settle it.
- **A specific name is not automatically a pass.** A unique, confident-sounding
  name that describes something other than where the link goes fails, and no
  duplicate-detection will ever catch it.

## What counts as context — a closed list
WCAG limits programmatically determined link context to what a reader can offer
alongside the link: text in the **same sentence, paragraph, list item or table
cell**, the **header cell** of a table cell containing the link, and text wired to
it by **`aria-describedby`** (or the link's own `title`). The evidence gives you
exactly these, per link.

Nothing else qualifies. In particular:

- **A heading further up the page does NOT count.** It is not offered with the
  link, and a user arriving from a links list never hears it. If a link is only
  intelligible because of a heading above it, that is a failure, not a pass. (The
  2.4.6 rotor view records a `underHeading` field for its own purposes — it is not
  context for this criterion.)
- **A neighbouring link does not count.** "Print" and "Save" as a pair do not
  explain each other.
- **Visual proximity does not count.** Text sitting next to the link in the layout
  but in a different block is not programmatically related to it.

Flag `inaccessible` under `2.4.4` when any of the following holds:

- **A generic name with no context that names the destination.** "Click here",
  "Read more", "More", "Details" where the sentence/block around it does not say
  what is at the other end — or where there is no enclosing block at all.
- **One announced name, several destinations, and the contexts do not tell them
  apart** — the surrounding text repeats too, or the links sit bare with no
  context each.
- **A name that misdescribes its destination** — announced "Download the 2024
  price list", `href` pointing at a contact form. Specific and wrong.
- **A bare URL as the name** where nothing around it says what the address is,
  so the reader spells out a path the user has to decode.
- **A `title` doing the whole job.** `title` is included above because readers may
  announce it, but many do not and it is unavailable to touch and keyboard users;
  if the name plus the sentence/block are ambiguous and only `title` resolves them,
  that is a failure.

## Pass criteria
- The announced name names the destination on its own.
- The name is generic **but** its sentence, block, table headers or
  `aria-describedby` text names the destination.
- The same name is used repeatedly for the **same** `href` — a "Contact us" link in
  the header, body and footer is ordinary, useful markup, and repetition alone is
  never the defect.
- The same name is used for different destinations **but** each sits in its own
  context that names where it goes — four "Read more" links, each ending its own
  article's paragraph, pass this criterion.
- An `aria-label` or `aria-labelledby` supplies a fuller name than the visible text
  ("Read more about changes to passport fees" over "Read more"). The announced form
  is what this criterion judges.
- An image link whose `alt` names the destination.

## Insufficient evidence
- A name whose descriptiveness depends on domain knowledge the capture cannot
  supply — a product code, a form reference, a case number. Do not flag specialist
  vocabulary merely for being unfamiliar.
- An `href` that is an opaque identifier (`/p/8813224`, a query-string-only URL)
  where the name is plausible: you cannot confirm the name misdescribes the
  destination without fetching it. Say so rather than guessing.
- The probe reports `truncated`: a name that looks unique in the list may repeat
  further down, so do not conclude uniqueness from a partial list.
- A page with no links at all.

## Scope boundary
Four neighbours are close, and this skill judges only whether a link's **purpose**
is determinable:
- **4.1.2** owns whether the link has an accessible name **at all**. A link that
  announces nothing is 4.1.2's finding; a link that announces something useless is
  this one's. The evidence calls nameless links out explicitly — do not convert
  them into 2.4.4 findings.
- **1.1.1** owns a missing `alt` on an image inside a link. The consequence (the
  reader falling back to the URL) shows up here, but the defect is the missing
  text alternative.
- **2.4.6** owns whether **headings and labels** describe their topic or purpose.
  Links are not headings or labels — link purpose is entirely this skill's, and
  the 2.4.6 rotor view is explicitly told not to adjudicate it.
- **2.4.9 Link Purpose (Link Only)** is the AAA criterion requiring the name to
  work with **no** context at all. It is **out of scope**. When identical link
  text is separated only by its context, say so and pass — do not quietly apply
  the AAA standard.

## Examples
- INACCESSIBLE: four links announced `link, Read more`, each alone in its own
  `<p>` with no other text, going to `/news/passport-fees`, `/news/test-centres`,
  `/news/winter-fuel`, `/news/tax-deadline` → generic name, no context, four
  destinations.
- INACCESSIBLE: `link, Click here` whose sentence reads "To apply, click here." →
  the context is present but names no destination.
- INACCESSIBLE: `link, More information` sitting bare in a `<div>` under a heading
  "Council tax discounts" → the heading is not programmatically determined context.
- INACCESSIBLE: `link, https://example.gov/svc/2024/ct-red/apply.html` announced as
  a bare address, with no sentence around it.
- INACCESSIBLE: `link, Download the price list` whose `href` is `/contact-us` →
  specific, unique and untrue of its destination.
- ACCESSIBLE: `link, Read more` whose sentence is "Standard adult passport renewal
  fees rise from April. Read more about passport fee changes." → generic name,
  context names the destination.
- ACCESSIBLE: four `link, Read more` entries, each ending a paragraph naming its
  own article → context distinguishes all four. (This fails 2.4.9, which is AAA
  and out of scope — say so and pass.)
- ACCESSIBLE: `link, Contact us` in header, body and footer, every one pointing at
  `/contact` → repeated name, one destination.
- ACCESSIBLE: `link, Renew, Passport, Adult` in a table cell whose row header is
  "Passport" and column header is "Adult" → the headers complete the purpose.
- ACCESSIBLE: `<a aria-label="Read more about winter fuel payments">Read more</a>`
  → the announced name carries the purpose on its own.
