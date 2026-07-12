"""Assemble the prompt from selected skills + evidence and call the LLM."""

from __future__ import annotations

from typing import List, Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from .evidence import Evidence
from .schema import Prediction
from .skills import Skill

BASE_SYSTEM_INSTRUCTIONS = """You are a strict WCAG 2.2 Level A and AA accessibility classifier.

You are given ONE captured DOM element and exactly THREE pieces of evidence:
  1. SOURCE HTML — the element's own raw HTML,
  2. PARENT CONTEXT HTML — the raw HTML of its parent, and
  3. SCREEN READER — the virtual screen-reader transcript for the element (the
     ordered phrases announced when walking through it; for a table this is the
     cell-by-cell walk, for a list the item-by-item reading).
There is no ARIA snapshot, no axe-core output, and no separate structural
metadata — reason ONLY from these fields. ARIA/live-region semantics (role,
aria-live, aria-atomic) and native elements like <output>/<progress> are part of
the SOURCE/PARENT HTML — read them there. The static transcript (#3) never fires
a live-region announcement, so silence in it is not, by itself, proof of a
status-message failure.

For status-message (WCAG 4.1.3) elements ONLY, a fourth field may be present:
  4. STATUS MESSAGE ANNOUNCEMENT — the result of an interaction probe that
     updated the status region and recorded whether the reader announced it.
     Here, SILENCE IS MEANINGFUL: if the region was updated but nothing was
     announced, the status is not conveyed without focus (a 4.1.3 failure); an
     announced "polite:/assertive: …" is a pass. This field is absent for
     non-status elements.

Below are the ONLY WCAG checks ("skills") relevant to this element. Evaluate the
element against these skills and nothing else. Each skill tells you which of the
three fields carries the proof and what pattern indicates a violation.

DECISION RULES
- Classify "inaccessible" if at least one skill's violation criteria are clearly
  met. Put the success-criterion number (e.g. "1.3.1") as a key in `reason` with a
  concise justification that cites the specific evidence field.
- Classify "accessible" only if the element satisfies the applied skills' pass
  criteria.
- Classify "insufficient_evidence" if the proof a skill needs is simply not
  present in these three fields (e.g. content injected via CSS `content:` that
  never appears in the HTML or the transcript) — do NOT guess. Explain what was
  missing.
- Read the raw markup directly (tags, attributes such as alt/scope/headers/role,
  nesting) rather than trusting any single word in the transcript. When judging
  grouping/heading/list/table defects, inspect the PARENT CONTEXT HTML, not just
  the element in isolation.
- Set `confidence` (0.0-1.0) and put a short quote from the deciding evidence in
  `evidence_citation`.

APPLICABLE SKILLS FOR THIS ELEMENT:
"""


def build_messages(ev: Evidence, skills: Sequence[Skill]) -> List:
    """Compose the system + human messages for one element."""
    skill_blocks = "\n\n".join(skill.prompt_block() for skill in skills)
    system = BASE_SYSTEM_INSTRUCTIONS + skill_blocks
    return [
        SystemMessage(content=system),
        HumanMessage(content=ev.block),
    ]


def classify(structured_llm, ev: Evidence, skills: Sequence[Skill]) -> Prediction:
    """Run the structured LLM call and stamp the applied skill ids."""
    messages = build_messages(ev, skills)
    prediction: Prediction = structured_llm.invoke(messages)
    prediction.applied_skills = [s.id for s in skills]
    return prediction
