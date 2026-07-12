"""Build a compact, LLM-friendly evidence block from one dataset row.

The capture is deliberately minimal: each row carries only three model inputs —
the element's HTML, its parent's HTML, and the screen-reader transcript. This
module renders those into the text block handed to the LLM, and parses the
element's outermost tag so the orchestrator can route it to a skill.

Status-message (WCAG 4.1.3) rows carry one extra field,
``sr_status_announcement``: the result of an interaction probe that updated the
live region and recorded what the reader announced. It is rendered as its own
section only when present (empty for every non-status row).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, List, Mapping

from .orchestrator import parse_root_tag

# Tags whose captured element is a generic container: the real violation lives
# somewhere inside, so container rows fan out to the structural skills.
CONTAINER_TAGS = {"main", "body", "section", "div", "article", "form", "nav"}


def clean_html(html: Any) -> str:
    """Clean up mangled HTML for better LLM comprehension.

    Ported verbatim from the legacy ``testing.py`` so behaviour is unchanged.
    """
    if not isinstance(html, str) or html == "nan":
        return "No HTML context provided"

    html = re.sub(r'\s*data-scan-id="[^"]*"', "", html)
    html = re.sub(r'\s*data-parent-scan-id="[^"]*"', "", html)
    html = re.sub(r'\s*data-sample-id="[^"]*"', "", html)
    html = html.replace('=""', "=__EMPTY_QUOTE__")
    html = re.sub(r'="" ([^"<>]+?)""=""', r'="\1"', html)
    html = re.sub(r'""', r'"', html)
    html = html.replace("=__EMPTY_QUOTE__", '=""')
    html = re.sub(r"\n\s*\n\s*\n", "\n\n", html)
    return html.strip()


def _val(row: Mapping[str, Any], key: str) -> str:
    """Return a trimmed string for a cell, mapping NaN/None to ''."""
    value = row.get(key)
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _phrases(raw: str) -> List[str]:
    """Parse a JSON array column (e.g. sr_transcript) into a list of phrases."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(p) for p in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return [raw]


def _format_phrases(raw: str) -> str:
    phrases = _phrases(raw)
    return " | ".join(phrases) if phrases else "(none)"


@dataclass
class Evidence:
    """Structured, pre-formatted evidence for one element plus routing hint."""

    element_tag: str
    is_container: bool
    block: str  # the rendered text handed to the LLM


def build(row: Mapping[str, Any]) -> Evidence:
    """Render one dataset row into an :class:`Evidence` object."""
    element_html = row.get("element_html")
    element_tag = parse_root_tag(element_html if isinstance(element_html, str) else "")
    is_container = element_tag in CONTAINER_TAGS

    parts: List[str] = []
    parts.append("## ELEMENT UNDER TEST")
    parts.append(f"- tag: <{element_tag or '?'}>")

    parts.append("\n## SOURCE HTML (the element under test)")
    parts.append(clean_html(element_html))

    parts.append(
        "\n## PARENT CONTEXT HTML (the element's parent — use this to check whether "
        "a REQUIRED ancestor/sibling structure exists around the element, e.g. a "
        "<ul>/<ol>/<dl> for an orphan check, or a <fieldset> around form controls)"
    )
    parts.append(clean_html(row.get("parent_html")))

    parts.append(
        "\n## SCREEN READER — transcript (what the virtual screen reader announces "
        "walking through this element, in order)"
    )
    parts.append(_format_phrases(_val(row, "sr_transcript")))

    # 4.1.3 interaction probe: only present for status-message rows. An empty
    # string means the row was not a status message (not probed) -> no section.
    status_raw = _val(row, "sr_status_announcement")
    if status_raw:
        announced = _phrases(status_raw)
        parts.append(
            "\n## STATUS MESSAGE ANNOUNCEMENT — 4.1.3 interaction probe (the reader "
            "was started, then the status region was updated to simulate a live "
            "change; this observes whether the update is announced WITHOUT moving "
            "focus)"
        )
        if announced:
            parts.append(
                "The update WAS announced without moving focus:\n"
                + "\n".join(f"  - {p}" for p in announced)
            )
        else:
            parts.append(
                "(SILENT — the region was updated but the reader announced NOTHING, "
                "so assistive-tech users are not notified. This is the decisive "
                "4.1.3 failure signal — UNLESS the region is a value-driven role "
                "such as progressbar, which this text-mutation probe does not "
                "exercise; in that case fall back to the SOURCE HTML markup.)"
            )

    return Evidence(
        element_tag=element_tag,
        is_container=is_container,
        block="\n".join(parts),
    )
