"""Select the applicable skills for a captured element.

Routing is deterministic and cheap, and depends mainly on a single signal: the
outermost tag parsed from the element's HTML (see :mod:`src.orchestrator`). The
element's tag is matched against each skill's ``applies_when.element_tag`` list;
container/unknown tags fall back to the full structural 1.3.1 set.

A skill may additionally declare ``applies_when.requires_column``, naming probe
columns it cannot be judged without. That exists because tag alone is not always
enough to identify a sample: the page-level 2.4.3 sample is ``<body>``, which is
indistinguishable from the generic fallback block every other suite captures.
Without this narrowing, the focus-order rubric would be attached to every
container row in every dataset, with no focus data to judge it against.
"""

from __future__ import annotations

from typing import List, Mapping

from . import orchestrator
from .evidence import Evidence
from .skills import Skill


def _has_columns(row: Mapping[str, object] | None, columns: List[str]) -> bool:
    """True if every named column is present and non-empty in ``row``."""
    if not columns:
        return True
    if row is None:
        return False
    for column in columns:
        value = row.get(column)
        if value is None:
            return False
        text = str(value).strip()
        if not text or text.lower() in ("nan", "null", "[]", "{}"):
            return False
    return True


def select(
    ev: Evidence,
    row: Mapping[str, object] | None = None,
    mode: str | None = None,
) -> List[Skill]:
    """Return the skills to apply to this element, based on its HTML tag.

    Skills declaring ``applies_when.requires_column`` are dropped when this row
    has no data in those columns. Skills without the key are unaffected.

    ``mode`` is accepted for backwards compatibility and ignored.
    """
    selected = orchestrator.route(ev.element_tag)
    narrowed = [
        s
        for s in selected
        if _has_columns(row, s.applies_when.get("requires_column", []))
    ]
    # Never leave a row with nothing to judge it by: if the column narrowing
    # removed everything, fall back to the tag-matched set.
    return narrowed or selected
