"""Assemble the prompt from selected skills + evidence and call the LLM."""

from __future__ import annotations

from typing import List, Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from .evidence import Evidence
from .schema import Prediction
from .skills import Skill

BASE_SYSTEM_INSTRUCTIONS = """You are a strict WCAG 2.2 Level A accessibility classifier.

You are given ONE captured DOM element: its tag/role, source HTML, parent context,
a virtual screen-reader transcript and full reading order, (for tables) a matrix
cell-walk and per-row header announcements, an ARIA snapshot of the accessibility
tree, and axe-core's automated findings.

Below are the ONLY WCAG checks ("skills") relevant to this element. Evaluate the
element against these skills and nothing else. Each skill tells you which evidence
field carries the proof and what pattern indicates a violation.

DECISION RULES
- Classify "inaccessible" if at least one skill's violation criteria are clearly
  met. Put the success-criterion number (e.g. "1.3.1") as a key in `reason` with a
  concise justification that cites the specific evidence field.
- Classify "accessible" only if the element satisfies the applied skills' pass
  criteria.
- Classify "insufficient_evidence" if the proof a skill needs is not present in the
  capture (e.g. content injected via CSS `content:` that is absent from the HTML) —
  do NOT guess. Explain what was missing.
- Trust the ARIA snapshot (`ax_subtree`) and `ax_role` over quirks in the raw
  transcript wording. When judging grouping/heading/list defects, inspect the
  PARENT context, not just the element in isolation.
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
