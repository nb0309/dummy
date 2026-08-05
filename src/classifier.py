"""Assemble the prompt from selected skills + evidence and call the LLM."""

from __future__ import annotations

from typing import List, Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from .evidence import Evidence
from .schema import Prediction
from .skills import Skill

BASE_SYSTEM_INSTRUCTIONS = """You are a strict WCAG 2.2 Level A and AA accessibility classifier.

You are given ONE captured DOM element and THREE standard pieces of evidence:
  1. SOURCE HTML — the element's own raw HTML,
  2. PARENT CONTEXT HTML — the raw HTML of its parent, and
  3. SCREEN READER — the virtual screen-reader transcript for the element (the
     ordered phrases announced when walking through it; for a table this is the
     cell-by-cell walk, for a list the item-by-item reading).
There is no ARIA snapshot, no axe-core output, and no separate structural
metadata — reason ONLY from the sections you are actually given. ARIA/live-region
semantics (role, aria-live, aria-atomic) and native elements like
<output>/<progress> are part of the SOURCE/PARENT HTML — read them there. The
static transcript (#3) never fires a live-region announcement, so silence in it is
not, by itself, proof of a status-message failure.

Some criteria cannot be judged from static markup at all — whether focus can
escape, what an interaction changes, what context surrounds a link. For those, the
capture runs a PROBE and its result appears as one or more ADDITIONAL sections
after the three above (STATUS MESSAGE ANNOUNCEMENT, ROLE / STATE / VALUE, LABELS /
INSTRUCTIONS, FOCUS ORDER, LINK PURPOSE, HEADINGS AND LABELS, READING ORDER,
KEYBOARD TRAP, ON FOCUS, ON INPUT). A probe section is present only when that probe
ran, and when present it is the PRIMARY evidence for its criterion: it observes the
live page, so it outranks anything you infer from the static HTML. Each section
carries its own reading instructions and an explicit note on what it does and does
not settle — follow them.

One of those readings is easy to get backwards, so it is stated here too: in the
STATUS MESSAGE ANNOUNCEMENT section (WCAG 4.1.3), SILENCE IS MEANINGFUL. If the
region was updated but nothing was announced, the status is not conveyed without
focus (a failure); an announced "polite:/assertive: …" is a pass.

Below are the ONLY WCAG checks ("skills") relevant to this element. Evaluate the
element against these skills and nothing else. Each skill tells you which field
carries the proof and what pattern indicates a violation. Where a skill hands a
question to a neighbouring criterion, respect that boundary: note the observation
if it is useful, but do not emit a `reason` key for a criterion this element's
skills do not own.

DECISION RULES
- Classify "inaccessible" if at least one skill's violation criteria are clearly
  met. Put the success-criterion number (e.g. "1.3.1") as a key in `reason` with a
  concise justification that cites the specific evidence field.
- Classify "accessible" only if the element satisfies the applied skills' pass
  criteria.
- Classify "insufficient_evidence" if the proof a skill needs is simply not
  present in the sections you were given (e.g. content injected via CSS `content:`
  that never appears in the HTML or the transcript) — do NOT guess. Explain what
  was missing.
- Read the raw markup directly (tags, attributes such as alt/scope/headers/role,
  nesting) rather than trusting any single word in the transcript. When judging
  grouping/heading/list/table defects, inspect the PARENT CONTEXT HTML, not just
  the element in isolation.
- Set `confidence` (0.0-1.0) and put a short quote from the deciding evidence in
  `evidence_citation`.

APPLICABLE SKILLS FOR THIS ELEMENT:
"""


PRIMARY_HEADER = """
--- PRIMARY CRITERION ---
This capture was MADE to adjudicate the criterion below: its probe was run against
the live page and its section in the evidence is the decisive one. Answer this
criterion first and explicitly. Returning "accessible" while its probe section
reports the failing observation is the single most common way to get this wrong.
"""

SECONDARY_HEADER = """
--- ALSO APPLICABLE ---
These matched on the element's tag rather than on a probe. They are real checks
and any one of them can make this element inaccessible on its own, but none of
them is what this capture was aimed at. Do not let them crowd out the criterion
above.
"""


def build_messages(
    ev: Evidence,
    skills: Sequence[Skill],
    secondary: Sequence[Skill] | None = None,
) -> List:
    """Compose the system + human messages for one element.

    Called either as ``build_messages(ev, primary, secondary)`` — the two-tier
    form the router produces — or as ``build_messages(ev, skills)``, in which case
    every skill is rendered in one undifferentiated block as before.
    """
    if secondary is None:
        system = BASE_SYSTEM_INSTRUCTIONS + "\n\n".join(
            skill.prompt_block() for skill in skills
        )
    else:
        sections = []
        if skills:
            sections.append(
                PRIMARY_HEADER
                + "\n\n".join(skill.prompt_block() for skill in skills)
            )
        if secondary:
            sections.append(
                SECONDARY_HEADER
                + "\n\n".join(skill.prompt_block() for skill in secondary)
            )
        system = BASE_SYSTEM_INSTRUCTIONS + "\n".join(sections)
    return [
        SystemMessage(content=system),
        HumanMessage(content=ev.block),
    ]


def classify(
    structured_llm,
    ev: Evidence,
    skills: Sequence[Skill],
    secondary: Sequence[Skill] | None = None,
) -> Prediction:
    """Run the structured LLM call and stamp the applied skill ids."""
    messages = build_messages(ev, skills, secondary)
    prediction: Prediction = structured_llm.invoke(messages)
    prediction.applied_skills = [s.id for s in skills] + [s.id for s in (secondary or [])]
    return prediction
