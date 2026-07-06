"""Route an element to its WCAG skills using only its HTML tag.

The capture now yields just three inputs — element HTML, parent HTML, and the
screen-reader transcript — so the old role/axe-based routing is gone. Instead
this orchestrator reads the **outermost tag of the element's HTML** and matches
it against each skill's ``applies_when.element_tag`` list. Generic containers
(and unknown tags) fall back to the full structural 1.3.1 rubric set so no
element is ever left without a skill.
"""

from __future__ import annotations

import re
from typing import Any, List

from .skills import Skill, load_skills

# First tag name in a chunk of HTML, e.g. "<table …>" -> "table".
_TAG_RE = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9]*)")


def parse_root_tag(element_html: Any) -> str:
    """Return the lowercased outermost tag of ``element_html`` (or "")."""
    if not isinstance(element_html, str):
        return ""
    match = _TAG_RE.search(element_html)
    return match.group(1).lower() if match else ""


def route(element_tag: str) -> List[Skill]:
    """Return the skills whose ``applies_when.element_tag`` covers this tag.

    Falls back to every 1.3.1 structural skill for a container/unknown tag, so a
    ``<div>``/``<main>`` wrapper (or an untagged blob) still gets a rubric.
    """
    skills = load_skills()
    tag = (element_tag or "").lower()
    selected = [s for s in skills if tag in s.applies_when.get("element_tag", [])]
    if not selected:
        selected = [s for s in skills if s.sc == "1.3.1"]
    return selected
