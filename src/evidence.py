"""Build a compact, LLM-friendly evidence block from one dataset row.

This is the highest-leverage part of the pipeline: the legacy classifier only
saw 4 fields, so it was blind to the signals that actually prove 1.3.1
violations. Here we surface the rich capture columns — the ARIA snapshot
(``ax_subtree``), the full reading order, table cell-walk / header announcements,
and axe-core's automated findings — formatted so the model can cite them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, List, Mapping

# Tags whose captured element is a generic container: the real violation lives
# somewhere inside, so container rows fan out to all structural skills.
CONTAINER_TAGS = {"main", "body", "section", "div", "article", "form", "nav"}


def clean_html(html: Any) -> str:
    """Clean up mangled HTML for better LLM comprehension.

    Ported verbatim from the legacy ``testing.py`` so behaviour is unchanged.
    """
    if not isinstance(html, str) or html == "nan":
        return "No HTML context provided"

    html = re.sub(r'\s*data-scan-id="[^"]*"', "", html)
    html = re.sub(r'\s*data-parent-scan-id="[^"]*"', "", html)
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


def _format_css_generated(raw: str) -> str:
    """Render captured ::before/::after injected text (absent from the DOM)."""
    if not raw:
        return "(none captured)"
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not items:
        return "(none — no CSS ::before/::after text is injected on this element)"
    lines = []
    for item in items:
        selector = item.get("selector", "?")
        pseudo = item.get("pseudo", "")
        content = item.get("content", "")
        lines.append(f'    - {selector} ::{pseudo} injects text: "{content}"')
    return "\n".join(lines)


def _format_hidden(raw: str) -> str:
    """Render text removed from the a11y tree via computed display/visibility."""
    if not raw:
        return "(none captured)"
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not items:
        return "(none — no text is hidden via computed display:none / visibility:hidden)"
    lines = []
    for item in items:
        selector = item.get("selector", "?")
        method = item.get("method", "")
        text = item.get("text", "")
        lines.append(f'    - {selector} [{method}] hides text: "{text}"')
    return "\n".join(lines)


def _format_cell_structure(raw: str) -> str:
    """Render the raw <th>/<td> tag + scope/headers/id per cell, row by row.

    This is a deliberate cross-check against ``ax_subtree``: the computed
    accessibility tree reflects the browser's best-effort header-inference
    algorithm, which will confidently assign a columnheader/rowheader role to a
    <th> even when it has no `scope` — masking a defect (e.g. a data value
    mistakenly marked up as <th>) that the raw tag/attribute never hides.
    """
    if not raw:
        return "(not a table / not captured)"
    try:
        rows = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not rows:
        return "(not a table / not captured)"
    lines = []
    for i, row in enumerate(rows, start=1):
        cells = []
        for cell in row:
            tag = cell.get("tag", "?")
            scope = cell.get("scope")
            headers = cell.get("headers")
            if tag == "th":
                attr = f"scope={scope}" if scope else "NO-SCOPE"
            else:
                attr = f"headers={headers}" if headers else "no-headers-attr"
            cells.append(f'{tag}[{attr}]"{cell.get("text", "")}"')
        lines.append(f"    row {i}: " + " ".join(cells))
    return "\n".join(lines)


def _format_axe(raw: str) -> str:
    """Summarise an axe-core violations JSON blob into id/impact/help lines."""
    if not raw:
        return "(none reported by axe-core)"
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not items:
        return "(none reported by axe-core)"
    lines = []
    for item in items:
        rule_id = item.get("id", "?")
        impact = item.get("impact", "?")
        help_text = item.get("help", "")
        lines.append(f"    - {rule_id} (impact={impact}): {help_text}")
    return "\n".join(lines)


@dataclass
class Evidence:
    """Structured, pre-formatted evidence for one element plus routing hints."""

    element_type: str
    element_tag: str
    ax_role: str
    ax_name: str
    ax_level: str
    is_table: bool
    is_container: bool
    axe_ids: List[str]
    block: str  # the rendered text handed to the LLM


def _collect_axe_ids(*raws: str) -> List[str]:
    ids: List[str] = []
    for raw in raws:
        if not raw:
            continue
        try:
            for item in json.loads(raw):
                rule = str(item.get("id", "")).lower()
                if rule and rule not in ids:
                    ids.append(rule)
        except (json.JSONDecodeError, TypeError):
            continue
    return ids


def build(row: Mapping[str, Any]) -> Evidence:
    """Render one dataset row into an :class:`Evidence` object."""
    element_type = _val(row, "element_type")
    element_tag = _val(row, "element_tag").lower()
    ax_role = _val(row, "ax_role").lower()
    ax_name = _val(row, "ax_name")
    ax_level = _val(row, "ax_level")

    is_table = element_tag == "table" or ax_role in {"table", "grid"} or element_type == "table"
    is_container = element_tag in CONTAINER_TAGS

    axe_raw = _val(row, "axe_violations")
    axe131_raw = _val(row, "axe_wcag131_violations")
    axe_ids = _collect_axe_ids(axe_raw, axe131_raw)

    parts: List[str] = []
    parts.append("## ELEMENT UNDER TEST")
    parts.append(f"- element_type: {element_type or '(unknown)'}")
    parts.append(f"- tag: <{element_tag or '?'}>")
    parts.append(f"- accessibility role: {ax_role or '(none)'}")
    if ax_name:
        parts.append(f"- accessible name: {ax_name}")
    if ax_level:
        parts.append(f"- level: {ax_level}")

    parts.append("\n## SOURCE HTML")
    parts.append(clean_html(row.get("element_html_raw")))
    parts.append("\n## PARENT CONTEXT HTML")
    parts.append(clean_html(row.get("parent_html")))

    parts.append("\n## CSS-INJECTED CONTENT (::before / ::after — NOT in the DOM or a11y tree)")
    parts.append(_format_css_generated(_val(row, "css_generated_content")))
    parts.append("\n## CONTENT HIDDEN via computed CSS (display:none / visibility:hidden)")
    parts.append(_format_hidden(_val(row, "hidden_content")))

    parts.append("\n## SCREEN READER — transcript (element scope)")
    parts.append(_format_phrases(_val(row, "sr_transcript")))
    parts.append("\n## SCREEN READER — full reading order (page)")
    parts.append(_format_phrases(_val(row, "sr_reading_order")))

    if is_table:
        parts.append("\n## TABLE — cell walk (matrix navigation)")
        parts.append(_format_phrases(_val(row, "sr_cell_walk")))
        parts.append("\n## TABLE — headers announced per row")
        parts.append(_format_phrases(_val(row, "sr_headers_announced")))
        parts.append(
            "\n## TABLE — raw markup per cell (tag + scope/headers/id — "
            "do NOT rely on the ARIA snapshot's inferred roles alone; a <th> "
            "with NO-SCOPE can still be assigned a plausible-looking "
            "columnheader/rowheader role by the browser's best-effort guess)"
        )
        parts.append(_format_cell_structure(_val(row, "table_cell_structure")))

    ax_subtree = _val(row, "ax_subtree")
    parts.append("\n## ARIA snapshot (accessibility tree)")
    parts.append(ax_subtree or "(not captured)")

    parts.append("\n## Automated findings (axe-core)")
    parts.append("  All violations:")
    parts.append(_format_axe(axe_raw))
    if axe131_raw and axe131_raw != "[]":
        parts.append("  WCAG 1.3.1-tagged violations:")
        parts.append(_format_axe(axe131_raw))

    return Evidence(
        element_type=element_type,
        element_tag=element_tag,
        ax_role=ax_role,
        ax_name=ax_name,
        ax_level=ax_level,
        is_table=is_table,
        is_container=is_container,
        axe_ids=axe_ids,
        block="\n".join(parts),
    )
