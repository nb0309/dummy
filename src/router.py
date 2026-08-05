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

That column test does more than exclude, though, and :func:`partition` is where
the rest of it is used. A satisfied ``requires_column`` identifies the criterion
the capture was actually *made* for — the probe ran, so somebody asked this
question of this page. Tag matching cannot make that distinction, and left flat
it buries the answer: a ``<body>`` row captured under ``--sc 1.3.3`` matched nine
skills, of which the sensory-characteristics rubric holding the decisive probe
was one, and the row was returned as accessible with no reason at all. So the
selection is ordered and split rather than merely filtered.
"""

from __future__ import annotations

from typing import List, Mapping, Tuple

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


# How many tag-only skills to keep alongside a primary one. A page captured for a
# named criterion does not stop being able to fail others, so the secondary set is
# trimmed rather than dropped — but nine rubrics for one element is how the
# decisive one gets lost.
#
# Set against what a <body> row actually matches: four distinct criteria (1.3.1,
# 1.4.1, 4.1.2, 4.1.3), six of them 1.3.1 rubrics. Five is the smallest cap that,
# combined with `_spread`, cannot silently discard a whole criterion there — a
# tighter one cut 1.4.1 off the colour-alone fixture, which is the criterion that
# page is about. Trimming duplicates within a criterion is safe; trimming the last
# skill of a criterion is a verdict, and not one this function should be making.
_SECONDARY_CAP = 5


def _spread(skills: List[Skill]) -> List[Skill]:
    """Reorder so the first N skills cover as many distinct criteria as possible.

    Only matters when the list is about to be capped. Skills load in path order,
    which puts all six 1.3.1 structural rubrics before anything else, so a plain
    truncation keeps three checks of one criterion and discards every other
    criterion the element matched — on the colour-alone fixture that dropped
    1.4.1, the criterion most likely to have something to say. Taking one skill
    per criterion before a second from any of them keeps the trim from being a
    decision about *which criterion* to look at.
    """
    by_criterion: dict = {}
    for skill in skills:
        by_criterion.setdefault(skill.sc, []).append(skill)
    spread: List[Skill] = []
    while by_criterion:
        for sc in list(by_criterion):
            spread.append(by_criterion[sc].pop(0))
            if not by_criterion[sc]:
                del by_criterion[sc]
    return spread


def partition(
    ev: Evidence,
    row: Mapping[str, object] | None = None,
) -> Tuple[List[Skill], List[Skill]]:
    """Split this element's skills into (primary, secondary).

    **Primary** — the skill declares ``requires_column`` and this row carries that
    data. The probe ran, so this is the criterion the capture was made to
    adjudicate, and its evidence section is the decisive one.

    **Secondary** — matched on tag alone. Still applicable (a page captured for
    2.4.3 can also have an unlabelled table), and still able to return
    ``inaccessible`` on its own, but capped when a primary exists.

    A skill whose ``requires_column`` is declared but NOT satisfied is excluded
    from both: that is the original narrowing and it is unchanged.
    """
    selected = orchestrator.route(ev.element_tag)

    primary: List[Skill] = []
    secondary: List[Skill] = []
    for skill in selected:
        required = skill.applies_when.get("requires_column", [])
        if not required:
            secondary.append(skill)
        elif _has_columns(row, required):
            primary.append(skill)
        # else: declared a column it does not have -> not judgeable, drop it.

    if primary:
        secondary = _spread(secondary)[:_SECONDARY_CAP]
    # Never leave a row with nothing to judge it by: if the narrowing removed
    # everything, fall back to the tag-matched set.
    if not primary and not secondary:
        secondary = selected
    return primary, secondary


def select(
    ev: Evidence,
    row: Mapping[str, object] | None = None,
    mode: str | None = None,
) -> List[Skill]:
    """Return the skills to apply to this element, primary criterion first.

    Thin wrapper over :func:`partition` for callers that only need the flat list
    (``--dry-run`` coverage reporting, the ``AppliedSkills`` output column).

    ``mode`` is accepted for backwards compatibility and ignored.
    """
    primary, secondary = partition(ev, row)
    return primary + secondary
