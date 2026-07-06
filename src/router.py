"""Select the applicable skills for a captured element.

Routing is deterministic and cheap: match each skill's ``applies_when``
predicates against the element's tag/role, and boost skills whose ``axe_ids``
appear in the row's axe-core findings. The union is returned.

By default routing is *blind* — it never consults the ground-truth ``wcag_sc``
column (that field is unavailable in real usage). Set ``ROUTING_MODE=oracle``
(env / :data:`src.config.ROUTING_MODE`) to additionally narrow candidates to the
row's declared success criterion, for skill-development and debugging only.
"""

from __future__ import annotations

from typing import List, Mapping

from . import config
from .evidence import Evidence
from .skills import Skill, load_skills


def _matches_predicates(skill: Skill, ev: Evidence) -> bool:
    """True if the skill's applies_when matches the element's tag or role."""
    tags = skill.applies_when.get("element_tag", [])
    roles = skill.applies_when.get("ax_role", [])
    if ev.element_tag and ev.element_tag in tags:
        return True
    if ev.ax_role and ev.ax_role in roles:
        return True
    return False


def _matches_axe(skill: Skill, ev: Evidence) -> bool:
    """True if any axe rule reported on the row is claimed by the skill."""
    return any(axe_id in skill.axe_ids for axe_id in ev.axe_ids)


def select(
    ev: Evidence,
    row: Mapping[str, object] | None = None,
    mode: str | None = None,
) -> List[Skill]:
    """Return the skills to apply to this element, most-specific-ish first.

    ``row`` is only needed for ``oracle`` mode (to read ``wcag_sc``).
    """
    mode = (mode or config.ROUTING_MODE or "blind").lower()
    skills = load_skills()

    selected: List[Skill] = []
    for skill in skills:
        if _matches_predicates(skill, ev) or _matches_axe(skill, ev):
            selected.append(skill)

    # Fallback: never leave an element with no skill. Generic containers get the
    # full structural 1.3.1 set; anything else gets every skill so the model at
    # least has a rubric to reason against.
    if not selected:
        if ev.is_container:
            selected = [s for s in skills if s.sc == "1.3.1"]
        else:
            selected = list(skills)

    if mode == "oracle" and row is not None:
        sc = str(row.get("wcag_sc", "")).strip()
        narrowed = [s for s in selected if s.sc == sc]
        if narrowed:
            selected = narrowed

    # Stable, de-duplicated order: axe-boosted skills first, then predicate hits.
    axe_boosted = [s for s in selected if _matches_axe(s, ev)]
    rest = [s for s in selected if s not in axe_boosted]
    ordered: List[Skill] = []
    for skill in axe_boosted + rest:
        if skill not in ordered:
            ordered.append(skill)
    return ordered
