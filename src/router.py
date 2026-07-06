"""Select the applicable skills for a captured element.

Routing is deterministic and cheap, and now depends on a single signal: the
outermost tag parsed from the element's HTML (see :mod:`src.orchestrator`). The
element's tag is matched against each skill's ``applies_when.element_tag`` list;
container/unknown tags fall back to the full structural 1.3.1 set.
"""

from __future__ import annotations

from typing import List, Mapping

from . import orchestrator
from .evidence import Evidence
from .skills import Skill


def select(
    ev: Evidence,
    row: Mapping[str, object] | None = None,
    mode: str | None = None,
) -> List[Skill]:
    """Return the skills to apply to this element, based on its HTML tag.

    ``row``/``mode`` are accepted for backwards compatibility and ignored.
    """
    return orchestrator.route(ev.element_tag)
