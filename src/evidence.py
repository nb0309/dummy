"""Build a compact, LLM-friendly evidence block from one dataset row.

The capture is deliberately minimal: each row carries only three model inputs —
the element's HTML, its parent's HTML, and the screen-reader transcript. This
module renders those into the text block handed to the LLM, and parses the
element's outermost tag so the orchestrator can route it to a skill.

Status-message (WCAG 4.1.3) rows carry one extra field,
``sr_status_announcement``: the result of an interaction probe that updated the
live region and recorded what the reader announced. It is rendered as its own
section only when present (empty for every non-status row).

Role/state/value (WCAG 4.1.2) rows carry one extra field,
``sr_role_state_value``: the result of an interaction probe that clicked the
control once and recorded what was announced, and the raw HTML, before and
after. Also rendered as its own section only when present.

Form (WCAG 3.3.2) rows carry one extra field, ``sr_label_instruction``: one
entry per form field, each recording what was announced before and after a value
was entered. Rendered as its own section only when present, with the
label/instruction segments that were LOST on input called out explicitly.

Page (WCAG 2.4.3) rows carry one extra field, ``sr_focus_order``: the Tab sweep,
one stop per focusable component with its announced phrase, position and source
index. Rendered as a per-stop table plus the derived comparisons (tab order vs
visual order vs source order, obscured stops, revealed content not reached).
Those comparisons are deliberately framed as observations rather than a verdict:
whether an order preserves *meaning* is the judgement handed to the model.

Page (WCAG 2.4.4) rows carry ``sr_link_purpose``: every link with what the reader
announces, its destination, and its *programmatically determined link context* —
the sentence, block, table header cells and aria-describedby text WCAG limits that
context to. Rendered per link, with the objective observations (one name serving
several destinations, generic action/position text, bare URLs) each PAIRED with the
context that is allowed to rescue it. That pairing is the whole section: the same
observation is a failure or a pass depending on it, and reporting it without the
context — which is what the 2.4.6 rotor view can only do — decides the criterion by
the wrong standard.

Page (WCAG 2.4.6) rows carry ``sr_headings_labels``: the rotor view — every
heading, control and link as announced, out of document order, with the context a
rotor list strips away. Rendered as three lists plus the objectively checkable
observations (duplicates, link text with several destinations); genericness and
accuracy are left to the model for the same reason.

Page (WCAG 1.3.2) rows carry ``sr_reading_order``: the reader's cursor walk with a
position per step, which is what makes the reading sequence and the visual
sequence comparable. Rendered as the walk plus a comparison against BOTH visual
orderings — row-major and column-major — since a genuine multi-column layout
matches only the latter. Whether the sequence carries meaning at all is the gate
the model applies.

Page (WCAG 2.1.2) rows carry ``sr_keyboard_trap``: the escape ladder — a forward Tab
sweep, then Shift+Tab, then the Escape key. Rendered as the sweep, how it ended, and
each recovery attempt in turn. The framing is the inverse of the other page sections:
containing focus is *correct* for a modal dialog, so a detected loop is not the
finding — a loop with no way out is, which is why only the recovery phases settle it.

Page (WCAG 3.2.1) rows carry ``sr_focus_context``: each focusable component was focused
in turn and what changed was recorded. The signals are rendered in two groups, because
they are not equally decidable — focus moving, the page navigating, a window opening
and a form submitting are changes of context by definition, while a DOM mutation may be
a hint appearing (ordinary) or a dialog opening (a failure). The mutation group is
therefore rendered *with the markup of what appeared* and left to the model.

Page (WCAG 3.2.2) rows carry ``sr_input_context``: the same measurement taken after
*changing each component's setting* rather than after focusing it, so the two columns
share their record shape and their rendering helpers. One thing is different, and it
decides the criterion: 3.2.2 permits a change of context on input when the user was
advised of it beforehand, so each component also carries the text that might be that
advisory. A change of context alone is therefore not a verdict here — the pairing of
the change with the absence of a warning is.

Page (WCAG 1.3.3) rows carry ``sr_sensory_reference``: candidate sensory phrases found
in the page's prose, each resolved against measurement where measurement is possible.
This is the only criterion here whose defect lives in *language* rather than in
behaviour or structure, so the section is framed differently from all the others — a
lexicon hit is a **candidate**, never a finding. Two of the six characteristics
(position, colour) carry resolved evidence; the other four are text matches the model
must weigh unaided.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
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


# Capture stores parent.outerHTML, which always nests the sample. The prompt
# already has SOURCE HTML, so repeating that subtree is wasted tokens. Fact
# finders still receive the stored full parent_html; this marker is prompt-only.
_ELEMENT_HOLE = "<!-- ELEMENT UNDER TEST: see SOURCE HTML above -->"
_MISSING_HTML = "No HTML context provided"


def _parent_context_html(element_html: Any, parent_html: Any) -> str | None:
    """Parent markup with the sample removed, or None if it adds nothing.

    Replaces the first copy of the cleaned element inside the cleaned parent
    with ``_ELEMENT_HOLE``. Omits the section when parent is missing or is
    identical to the element (there is no surrounding context to show).
    """
    cleaned_element = clean_html(element_html)
    cleaned_parent = clean_html(parent_html)
    if not cleaned_parent or cleaned_parent == _MISSING_HTML:
        return None
    if cleaned_element == _MISSING_HTML:
        return cleaned_parent
    if cleaned_parent == cleaned_element:
        return None
    if cleaned_element and cleaned_element in cleaned_parent:
        return cleaned_parent.replace(cleaned_element, _ELEMENT_HOLE, 1)
    return cleaned_parent


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


def _role_state_value(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_role_state_value JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) and "before" in parsed and "after" in parsed else None


def _label_instruction(raw: str) -> List[Mapping[str, Any]]:
    """Parse the sr_label_instruction JSON array column, or [] if absent."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [e for e in parsed if isinstance(e, dict) and "before" in e and "after" in e]


def _focus_order(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_focus_order JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("stops"), list):
        return None
    return parsed


def _usable_rect(rect: Any) -> bool:
    """True when ``rect`` is a real layout box, not a missing or 0x0 placeholder.

    Component hosts with ``display: contents`` used to serialize as ``{x:0,y:0,w:0,h:0}``.
    Ranking those at the origin threw off every visual-order comparison.
    """
    if not isinstance(rect, dict):
        return False
    try:
        width = float(rect.get("w") or 0)
        height = float(rect.get("h") or 0)
    except (TypeError, ValueError):
        return False
    return width > 0 or height > 0


def _format_position(rect: Any) -> str:
    if not _usable_rect(rect):
        return "unknown"
    return f"{rect.get('x', '?')},{rect.get('y', '?')}"


def _visual_rank(
    stops: List[Mapping[str, Any]],
    band: int = 24,
    major: str = "row",
    id_key: str = "stop",
) -> List[int]:
    """Item numbers sorted into a visual reading order.

    ``id_key`` names the field holding each item's sequence number — ``"stop"`` for
    the 2.4.3 focus sweep (the default), ``"step"`` for the 1.3.2 reading walk.

    ``major="row"`` (the default, and what 2.4.3 uses) reads top to bottom, then
    left to right. ``y`` is bucketed into bands so items sitting on the same visual
    row (a nav bar, a pair of dialog buttons) are ordered by ``x`` rather than by a
    few pixels of baseline difference.

    ``major="column"`` reads down each column, then across — the order a genuine
    multi-column layout is *supposed* to produce. 1.3.2 compares against both,
    because a two-column article matches only the column-major ordering and
    checking row-major alone would report it as an inversion.

    Stops with no layout box are omitted rather than ranked at (0, 0).
    """
    positioned = [s for s in stops if _usable_rect(s.get("rect"))]

    def key(stop: Mapping[str, Any]) -> tuple:
        rect = stop.get("rect") or {}
        y = int(rect.get("y") or 0)
        x = int(rect.get("x") or 0)
        if major == "column":
            return (x // band, y)
        return (y // band, x)

    return [int(s.get(id_key) or 0) for s in sorted(positioned, key=key)]


def _focus_order_findings(stops: List[Mapping[str, Any]]) -> List[str]:
    """Derive the near-mechanical focus-order signals a person would eyeball.

    Deliberately does NOT decide the verdict — 2.4.3 turns on whether the order
    preserves *meaning*, which is the judgement handed to the model. These are the
    observations that judgement should start from.
    """
    findings: List[str] = []
    tab_all = [int(s.get("stop") or 0) for s in stops]
    positioned = [s for s in stops if _usable_rect(s.get("rect"))]
    tab_visual = [int(s.get("stop") or 0) for s in positioned]

    visual = _visual_rank(positioned)
    if visual != tab_visual:
        findings.append(
            f"Tab order does NOT match visual reading order.\n"
            f"    tab order    : {tab_visual}\n"
            f"    visual order : {visual}   (top-to-bottom, then left-to-right)"
        )

    unknown = len(stops) - len(positioned)
    if unknown:
        findings.append(
            f"{unknown} stop(s) have no layout box (collapsed, display:contents, or "
            f"unrendered) and were omitted from the visual-order comparison rather "
            f"than ranked at (0,0)."
        )

    dom_order = [
        int(s.get("stop") or 0)
        for s in sorted(stops, key=lambda s: int(s.get("domIndex") or 0))
    ]
    if dom_order != tab_all:
        findings.append(
            f"Tab order does NOT match source (DOM) order.\n"
            f"    tab order    : {tab_all}\n"
            f"    source order : {dom_order}"
        )

    positive = [
        f"stop {s.get('stop')} (tabindex={s.get('tabindex')})"
        for s in stops
        if str(s.get("tabindex") or "").strip().lstrip("+").isdigit()
        and int(str(s.get("tabindex")).strip()) > 0
    ]
    if positive:
        findings.append(
            "Positive tabindex in use, which imposes an order of its own: "
            + ", ".join(positive)
        )

    obscured = [str(s.get("stop")) for s in stops if s.get("obscured")]
    if obscured:
        findings.append(
            f"Focus lands on OBSCURED content (something is painted on top of it) at "
            f"stop(s) {', '.join(obscured)} — the user cannot see or click what is "
            f"focused. Consecutive obscured stops are the signature of an open modal "
            f"with a live page behind it."
        )

    # Did focus move into the content a control claims to reveal?
    for index, stop in enumerate(stops):
        rng = stop.get("controlsRange")
        if not (isinstance(rng, list) and len(rng) == 2):
            continue
        nxt = stops[index + 1] if index + 1 < len(stops) else None
        if nxt is None:
            findings.append(
                f"Stop {stop.get('stop')} controls \"{stop.get('controls')}\" but is the "
                f"last stop, so focus never reaches the content it reveals."
            )
            continue
        nxt_dom = int(nxt.get("domIndex") or -1)
        if not (rng[0] <= nxt_dom <= rng[1]):
            landed = [
                s.get("stop")
                for s in stops
                if rng[0] <= int(s.get("domIndex") or -1) <= rng[1]
            ]
            where = f"reached later at stop(s) {landed}" if landed else "never reached"
            findings.append(
                f"Stop {stop.get('stop')} reveals \"{stop.get('controls')}\", but the next "
                f"stop is OUTSIDE that content — it is {where}. The content the control "
                f"revealed is not where the keyboard arrives."
            )

    return findings


def _activation_lines(activation: Mapping[str, Any], initial_stops: int) -> List[str]:
    """What each in-page control did to the tab sequence when activated.

    Framed around one comparison, because it is the whole reason this pass exists:
    a page whose initial sweep found ONE stop is not a page with one focusable
    control, it is a page whose controls are behind an interaction — and the
    "fewer than two stops is not a sequence" abstention is exactly wrong there.
    The lead line says so outright when that is the situation.

    ``focusMovedIntoRevealed`` is a set-membership test and is stated as a fact.
    Everything downstream of it — whether arriving at revealed content later in the
    order is confusing, whether a lightbox ought to hold focus at all — is left to
    the model, as with every other 2.4.3 observation.
    """
    triggers = [t for t in activation.get("triggers") or [] if isinstance(t, dict)]
    if not triggers:
        return []

    lines = [
        "\n## FOCUS ORDER AFTER ACTIVATION — 2.4.3 (each in-page control was "
        "clicked, then the page was swept again; only controls that actually "
        "brought new components into the tab sequence are listed)"
    ]
    if initial_stops < 2:
        lines.append(
            f"The sweep above found {initial_stops} stop(s), but this page's other "
            f"components are behind an interaction rather than absent. Judge the "
            f"focus order from what follows — do NOT return insufficient_evidence "
            f"on the grounds that the initial sweep was too short."
        )

    for entry in triggers:
        trigger = entry.get("trigger") or {}
        revealed = [r for r in entry.get("revealed") or [] if isinstance(r, dict)]
        focus_after = entry.get("focusAfter") or {}
        lines.append(
            f'\nActivating <{trigger.get("tag")}> "{trigger.get("text")}" '
            f'(dom {trigger.get("domIndex")}) brought {len(revealed)} component(s) '
            f"into the tab sequence:"
        )
        for item in revealed:
            lines.append(
                f'    dom {item.get("domIndex")}: <{item.get("tag")}> "{item.get("text")}"'
            )

        if entry.get("focusMovedIntoRevealed"):
            lines.append(
                f'    Focus MOVED INTO the revealed content — it landed on '
                f'"{focus_after.get("phrase", "")}", which is one of the components '
                f"above. The user arrives where the new content is."
            )
        elif focus_after:
            lines.append(
                f'    Focus did NOT move into the revealed content — it stayed on '
                f'"{focus_after.get("phrase", "")}" (dom {focus_after.get("domIndex")}), '
                f"which is the trigger or something else outside what just appeared. "
                f"The content is on screen; the keyboard is not in it."
            )
        else:
            lines.append(
                "    Focus is on NOTHING in the document after activation — it left "
                "the page entirely, so the revealed content is not where the keyboard "
                "is either."
            )

        stops_after = [s for s in entry.get("stopsAfter") or [] if isinstance(s, dict)]
        if stops_after:
            # Deliberately NOT a fresh sweep from the top of the page. The browser
            # keeps its sequential-navigation starting point at the control that
            # was just activated, so these are the stops a user actually walks
            # next, which is the question this section exists to answer. Labelled
            # as such, because read as a whole-page order it would look like the
            # trigger had vanished from the sequence.
            lines.append("    Tab order CONTINUING from the trigger:")
            for stop in stops_after:
                lines.append(
                    f'      {stop.get("stop")}. dom {stop.get("domIndex")}  '
                    f'"{stop.get("phrase", "")}"'
                )
            revealed_indexes = {r.get("domIndex") for r in revealed}
            reached = [s for s in stops_after if s.get("domIndex") in revealed_indexes]
            if not reached:
                lines.append(
                    "      NONE of the revealed components appear in the tab order at "
                    "all — the content cannot be reached by keyboard from here."
                )
            elif stops_after.index(reached[0]):
                lines.append(
                    f"      The revealed content is first reached at stop "
                    f'{reached[0].get("stop")}, after '
                    f"{stops_after.index(reached[0])} unrelated stop(s)."
                )
        if entry.get("completeAfter") and stops_after:
            lines.append(
                "      The sweep then left the document, so nothing holds focus while "
                "this content is open."
            )

    return lines


def _reading_order(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_reading_order JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("steps"), list):
        return None
    return parsed


def _frames(raw: Any) -> List[Mapping[str, Any]] | None:
    """Parse sr_frames (list of iframe records), or None if absent."""
    parsed: Any = raw
    if parsed is None:
        return None
    # pandas empty cells become float NaN; older datasets have no column at all.
    if isinstance(parsed, float) and parsed != parsed:
        return None
    if isinstance(parsed, str):
        text = parsed.strip()
        if not text or text.lower() == "nan":
            return None
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(parsed, list) or not parsed:
        return None
    return [item for item in parsed if isinstance(item, dict)]


def _frame_lines(frames: List[Mapping[str, Any]]) -> List[str]:
    """Coverage of nested browsing contexts — inspected vs skipped, never silent."""
    skipped = sum(1 for frame in frames if frame.get("status") == "skipped")
    inspected = len(frames) - skipped
    lines = [
        "\n## FRAMES — nested documents (payment widgets, chat, embedded players). "
        "SKIPPED means the contents were NOT tested. Do not treat the host page as "
        "covering a skipped frame."
    ]
    lines.append(
        f"{len(frames)} frame(s) on this page: {inspected} inspected, {skipped} skipped."
    )
    why = {
        "cross-origin": "cross-origin — the capture cannot read another origin's DOM",
        "evaluate-failed": "the nested document could not be evaluated",
        "empty": "the nested document was empty",
    }
    for frame in frames:
        tag = frame.get("tag") or "iframe"
        src = frame.get("src") or frame.get("url") or "(no src)"
        title = frame.get("title") or frame.get("name") or "(untitled)"
        if frame.get("status") == "skipped":
            reason = why.get(
                str(frame.get("skipped") or ""),
                str(frame.get("skipped") or "unreadable"),
            )
            lines.append(f'- SKIPPED <{tag}> src="{src}" title="{title}"')
            lines.append(
                f"    {reason}. Contents were not sampled, not walked, not judged."
            )
            continue
        inner = frame.get("inner") if isinstance(frame.get("inner"), dict) else {}
        bits = []
        for key, label in (
            ("forms", "form(s)"),
            ("inputs", "control(s)"),
            ("media", "media"),
            ("headings", "heading(s)"),
            ("links", "link(s)"),
        ):
            count = inner.get(key) or 0
            if count:
                bits.append(f"{count} {label}")
        sampled = frame.get("sampled") or 0
        detail = ", ".join(bits) if bits else "no controls/media/headings/links counted"
        preview = inner.get("textPreview")
        lines.append(f'- INSPECTED <{tag}> src="{src}" title="{title}"')
        lines.append(
            f"    {detail}. sampled {sampled} element(s) inside."
            + (f' Preview: "{preview}"' if preview else "")
        )
    return lines


def _content_steps(steps: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """The steps worth comparing positions for.

    The walk emits two steps per element — its role ("paragraph") then its text —
    sharing a ``domIndex``, plus "end of …" boundary phrases. It also passes
    through containers like ``<body>``, whose rect spans the whole page and would
    distort any ranking. So: drop boundaries, keep leaves *or* text nodes (a
    component like ``<button><svg></svg>Go</button>`` is not a leaf, but the text
    still has a position), skip empty 0x0 boxes, and collapse each element to one
    step.

    Which of the two to keep matters. Both carry the same position, so ordering is
    unaffected either way — but the skill asks the model to *read the announced
    sequence* and judge whether it still makes sense, and a list of bare
    "paragraph, paragraph, paragraph" cannot be read. Prefer the text-bearing step
    (``nodeType`` 3) so the rendered walk shows the actual content.
    """
    best: dict = {}
    order: List[int] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if re.match(r"^end of\b", str(step.get("phrase") or ""), re.IGNORECASE):
            continue
        # Text is the content even when the parent is a component with children
        # (icon + label). Empty 0x0 boxes are not a position.
        is_text = step.get("nodeType") == 3
        if not (step.get("isLeaf") or is_text):
            continue
        if not _usable_rect(step.get("rect")):
            continue
        dom = step.get("domIndex")
        if dom is None or dom < 0:
            continue
        if dom not in best:
            best[dom] = step
            order.append(dom)
        elif step.get("nodeType") == 3 and best[dom].get("nodeType") != 3:
            # Text beats the bare role announcement for the same element.
            best[dom] = step
    return [best[d] for d in order]


def _reading_order_findings(steps: List[Mapping[str, Any]]) -> List[str]:
    """Compare the reading sequence against both visual orderings.

    Reports which ordering the reading order matches, if either. Matching *either*
    is normally fine — a multi-column layout legitimately matches only the
    column-major one. Matching NEITHER is the finding. Whether the sequence
    actually carries meaning is not decided here; that is the model's gate.
    """
    findings: List[str] = []
    if len(steps) < 2:
        return findings

    reading = [int(s.get("step") or 0) for s in steps]
    row_major = _visual_rank(steps, major="row", id_key="step")
    column_major = _visual_rank(steps, major="column", id_key="step")

    if reading == row_major:
        findings.append(
            "Reading order matches the row-major visual order (top to bottom, then "
            "left to right) — the sequence a reader hears is the sequence on screen."
        )
    elif reading == column_major:
        findings.append(
            "Reading order matches the COLUMN-major visual order (down each column, "
            "then across). That is what a genuine multi-column layout should do, and "
            "is NOT a defect — it only looks like one against a row-major sweep."
        )
    else:
        out_of_place = [
            f"step {r} (announced position {i + 1}, row-major position "
            f"{row_major.index(r) + 1})"
            for i, r in enumerate(reading)
            if row_major[i] != r
        ]
        findings.append(
            "Reading order matches NEITHER visual ordering:\n"
            f"    reading order : {reading}\n"
            f"    row-major     : {row_major}\n"
            f"    column-major  : {column_major}\n"
            "    The sequence exposed to a screen reader is not the sequence on "
            "screen, under either way of reading the layout."
        )
        if out_of_place:
            findings.append("Out of place vs row-major: " + "; ".join(out_of_place[:8]))

    return findings


def _keyboard_trap(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_keyboard_trap JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("stops"), list):
        return None
    return parsed


def _advisory_text(region: Mapping[str, Any]) -> List[str]:
    """Every piece of text that could be advising the user how to get out."""
    candidates = [str(region.get("advisory") or "")]
    candidates += [str(t) for t in region.get("describedBy") or []]
    return [t.strip() for t in candidates if t.strip()]


def _keyboard_trap_findings(data: Mapping[str, Any]) -> List[str]:
    """Derive the escapability observations, resolution first.

    This one section departs from how the other page-level criteria are rendered,
    and deliberately. There, the mechanical signals are withheld from a verdict
    because the criterion turns on something no measurement reaches — whether an
    order preserves *meaning* (2.4.3), whether a heading is *descriptive* (2.4.6).
    Here the decisive question is "did any key move focus out", which is a
    measurement and nothing else, so it is stated outright and stated FIRST.

    The ordering is the point. A conforming modal dialog produces a loop, a blocked
    Shift+Tab, and an exit only on Escape — so a findings list in probe order opens
    with three alarming lines and buries the one that exonerates it. Leading with
    the resolution is what stops a correctly-built dialog reading as a trap.

    What is still left to the model is the genuinely semantic half: whether text
    beside a widget that keeps focus actually tells the user how to leave it.
    """
    findings: List[str] = []
    outcome = str(data.get("outcome") or "")
    stops = [s for s in data.get("stops", []) if isinstance(s, dict)]

    if outcome == "escaped":
        findings.append(
            f"Focus LEFT the page unaided after {len(stops)} stop(s) — Tab alone "
            f"walked every focusable component and then moved out of the document. "
            f"Nothing held focus, so there is no trap for 2.1.2 to be about."
        )
        return findings

    if outcome == "cap":
        findings.append(
            "The sweep hit its cap without either leaving the page or repeating a "
            "stop, so it never established whether focus can escape. A page with "
            "more focusable components than the cap looks exactly like this. Treat "
            "as INCONCLUSIVE, not as a trap."
        )
        return findings

    reverse = data.get("reverse") if isinstance(data.get("reverse"), dict) else {}
    escape = data.get("escape") if isinstance(data.get("escape"), dict) else None
    region = data.get("region") if isinstance(data.get("region"), dict) else None
    is_dialog = bool(
        region
        and (
            region.get("ariaModal")
            or str(region.get("role") or "") in ("dialog", "alertdialog")
        )
    )

    # ---- the resolution, before any of the detail that produced it -------------
    if reverse.get("exited") or (escape and escape.get("exited")):
        via = "Shift+Tab" if reverse.get("exited") else "the Escape key"
        findings.append(
            f"ESCAPABLE — focus was held, but {via} moved it back out. Focus "
            f"containment WITH a working exit is not a 2.1.2 failure"
            + (
                ', and for this role="dialog"/aria-modal region it is the REQUIRED '
                "pattern: a modal is supposed to keep focus while it is open"
                if is_dialog
                else ""
            )
            + ". Do not flag 2.1.2 for the hold described below — it is the expected "
            "behaviour of a component that can still be left."
        )
    else:
        findings.append(
            "NOT ESCAPABLE — focus was held and none of Tab, Shift+Tab or the Escape "
            "key moved it out. That is the 2.1.2 failure, unless the region advertises "
            "some other method (checked below)."
        )

    last = stops[-1] if stops else {}
    if outcome == "stalled":
        findings.append(
            f"Focus is PINNED on one control — stop {last.get('stop')}, "
            f"<{last.get('tag')}> \"{last.get('phrase', '')}\". Tab was pressed and "
            f"focus did not move at all. Two handlers produce this and the sweep cannot "
            f"tell them apart: a keydown handler calling preventDefault() on the Tab "
            f"key, or a focusin/blur handler pulling focus back to this control. Which "
            f"one is visible in the SOURCE/PARENT HTML."
        )
    elif outcome == "cycled":
        cycle = data.get("cycle") if isinstance(data.get("cycle"), dict) else {}
        # One entry per member, in loop order. Keyed off domIndex because the stop
        # that closed the loop is a SECOND visit to a member already listed.
        phrases = {s.get("domIndex"): str(s.get("phrase", "")) for s in reversed(stops)}
        looped = [f'"{phrases.get(dom, "(unnamed)")}"' for dom in cycle.get("members") or []]
        findings.append(
            f"Focus is HELD in a loop of {cycle.get('length', '?')} component(s): "
            f"{', '.join(looped) or '(unnamed)'}. From stop {cycle.get('startStop')} "
            f"onward Tab only revisits components it has already visited, so it does "
            f"not advance past them."
        )

    if reverse.get("exited"):
        target = reverse.get("exitedTo") or {}
        where = f' to "{target.get("phrase", "")}"' if target else " out of the page"
        findings.append(
            f"Shift+Tab DID move focus{where} after {reverse.get('presses')} press(es) "
            f"— the component can be left backwards with an unmodified key."
        )
    else:
        findings.append(
            f"Shift+Tab did not move focus out either ({reverse.get('presses')} "
            f"press(es)) — both unmodified Tab directions are held."
        )

    if escape:
        if escape.get("exited"):
            findings.append(
                "The ESCAPE key released focus"
                + (
                    " and the region it was held in is now gone"
                    if escape.get("regionHidden")
                    else " (the region is still on the page)"
                )
                + ' — focus moved to "'
                + str((escape.get("activeAfter") or {}).get("phrase", "(outside the page)"))
                + '". There IS a keyboard way out.'
            )
        else:
            findings.append(
                "The ESCAPE key did NOT release focus — after pressing it, and then "
                "Tab again, focus is still inside the same set of components."
            )

    if region:
        descriptor = f"<{region.get('tag')}"
        if region.get("role"):
            descriptor += f" role=\"{region.get('role')}\""
        if region.get("ariaModal"):
            descriptor += f" aria-modal=\"{region.get('ariaModal')}\""
        descriptor += ">"
        shortcuts = [s for s in region.get("keyshortcuts") or [] if s]
        advisory = _advisory_text(region)
        if shortcuts:
            findings.append(
                f"The region holding focus, {descriptor}, declares "
                f"aria-keyshortcuts=\"{', '.join(shortcuts)}\" — an explicitly "
                f"advertised way out, which this probe's fixed key ladder may not have "
                f"pressed."
            )
        if advisory:
            findings.append(
                f"Text inside/attached to {descriptor} that is not part of any control: "
                + " / ".join(f'"{t}"' for t in advisory)
                + ". Judge whether any of it tells the user how to move focus away."
            )
        elif not shortcuts:
            findings.append(
                f"The region holding focus, {descriptor}, carries NO non-control text "
                f"and no aria-keyshortcuts — nothing on the page advises the user how "
                f"to get out."
            )

    return findings


def _focus_context(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_focus_context JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("components"), list):
        return None
    return parsed


def _component_label(component: Mapping[str, Any]) -> str:
    """A short, readable identifier for one focusable component."""
    tag = component.get("tag") or "?"
    bits = [f"<{tag}>"]
    if component.get("role"):
        bits.append(f'role="{component["role"]}"')
    if component.get("id"):
        bits.append(f'#{component["id"]}')
    name = str(component.get("name") or "").strip()
    if name:
        bits.append(f'"{name}"')
    return " ".join(bits)


def _context_changes(entry: Mapping[str, Any]) -> List[str]:
    """The UNAMBIGUOUS changes of context recorded for one component.

    These four need no judgement: each one is a change of context by the definition in
    the SC itself. Kept separate from mutations for exactly that reason.
    """
    changes: List[str] = []
    if entry.get("navigatedTo"):
        changes.append(f"the page NAVIGATED to {entry['navigatedTo']}")
    for url in entry.get("opened") or []:
        changes.append(f'a NEW WINDOW was opened ({url or "no url"})')
    for form in entry.get("submitted") or []:
        changes.append(f"a FORM was SUBMITTED ({form})")
    if not entry.get("focusHeld") and not entry.get("navigatedTo"):
        moved = entry.get("focusMovedTo") or {}
        where = f'"{moved.get("phrase", "")}"' if moved.get("phrase") else "elsewhere"
        changes.append(f"FOCUS MOVED away, to {where}")
    return changes


def _mutation_lines(component: Mapping[str, Any]) -> List[str]:
    """The markup a focus event produced: what appeared, and what changed state.

    Rendered for EVERY component that mutated, not only the ambiguous ones. A dialog
    opening on focus also moves focus, which makes it an unambiguous failure — but
    reporting only "focus moved" would throw away the reason, and a modal opening reads
    very differently from a field quietly handing focus to its neighbour.
    """
    mutations = component.get("mutations") or {}
    lines: List[str] = []
    for markup in mutations.get("addedNodes") or []:
        lines.append(f"    appeared: {markup}")
    for target in mutations.get("attributeTargets") or []:
        if not isinstance(target, dict):
            continue
        descriptor = f"<{target.get('tag')}"
        if target.get("role"):
            descriptor += f' role="{target.get("role")}"'
        if target.get("ariaModal"):
            descriptor += f' aria-modal="{target.get("ariaModal")}"'
        if target.get("id"):
            descriptor += f' #{target.get("id")}'
        descriptor += ">"
        note = ""
        if str(target.get("role") or "") in ("dialog", "alertdialog") or target.get("ariaModal"):
            note = (
                "  <-- a DIALOG changed state. A dialog already in the DOM that merely "
                "becomes visible adds no node at all, so this attribute change is the "
                "whole signal; if it opened a modal, that is a change of context."
            )
        lines.append(f"    attribute \"{target.get('attribute')}\" changed on {descriptor}{note}")
    return lines


def _focus_context_findings(data: Mapping[str, Any]) -> List[str]:
    """Split the on-focus observations by how decidable they are.

    The mechanical half of 3.2.1 covers only the four changes in ``_context_changes``.
    A DOM mutation is deliberately NOT resolved here: revealing a hint and opening a
    dialog are the same measurement, and telling them apart means reading what
    appeared. So mutations are reported with their markup and handed over, and the
    lead finding does not pre-judge a mutation-only result.
    """
    findings: List[str] = []
    components = [c for c in data.get("components", []) if isinstance(c, dict)]
    if not components:
        return ["No focusable component was found on the page, so 3.2.1 has nothing to apply to."]

    offenders = [(c, _context_changes(c)) for c in components]
    offenders = [(c, ch) for c, ch in offenders if ch]
    mutators = [
        c
        for c in components
        if not _context_changes(c)
        and (
            (c.get("mutations") or {}).get("added")
            or (c.get("mutations") or {}).get("removed")
            or (c.get("mutations") or {}).get("attributes")
        )
    ]

    # ---- the resolution of the mechanical half, first ------------------------
    if offenders:
        findings.append(
            f"CONTEXT CHANGED ON FOCUS for {len(offenders)} of {len(components)} "
            f"component(s). Each change listed below is a change of context by "
            f"definition — not a judgement call — so this is a 3.2.1 failure."
        )
        for component, changes in offenders:
            findings.append(
                f"Focusing {_component_label(component.get('component') or {})}: "
                + "; ".join(changes)
            )
            supporting = _mutation_lines(component)
            if supporting:
                findings.append("    ...and the DOM changed at the same time:")
                findings.extend(supporting)
    else:
        findings.append(
            f"No component moved focus, navigated, opened a window or submitted a form "
            f"when focused ({len(components)} component(s) probed). None of the "
            f"unambiguous changes of context occurred."
        )

    # ---- the ambiguous half, reported and NOT resolved -----------------------
    for component in mutators:
        mutations = component.get("mutations") or {}
        label = _component_label(component.get("component") or {})
        findings.append(
            f"Focusing {label} changed the DOM but nothing else — focus stayed on it, "
            f"and the page did not navigate, open a window or submit. "
            f"{mutations.get('added', 0)} node(s) added, "
            f"{mutations.get('removed', 0)} removed, "
            f"{mutations.get('attributes', 0)} attribute change(s). This is the case "
            f"that needs judgement, from what actually appeared:"
        )
        findings.extend(_mutation_lines(component))

    if not offenders and not mutators:
        findings.append(
            "Nothing at all changed on any component's focus — no mutation, no "
            "attribute change, no navigation."
        )

    if data.get("truncated"):
        findings.append(
            "The probe stopped at its component cap, so not every focusable component "
            "on the page was tried. A clean result here does not cover the rest."
        )

    return findings


def _input_context(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_input_context JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("components"), list):
        return None
    return parsed


def _advisory_lines(entry: Mapping[str, Any]) -> List[str]:
    """The text that might be 3.2.2's required warning, in strength order.

    Not labelled as *the* warning, because whether wording actually advises anyone of
    a change of context is a judgement about language. The probe can only say what
    text is attached to the control and how firmly.
    """
    advisory = entry.get("advisory") or {}
    lines: List[str] = []
    for text in advisory.get("describedBy") or []:
        lines.append(
            f'    described by (announced with the control): "{text}"'
        )
    if advisory.get("precedingText"):
        lines.append(
            f'    text before it in its group: "{advisory["precedingText"]}"'
        )
    if not lines:
        lines.append(
            "    NO text is attached to this control and none precedes it in its "
            "group (its label aside, which names it rather than warning about it)."
        )
    return lines


def _input_context_findings(data: Mapping[str, Any]) -> List[str]:
    """Split the on-input observations the way 3.2.2 splits them.

    Structurally the same as the 3.2.1 findings, and reusing the same two helpers for
    the changes themselves — but the resolution is different in a way that is the
    whole criterion. On focus, an unambiguous change of context IS the failure. On
    input it is only half of one: the criterion permits it outright when the user was
    advised beforehand. So a change is always reported together with whatever text
    might be that advisory, and the lead never resolves a warned change on its own.
    """
    findings: List[str] = []
    components = [c for c in data.get("components", []) if isinstance(c, dict)]
    if not components:
        return [
            "No component with a changeable setting was found on the page, so 3.2.2 "
            "has nothing to apply to. (Buttons and links are deliberately not probed: "
            "activating one is a user REQUEST, which this criterion permits.)"
        ]

    offenders = [(c, _context_changes(c)) for c in components]
    offenders = [(c, ch) for c, ch in offenders if ch and not c.get("note")]
    mutators = [
        c
        for c in components
        if not _context_changes(c)
        and not c.get("note")
        and (
            (c.get("mutations") or {}).get("added")
            or (c.get("mutations") or {}).get("removed")
            or (c.get("mutations") or {}).get("attributes")
        )
    ]
    excluded = [c for c in components if c.get("note")]

    if offenders:
        warned = [c for c, _ in offenders if (c.get("advisory") or {}).get("hasText")]
        findings.append(
            f"CHANGING A SETTING CHANGED THE CONTEXT for {len(offenders)} of "
            f"{len(components)} component(s). Unlike 3.2.1 this is NOT yet a verdict: "
            f"3.2.2 permits it where the user was advised of the behaviour beforehand. "
            f"{len(warned)} of the {len(offenders)} carry text that could be that "
            f"advisory — read it and decide whether it actually warns of this."
        )
        for component, changes in offenders:
            findings.append(
                f"Changing {_component_label(component.get('component') or {})}: "
                + "; ".join(changes)
            )
            findings.extend(_advisory_lines(component))
            supporting = _mutation_lines(component)
            if supporting:
                findings.append("    ...and the DOM changed at the same time:")
                findings.extend(supporting)
    else:
        findings.append(
            f"No component navigated, opened a window, submitted a form or moved focus "
            f"when its setting was changed ({len(components)} component(s) probed). "
            f"None of the unambiguous changes of context occurred on input."
        )

    for component in mutators:
        mutations = component.get("mutations") or {}
        findings.append(
            f"Changing {_component_label(component.get('component') or {})} changed the "
            f"DOM but nothing else — focus stayed where it was, and the page did not "
            f"navigate, open a window or submit. {mutations.get('added', 0)} node(s) "
            f"added, {mutations.get('removed', 0)} removed, "
            f"{mutations.get('attributes', 0)} attribute change(s). Judge from what "
            f"appeared whether the page now means something different:"
        )
        findings.extend(_mutation_lines(component))

    for component in excluded:
        findings.append(
            f"{_component_label(component.get('component') or {})} could not be measured "
            f"for 3.2.2: {component.get('note')}. Do not read this as a pass or a fail "
            f"here — it is the other criterion's finding."
        )

    if data.get("truncated"):
        findings.append(
            "The probe stopped at its component cap, so not every settable component "
            "was tried. A clean result here does not cover the rest."
        )

    return findings


# Link text naming an ACTION or a POSITION rather than a destination — the classic
# F63/H30 list. Deliberately closed, and deliberately only an OBSERVATION: 2.4.4
# permits every one of these phrases when the surrounding context supplies the
# purpose, so "this says nothing on its own" is the finding and whether the context
# rescues it is the skill's judgement.
_GENERIC_LINK_TEXT = frozenset(
    {
        "click here", "click", "here", "read more", "more", "learn more",
        "find out more", "see more", "view more", "details", "more details",
        "more information", "more info", "info", "link", "this link", "this page",
        "this", "continue", "go", "start", "open", "view", "download", "next",
        "previous", "back", "full story", "read", "see", "apply",
    }
)

# A name the reader has to announce as a bare address — "https://…", "www.…", or a
# path like "/news/2024/passport-fees.html".
_URL_LIKE = re.compile(r"^(?:https?://|www\.|/[\w\-./%~]*$)", re.I)


def _link_purpose(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_link_purpose JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("links"), list):
        return None
    return parsed


def _announced_name(entry: Mapping[str, Any]) -> str:
    """The link's NAME as announced, with the reader's role word removed.

    The transcript phrase is "link, Read more"; 2.4.4 is about the name, so the
    leading role word goes. Only a leading "link"/"visited link" is stripped, and
    only up to the FIRST comma, so a name that itself contains commas survives.
    Falls back to the visible text when nothing was announced.
    """
    phrase = str(entry.get("phrase") or "").strip()
    if not phrase:
        return str(entry.get("text") or "").strip()
    head, sep, tail = phrase.partition(",")
    if sep and head.strip().casefold() in ("link", "visited link"):
        return tail.strip()
    # A phrase that is ONLY the role word is a link with NO accessible name --
    # not a link whose name happens to be "link". The difference decides which
    # criterion owns it: nameless is 4.1.2's, and treating it as generic text
    # would silently report it here instead.
    if phrase.strip().casefold() in ("link", "visited link"):
        return ""
    return phrase


def _context_text(entry: Mapping[str, Any]) -> str:
    """The strongest programmatically determined context this link has, or "".

    Ordered by how tightly WCAG binds it to the link: the sentence first, then the
    enclosing block, then a table's header cells, then aria-describedby. The first
    non-empty one is what the user would actually be given alongside the link.
    """
    context = entry.get("context")
    if not isinstance(context, dict):
        return ""
    for key in ("sentence", "block"):
        value = str(context.get(key) or "").strip()
        if value:
            return value
    headers = context.get("tableHeaders")
    if isinstance(headers, list) and headers:
        return " / ".join(str(h) for h in headers if h)
    return str(context.get("describedBy") or "").strip()


def _link_purpose_findings(links: List[Mapping[str, Any]]) -> List[str]:
    """Compute only the OBJECTIVE observations about link purpose.

    Three things are checkable without judgement: whether one announced name is
    used for more than one destination, whether a name is on the closed
    action/position list, and whether a name is a bare URL. None of them is a
    verdict — 2.4.4 is "In Context", so each observation is paired with the context
    that is allowed to rescue it, and the skill decides whether it does.
    """
    findings: List[str] = []

    groups: dict = {}
    for entry in links:
        name = _announced_name(entry)
        if name:
            groups.setdefault(name.casefold(), []).append(entry)

    # 1. One name, several destinations. The context check is the whole point: the
    #    same finding is a failure or a pass depending on it.
    for entries in groups.values():
        destinations = {str(e.get("href") or "") for e in entries}
        if len(entries) < 2 or len(destinations) < 2:
            continue
        display = _announced_name(entries[0])
        contexts = [_context_text(e) for e in entries]
        distinct = {c.casefold() for c in contexts if c}
        if all(contexts) and len(distinct) == len(entries):
            findings.append(
                f'"{display}" is announced {len(entries)} times for {len(destinations)} '
                f"different destinations, BUT each one sits in a DIFFERENT context "
                f"(listed per link above). 2.4.4 allows the context to be what "
                f"distinguishes them, so this is only a failure if those contexts do "
                f"not actually name where each link goes. Identical link text that IS "
                f"separated by context fails 2.4.9 Link Purpose (Link Only) — that is "
                f"Level AAA and out of scope here."
            )
        else:
            missing = [c for c in contexts if not c]
            why = (
                f"{len(missing)} of them have NO enclosing sentence, paragraph, list "
                f"item or table cell at all"
                if missing
                else "their contexts are identical too"
            )
            findings.append(
                f'"{display}" is announced {len(entries)} times for {len(destinations)} '
                f"different destinations ({', '.join(sorted(destinations))}), and the "
                f"context does not separate them — {why}. Nothing available to the user "
                f"tells these links apart."
            )

    # 2. Names that say nothing on their own, reported once per distinct name.
    for entries in groups.values():
        display = _announced_name(entries[0])
        flat = display.casefold().strip(" .!?…:,")
        contexts = [_context_text(e) for e in entries]
        count = f" (used {len(entries)} times)" if len(entries) > 1 else ""
        if flat in _GENERIC_LINK_TEXT:
            kind = "names an action or a position rather than a destination"
        elif _URL_LIKE.match(display):
            kind = "is a bare address, read out character by character"
        else:
            continue
        if all(contexts):
            findings.append(
                f'"{display}"{count} {kind}. It DOES have context (shown above) — judge '
                f"whether that context names the destination."
            )
        else:
            findings.append(
                f'"{display}"{count} {kind}, and has NO enclosing sentence, paragraph, '
                f"list item or table cell to fall back on. There is nothing but the "
                f"name, so the name has to carry the purpose by itself."
            )

    # 3. Links the reader announces with no name at all. Named here because it
    #    changes what the other observations mean, but it is not this criterion's
    #    finding to make -- see the scope note in the skill.
    nameless = [e for e in links if not _announced_name(e)]
    if nameless:
        hrefs = ", ".join(str(e.get("href") or "?") for e in nameless[:5])
        findings.append(
            f"{len(nameless)} link(s) announce NO name at all ({hrefs}). A link with no "
            f"accessible name is 4.1.2's finding (and 1.1.1's if it wraps an image with "
            f"no alt); note it, but do not report it under 2.4.4."
        )

    return findings


def _sensory_reference(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_sensory_reference JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("references"), list):
        return None
    return parsed


def _sensory_reference_findings(data: Mapping[str, Any]) -> List[str]:
    """Report each candidate sensory phrase with whatever corroborates it.

    Framed harder than any other section in this module, because the detector is a word
    lexicon and a word lexicon cannot tell an instruction from ordinary prose. "You have
    the right to appeal", "see below for our address" and "a large number of appeals"
    all match, and none of them is a 1.3.3 anything. So nothing here resolves to a
    verdict: the findings say what was matched, what measurement corroborates it, and
    whether the sentence also names a real component — and then stop.
    """
    findings: List[str] = []
    references = [r for r in data.get("references", []) if isinstance(r, dict)]

    if not references:
        findings.append(
            "No sentence on the page matched the sensory-characteristic lexicon "
            "(shape, colour, size, position, orientation, sound). Nothing to weigh — "
            "though note the lexicon is word-based, so a paraphrase it does not know "
            "would not appear here either."
        )
        return findings

    named = [r for r in references if r.get("namesInSentence")]
    findings.append(
        f"{len(references)} candidate sensory phrase(s) found; {len(named)} of them "
        f"also contain the accessible name of a real component on the page. These are "
        f"CANDIDATES, not findings: the detector is a word lexicon and cannot tell an "
        f"instruction from ordinary prose."
    )

    for index, reference in enumerate(references, start=1):
        categories = ", ".join(reference.get("categories") or [])
        matched = ", ".join(f'"{m}"' for m in reference.get("matched") or [])
        element = reference.get("element") or {}
        findings.append(
            f'{index}. In <{element.get("tag", "?")}>: "{reference.get("sentence", "")}"'
        )
        findings.append(f"      matched {categories} on {matched}")

        names = reference.get("namesInSentence") or []
        if names:
            findings.append(
                "      a component name also appears in this sentence: "
                + ", ".join(f'"{n}"' for n in names)
                + ". If the sentence is using that name to identify what it is talking "
                "about, the sensory characteristic is an ADDITIONAL cue and not the "
                "only one — check it is not a coincidence of wording."
            )
        else:
            findings.append(
                "      NO component's accessible name appears in this sentence. If it "
                "is an instruction identifying a component, the sensory characteristic "
                "is the only identifier it offers."
            )

        resolved = reference.get("resolved") or {}
        position = resolved.get("position") or {}
        for claim, matches in (position.get("claims") or {}).items():
            listed = ", ".join(f'"{m}"' for m in matches if m) or "nothing"
            findings.append(
                f'      resolved "{claim}": {listed} (measured from the rendered '
                f"layout, not from source order)"
            )
        colour = resolved.get("colour") or {}
        if colour.get("named"):
            matches = colour.get("matching") or []
            if matches:
                for match in matches:
                    findings.append(
                        f'      resolved colour: "{match.get("name")}" computes to '
                        f'{match.get("backgroundName") or match.get("textName")} '
                        f'({match.get("background") or match.get("text")})'
                    )
            else:
                findings.append(
                    f"      resolved colour: nothing on the page computes to "
                    f"{', '.join(colour['named'])} — the reference may be to something "
                    f"other than a component, or to a colour the page does not use."
                )

        unresolved = reference.get("unresolvedCategories") or []
        if unresolved:
            # Say WHY each one is unresolvable rather than repeating one generic
            # sentence: "no measurement exists" and "the measurement exists but proves
            # nothing" are different limitations and the reader should know which.
            why = {
                "sound": "nothing in a page represents a sound at all",
                "shape": "border-radius is measurable, but whether an author meant a "
                "given element by \"round\" is not",
                "size": "dimensions are measurable, but which element counts as "
                "\"large\" is a comparison the page does not state",
                "orientation": "no rendered property corresponds to it",
            }
            detail = "; ".join(f"{c} — {why.get(c, 'no measurement applies')}" for c in unresolved)
            findings.append(f"      TEXT MATCH ONLY for {detail}.")

    if data.get("truncated"):
        findings.append(
            "The scan stopped at its cap, so later prose on the page was not examined."
        )

    return findings


def _headings_labels(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_headings_labels JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    if not any(isinstance(parsed.get(k), list) for k in ("headings", "labels", "links")):
        return None
    return parsed


def _headings_labels_findings(data: Mapping[str, Any]) -> List[str]:
    """Compute only the OBJECTIVE observations from the rotor view.

    Genericness ("Section 1" says nothing) and accuracy (a heading that does not
    match its section) are deliberately left alone — those are the judgement 2.4.6
    turns on, and a keyword list would only fake it.
    """
    findings: List[str] = []
    headings = [h for h in data.get("headings") or [] if isinstance(h, dict)]
    labels = [x for x in data.get("labels") or [] if isinstance(x, dict)]
    links = [x for x in data.get("links") or [] if isinstance(x, dict)]

    def group(entries: List[Mapping[str, Any]], key: str) -> Mapping[str, list]:
        out: dict = {}
        for entry in entries:
            value = str(entry.get(key) or "").strip()
            if value:
                out.setdefault(value, []).append(entry)
        return out

    for text, group_entries in group(headings, "text").items():
        if len(group_entries) > 1:
            levels = ", ".join(f"level {e.get('level')}" for e in group_entries)
            findings.append(
                f'DUPLICATE heading "{text}" appears {len(group_entries)} times '
                f"({levels}). In a headings list these are indistinguishable — check "
                f"whether they introduce materially different content."
            )

    for phrase, group_entries in group(labels, "phrase").items():
        if len(group_entries) > 1:
            sections = ", ".join(
                str(e.get("underHeading") or "?") for e in group_entries
            )
            findings.append(
                f'DUPLICATE control label "{phrase}" appears {len(group_entries)} '
                f"times, under: {sections}. Check whether these controls do the same "
                f"thing; identically-labelled controls doing different things cannot "
                f"be told apart in a form-controls list."
            )

    # Same announced text, different destinations. Reported as context for the
    # headings/labels judgement only -- NOT as a finding to act on. Whether that is
    # a defect is WCAG 2.4.4's question, and settling it needs the programmatically
    # determined context of each link (the sentence or block around it), which this
    # rotor view does not capture: `underHeading` is a nearest-preceding heading,
    # which is not context a reader offers alongside a link. Capture the page with
    # `--sc 2.4.4` to adjudicate it.
    for text, group_entries in group(links, "text").items():
        destinations = {str(e.get("href") or "") for e in group_entries}
        if len(group_entries) > 1 and len(destinations) > 1:
            findings.append(
                f'Link text "{text}" is used {len(group_entries)} times for '
                f"{len(destinations)} different destinations "
                f"({', '.join(sorted(destinations))}). This is WCAG 2.4.4's question, not "
                f"2.4.6's, and it cannot be settled from this view — 2.4.4 lets the "
                f"surrounding sentence be what tells the links apart, and that sentence "
                f"is not captured here. Do NOT report a 2.4.4 finding from this row."
            )

    empty = [
        f'"{h.get("text")}"' for h in headings if not str(h.get("introduces") or "").strip()
    ]
    if empty:
        findings.append(
            f"Heading(s) with NO content beneath them: {', '.join(empty)}. There is "
            f"nothing for these to be descriptive of, so accuracy cannot be assessed."
        )

    return findings


def _lost_segments(before: str, after: str) -> List[str]:
    """Segments announced BEFORE input that are missing AFTER it.

    The announced phrase is a ``", "``-joined list of role, name, value, state and
    description. Entering a value always changes the phrase (the value joins it),
    so a plain inequality proves nothing — what matters is whether anything the
    reader used to say has *gone*. Every segment is checked, including the role
    word: the role never changes, so it can never be a false positive, and this
    avoids assuming the name sits at any fixed position (a password input, for
    one, announces no role at all).
    """
    return [seg for seg in before.split(", ") if seg and seg not in after]


# ---------------------------------------------------------------------------
# 1.3.1 structure observations
#
# Every other criterion in this module gets its decisive facts from a probe that
# ran against the live page. 1.3.1 has no probe: its evidence is the raw markup,
# and the model was being asked to sum `colspan` attributes across four rows and
# notice that a `<td>` holding `&nbsp;` is empty. Those are mechanical, so they
# are computed here and rendered as their own section — the same bargain the
# probe sections strike. What is NOT computed is whether a `<table>` is a data
# table at all, or whether an irregular shape actually breaks the row/column
# mapping; those are the judgements 1.3.1 turns on and they stay with the model.
#
# stdlib `html.parser` only. `requirements.txt` deliberately carries no HTML
# parser, and adding one for a cell count would be a poor trade.
# ---------------------------------------------------------------------------

_VOID_TAGS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }
)

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_LANDMARK_TAGS = ("main", "nav", "header", "footer", "aside", "section", "article")
_LIST_TAGS = ("ul", "ol", "dl")


class _Markup(HTMLParser):
    """A minimal element index of a fragment: one record per element, in order.

    Only what the structure findings below need — tag, attributes, the element's
    own children and its full descendant text. Text is appended to every open
    ancestor so each node ends up carrying its text content, which is what makes
    an "is this cell empty" test possible without a second pass.

    ``convert_charrefs`` is left on deliberately: it turns ``&nbsp;`` into
    ``\\xa0``, so a cell authored as ``<td>&nbsp;</td>`` becomes whitespace and
    the emptiness test catches it. That entity is exactly what defeated the model
    on the ``table-with-some-empty-cells`` fixture.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: List[dict] = []
        self._stack: List[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        node = {
            "tag": tag,
            "attrs": {k.lower(): (v or "") for k, v in attrs},
            "ancestors": [n["tag"] for n in self._stack],
            "children": [],
            "text": "",
        }
        if self._stack:
            self._stack[-1]["children"].append(node)
        self.nodes.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack and self._stack[-1]["tag"] == tag:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        # Unwind to the nearest matching open element. Captured markup is real
        # browser outerHTML so it is well formed, but a stray close tag must not
        # be allowed to desynchronise the stack.
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index]["tag"] == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        for node in self._stack:
            node["text"] += data


def _parse_markup(html: Any) -> List[dict]:
    """Element records for a fragment, in document order ([] if unparseable)."""
    if not isinstance(html, str) or not html.strip() or html == "nan":
        return []
    parser = _Markup()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - a findings section must never break a run
        return []
    return parser.nodes


def _own_descendants(node: Mapping[str, Any], stop_tag: str = "table"):
    """Descendants of ``node``, not descending into a nested ``stop_tag``.

    A table nested inside another table owns its own rows; walking blindly would
    attribute them to the outer table and report a shape defect that is really
    the inner table's.
    """
    for child in node["children"]:
        yield child
        if child["tag"] != stop_tag:
            yield from _own_descendants(child, stop_tag)


def _blank(text: str) -> bool:
    """True when a cell's text content is empty once entities are resolved."""
    return not text.replace("\xa0", " ").strip()


def _span(node: Mapping[str, Any], attribute: str) -> int:
    raw = str(node["attrs"].get(attribute, "")).strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else 1


def _table_findings(element_html: Any, parent_html: Any) -> List[str]:
    """Mechanical shape facts for every table in the element, verdict-free.

    Reports cell counts BESIDE ``colspan``-expanded widths rather than choosing
    between them, because the two disagreeing is itself the signal: rows of 1, 4,
    2 and 4 cells all padded to a width of 10 is a grid of label/value pairs, not
    a data table with a consistent column mapping, and either number alone hides
    that.
    """
    tables = [n for n in _parse_markup(element_html) if n["tag"] == "table"]
    if not tables:
        return []

    findings: List[str] = []
    parent_nodes = _parse_markup(parent_html)
    nested_in_parent = any(
        n["tag"] == "table" and ("table" in n["ancestors"] or "th" in n["ancestors"])
        for n in parent_nodes
    )

    for index, table in enumerate(tables, start=1):
        name = "TABLE" if len(tables) == 1 else f"TABLE {index}"
        own = list(_own_descendants(table))
        rows = [n for n in own if n["tag"] == "tr"]
        headers = [n for n in own if n["tag"] == "th"]
        data_cells = [n for n in own if n["tag"] == "td"]
        captions = [n for n in own if n["tag"] == "caption"]

        findings.append(
            f"{name}: {len(rows)} row(s), {len(headers)} <th>, {len(data_cells)} <td>."
        )

        named_by = table["attrs"].get("aria-label") or table["attrs"].get(
            "aria-labelledby"
        )
        if captions:
            findings.append(f'    <caption> present: "{captions[0]["text"].strip()}"')
        elif named_by:
            findings.append(f'    NO <caption>, but the table is named by "{named_by}".')
        else:
            findings.append(
                "    NO <caption>, and no aria-label/aria-labelledby either — this "
                "table has no accessible name."
            )

        if headers and not data_cells:
            findings.append(
                "    This table has header cells and NO data cells at all — there is "
                "nothing for the headers to be the headers OF."
            )

        # ---- shape: cell count beside colspan-expanded width -----------------
        shapes = []
        for row_index, row in enumerate(rows):
            cells = [c for c in _own_descendants(row) if c["tag"] in ("th", "td")]
            width = sum(_span(c, "colspan") for c in cells)
            shapes.append((row_index, len(cells), width, cells))
        if shapes:
            findings.append(
                "    row shape (cells -> width after colspan):  "
                + ",  ".join(f"row {i}: {n} -> {w}" for i, n, w, _ in shapes)
            )
            widths = {w for _, _, w, _ in shapes}
            counts = {n for _, n, _, _ in shapes}
            if len(widths) > 1:
                findings.append(
                    f"    Rows do NOT all expand to the same width ({sorted(widths)}) "
                    f"— the column mapping is not consistent across rows."
                )
            elif len(counts) > 1:
                findings.append(
                    f"    Every row expands to width {widths.pop()}, but the rows hold "
                    f"DIFFERENT numbers of cells ({sorted(counts)}) — the uniform width "
                    f"is produced by colspans, not by a shared column structure."
                )

        # ---- empty cells, located ---------------------------------------------
        empties = [
            f"row {i}, cell {position}"
            for i, _, _, cells in shapes
            for position, cell in enumerate(cells)
            if _blank(cell["text"])
        ]
        if empties:
            findings.append(
                f"    {len(empties)} cell(s) are EMPTY once &nbsp;/whitespace is "
                f"resolved: {', '.join(empties)}."
            )

        # ---- header association ------------------------------------------------
        unscoped = [
            h for h in headers if not h["attrs"].get("scope") and not h["attrs"].get("id")
        ]
        if unscoped:
            findings.append(
                f"    {len(unscoped)} of {len(headers)} <th> carry neither scope= nor "
                f"id= (so no headers=/id= association either): "
                + ", ".join(f'"{h["text"].strip()[:30]}"' for h in unscoped[:6])
            )

        # A <th> whose text differs on every row is a data VALUE wearing a header
        # tag — the signature tables.md describes but has never had facts to test.
        # Gated on the header being UNASSOCIATED: `<th scope="row">Jackie</th>` also
        # varies per row and is a perfectly correct row header, so scope=/headers=
        # is exactly what tells the defect from the conforming pattern.
        body_header_texts = [
            cell["text"].strip()
            for row_index, _, _, cells in shapes
            if row_index > 0
            for cell in cells
            if cell["tag"] == "th"
            and cell["text"].strip()
            and not cell["attrs"].get("scope")
            and not cell["attrs"].get("id")
        ]
        if len(body_header_texts) > 1 and len(set(body_header_texts)) == len(
            body_header_texts
        ):
            findings.append(
                f"    Below the first row, every <th> holds a DIFFERENT value "
                f"({', '.join(repr(t[:24]) for t in body_header_texts[:6])}) — values "
                f"that change per row are data, not column or row labels."
            )

        if "table" in table["ancestors"] or "th" in table["ancestors"] or nested_in_parent:
            findings.append(
                "    This table is NESTED inside another table (or inside a <th>)."
            )

    return findings


# Elements that carry an interactive role natively, so `tabindex` on them is
# ordinary. Anything else with a tabindex is claiming a place in the focus order
# without claiming a role to go with it.
_NATIVELY_INTERACTIVE = frozenset(
    {"a", "button", "input", "select", "textarea", "iframe", "frame", "audio", "video"}
)

# Controls that owe an accessible name. `input[type=hidden]` is excluded when the
# attribute is read; a hidden input is not a component.
_NAMEABLE_TAGS = frozenset({"input", "select", "textarea", "button"})


def _name_findings(element_html: Any, parent_html: Any) -> List[str]:
    """The name/label arithmetic for 4.1.2, verdict-free.

    Same bargain as the table findings: these are all countable, and the model was
    being asked to notice them by eye in a whole ``<main>`` block. Two ``<label>``
    elements pointing at one id, a hint paragraph that no ``aria-describedby``
    references, a ``tabindex`` on a ``<p>`` — each is a set operation over the
    markup, and each was missed on the 4.1.2 suite.

    What is NOT decided here is whether a name that exists is any *good*. A frame
    titled "Facebook" is reported as named; whether that describes what it embeds
    needs the ``src`` and a judgement, and stays with the model.

    Two scopes, and the split is what keeps this honest:

    * **context** — the richer of element/parent markup. Where names come FROM:
      labels, ids, ``aria-describedby`` targets. A control captured on its own has
      its ``<label>`` in the parent.
    * **scope** — what is AUDITED. Absence of a name can only be concluded from
      markup that would have contained the name, so this is normally the element
      under test alone. Without that limit, a 4.1.3 status-region row reports the
      missing labels of every input that happens to share its form — inputs the
      capture never claimed to be about — and five fixtures that pass their own
      criterion get flagged.

      The exception is when the element under test IS a nameable control. Then it
      is a leaf, everything that could name it is by definition outside it, and
      the parent is not a bystander but the control's own naming context. So scope
      widens to match context there, and only there.
    """
    element_nodes = _parse_markup(element_html)
    parent_nodes = _parse_markup(parent_html)
    context = parent_nodes if len(parent_nodes) > len(element_nodes) else element_nodes
    root = element_nodes[0] if element_nodes else None
    element_is_control = bool(
        root
        and (
            root["tag"] in _NAMEABLE_TAGS
            or root["tag"] in ("a", "iframe", "frame")
            or root["attrs"].get("tabindex")
        )
    )
    scope = context if element_is_control else (element_nodes or context)
    if not context:
        return []

    findings: List[str] = []
    ids = {n["attrs"].get("id") for n in context if n["attrs"].get("id")}

    # ---- label bindings ----------------------------------------------------
    labels = [n for n in context if n["tag"] == "label"]
    by_target: dict = {}
    for label in labels:
        target = label["attrs"].get("for")
        if target:
            by_target.setdefault(target, []).append(label)

    for target, group in by_target.items():
        if len(group) > 1:
            texts = ", ".join(f'"{l["text"].strip()}"' for l in group)
            findings.append(
                f'{len(group)} <label> elements all point at for="{target}": {texts}. '
                f"One control can have only ONE accessible name, so these either "
                f"concatenate or one is dropped — check sr_transcript for which. Any "
                f"other control those labels appear to belong to on screen has none."
            )
        if target not in ids:
            findings.append(
                f'<label for="{target}"> names an id that does not exist in this '
                f"markup — the label is bound to nothing."
            )

    # ---- controls with no name source at all --------------------------------
    for node in scope:
        if node["tag"] not in _NAMEABLE_TAGS:
            continue
        if node["tag"] == "input" and node["attrs"].get("type", "").lower() == "hidden":
            continue
        node_id = node["attrs"].get("id")
        named_by = (
            node["attrs"].get("aria-label")
            or node["attrs"].get("aria-labelledby")
            or node["attrs"].get("title")
            or (node_id and node_id in by_target)
            or "label" in node["ancestors"]
            or (node["tag"] == "button" and not _blank(node["text"]))
        )
        if not named_by:
            descriptor = f'<{node["tag"]}'
            if node["attrs"].get("type"):
                descriptor += f' type="{node["attrs"]["type"]}"'
            if node_id:
                descriptor += f' id="{node_id}"'
            descriptor += ">"
            findings.append(
                f"{descriptor} has NO name source: no <label for> pointing at it, no "
                f"wrapping <label>, no aria-label/aria-labelledby, no title."
            )

    # ---- description text bound to nothing ----------------------------------
    described = {
        ref
        for n in context
        for ref in str(n["attrs"].get("aria-describedby", "")).split()
        if ref
    }
    controls = [
        n
        for n in scope
        if n["tag"] in _NAMEABLE_TAGS
        and not (n["tag"] == "input" and n["attrs"].get("type", "").lower() == "hidden")
    ]
    if controls:
        for node in scope:
            if node["tag"] not in ("p", "span", "div") or _blank(node["text"]):
                continue
            # Only text sitting INSIDE the form, beside the controls -- prose
            # elsewhere on the page is not claiming to describe anything.
            if "form" not in node["ancestors"]:
                continue
            if node["children"]:
                continue
            if node["attrs"].get("id") in described:
                continue
            # A live region is not a description. Its whole design is to be
            # announced on change WITHOUT being attached to a control, so the
            # absence of an aria-describedby is correct there and reporting it
            # would argue against the very thing 4.1.3 asks for.
            if node["attrs"].get("aria-live") or str(
                node["attrs"].get("role", "")
            ).lower() in ("status", "alert", "log", "progressbar", "timer", "marquee"):
                continue
            findings.append(
                f'Text beside a control, referenced by no aria-describedby: '
                f'<{node["tag"]}> "{node["text"].strip()[:80]}". It is on screen and '
                f"is not part of any control's announcement."
            )

    # ---- focusable, but not a component -------------------------------------
    for node in scope:
        raw = str(node["attrs"].get("tabindex", "")).strip()
        if not raw.lstrip("+").isdigit():
            continue
        if node["tag"] in _NATIVELY_INTERACTIVE or node["attrs"].get("role"):
            continue
        findings.append(
            f'<{node["tag"]} tabindex="{raw}"> is focusable but has NO role and no '
            f"native interactive semantics"
            + (f': "{node["text"].strip()[:60]}"' if not _blank(node["text"]) else "")
            + ". Focus stops there and the reader announces the element's ordinary "
            "role, which says nothing about what it is or does."
        )

    # ---- embedded frames -----------------------------------------------------
    for node in scope:
        if node["tag"] not in ("iframe", "frame"):
            continue
        name = node["attrs"].get("title") or node["attrs"].get("aria-label")
        src = node["attrs"].get("src", "(no src)")
        if name:
            findings.append(
                f'<{node["tag"]}> is named "{name}" and embeds {src}. Whether that '
                f"name describes what is actually inside is a judgement, not a count "
                f"— read the src."
            )
        else:
            findings.append(
                f'<{node["tag"]}> embedding {src} has NO title and NO aria-label — it '
                f"is announced as a bare frame with nothing to identify it."
            )

    return findings


def _structure_findings(element_html: Any, parent_html: Any) -> List[str]:
    """How much structure the markup actually carries, verdict-free.

    Counts headings, landmarks, lists and block-level text against each other.
    The undifferentiated-blob defect has no single tag to look for — it is the
    RATIO of prose to structure — and a model reading eight long paragraphs one
    after another has no way to feel that ratio. Whether the content genuinely
    has sections that the markup fails to express is still the model's call.
    """
    element_nodes = _parse_markup(element_html)
    parent_nodes = _parse_markup(parent_html)
    # The parent is an ancestor, so it is a superset — prefer it when it actually
    # carries more heading context (a <main><p></p></main> sample cannot see the
    # <h1> that sits beside it in <body>).
    nodes = element_nodes
    scope = "the element"
    if sum(1 for n in parent_nodes if n["tag"] in _HEADING_TAGS) > sum(
        1 for n in element_nodes if n["tag"] in _HEADING_TAGS
    ):
        nodes, scope = parent_nodes, "the element's parent"
    if not nodes:
        return []

    findings: List[str] = []
    headings = [n for n in nodes if n["tag"] in _HEADING_TAGS]
    landmarks = [n for n in nodes if n["tag"] in _LANDMARK_TAGS]
    lists = [n for n in nodes if n["tag"] in _LIST_TAGS]
    blocks = [
        n for n in nodes if n["tag"] == "p" and not _blank(n["text"])
    ]
    prose = sum(len(n["text"].strip()) for n in blocks)
    orphan_li = [
        n
        for n in nodes
        if n["tag"] == "li" and not (set(n["ancestors"]) & {"ul", "ol", "menu"})
    ]
    orphan_dd = [
        n for n in nodes if n["tag"] in ("dt", "dd") and "dl" not in n["ancestors"]
    ]

    # Nothing to say about a bare <table> or an <img>: reporting "0 headings, 0
    # lists, 0 prose" on every such row would be noise competing with the table
    # findings above it for the model's attention.
    if not (headings or landmarks or lists or blocks or orphan_li or orphan_dd):
        return []

    findings.append(
        f"Structure of {scope}: {len(headings)} heading(s), {len(landmarks)} "
        f"landmark(s) ({', '.join(sorted({l['tag'] for l in landmarks})) or 'none'}), "
        f"{len(lists)} list(s), {len(blocks)} non-empty <p> carrying ~{prose} "
        f"characters of prose."
    )

    if headings:
        sequence = [(int(h["tag"][1]), h["text"].strip()[:40]) for h in headings]
        findings.append(
            "    heading sequence: "
            + " -> ".join(f'h{level} "{text}"' for level, text in sequence)
        )
        skips = [
            f"h{previous[0]} -> h{current[0]}"
            for previous, current in zip(sequence, sequence[1:])
            if current[0] > previous[0] + 1
        ]
        if skips:
            findings.append(f"    heading levels SKIP downwards at: {', '.join(skips)}")
        empty = [h for h in headings if _blank(h["text"])]
        if empty:
            findings.append(f"    {len(empty)} heading element(s) have NO text.")
    else:
        findings.append("    NO heading element anywhere in this markup.")

    if len(blocks) >= 4 and len(headings) <= 1 and not lists:
        findings.append(
            f"    {len(blocks)} blocks of prose are organised by {len(headings)} "
            f"heading(s), no list and no sectioning element. Whether that prose has "
            f"sections a reader would need to navigate between is the judgement here — "
            f"the markup expresses none."
        )

    if orphan_li:
        findings.append(f"    {len(orphan_li)} <li> with no <ul>/<ol>/<menu> ancestor.")
    if orphan_dd:
        findings.append(f"    {len(orphan_dd)} <dt>/<dd> with no <dl> ancestor.")

    return findings


def _computed_style(raw: str) -> Mapping[str, Any] | None:
    """Parse the sr_computed_style JSON object column, or None if absent."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed if parsed.get("generated") or parsed.get("links") else None


def _computed_style_findings(data: Mapping[str, Any]) -> List[str]:
    """What the page RENDERS as, for the two defects markup cannot show.

    Framed to cut both ways. Text injected by a `content:` rule is invisible in the
    HTML and in the transcript alike, so its absence from those has been read as
    "no evidence" when it is really the defect. A link's distinguishability is the
    mirror image: the markup carries only a class name, and a class name is what
    the author called the rule, not what the rule does. So the measured values are
    reported and the class name is not trusted — including when it is named after
    the very defect being looked for.

    ``differsIn`` is the whole link finding: an empty list means nothing at all
    sets the link apart from its surrounding text, and ``["color"]`` means colour
    alone does. Anything else — an underline, a weight — is a non-colour cue and a
    pass. Whether there IS surrounding text is reported beside it, because a link
    alone in a nav item has nothing to be indistinguishable from.
    """
    findings: List[str] = []

    generated = [g for g in data.get("generated") or [] if isinstance(g, dict)]
    if generated:
        findings.append(
            f"{len(generated)} CSS-GENERATED content rule(s) render text that exists "
            f"in NEITHER the source HTML NOR the transcript:"
        )
        for entry in generated:
            where = f'<{entry.get("tag")}'
            if entry.get("id"):
                where += f' #{entry.get("id")}'
            where += ">"
            findings.append(
                f'    {where}{entry.get("pseudo")} renders {entry.get("content")}'
            )
        findings.append(
            "    Content injected this way is not in the accessibility tree, so a "
            "reader never receives it. Judge whether it is decorative or whether it "
            "carries meaning the rest of the element does not."
        )

    links = [x for x in data.get("links") or [] if isinstance(x, dict)]
    for entry in links:
        differs = entry.get("differsIn")
        if differs is None:
            continue
        link = entry.get("link") or {}
        surrounding_text = str(entry.get("surroundingText") or "").strip()
        name = str(entry.get("text") or "").strip() or "(no text)"

        if not surrounding_text:
            findings.append(
                f'Link "{name}" has no surrounding text in its block, so there is '
                f"nothing for it to be visually indistinguishable from. Its own "
                f'decoration is "{link.get("textDecorationLine")}".'
            )
        elif not differs:
            findings.append(
                f'Link "{name}" computes IDENTICALLY to the text around it — same '
                f'colour ({link.get("color")}), same weight ({link.get("fontWeight")}), '
                f'text-decoration-line: {link.get("textDecorationLine")}. NOTHING '
                f'visually distinguishes it from the prose "{surrounding_text[:60]}". '
                f"Not colour alone — no cue at all."
            )
        elif differs == ["color"]:
            findings.append(
                f'Link "{name}" differs from the text around it in COLOUR ONLY '
                f'({link.get("color")} vs {(entry.get("surrounding") or {}).get("color")}), '
                f'with text-decoration-line: {link.get("textDecorationLine")}. Colour is '
                f"the only visual cue that it is a link."
            )
        else:
            findings.append(
                f'Link "{name}" differs from its surrounding text in '
                f'{", ".join(str(d) for d in differs)} — it carries a cue that is not '
                f"colour."
            )

    return findings


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

    parent_context = _parent_context_html(element_html, row.get("parent_html"))
    if parent_context is not None:
        parts.append(
            "\n## PARENT CONTEXT HTML (the element's parent — use this to check whether "
            "a REQUIRED ancestor/sibling structure exists around the element, e.g. a "
            "<ul>/<ol>/<dl> for an orphan check, or a <fieldset> around form controls. "
            "The nested copy of the element under test is replaced with a marker.)"
        )
        parts.append(parent_context)

    parts.append(
        "\n## SCREEN READER — transcript (what the virtual screen reader announces "
        "walking through this element, in order)"
    )
    parts.append(_format_phrases(_val(row, "sr_transcript")))

    frames = _frames(row.get("sr_frames"))
    if frames:
        parts.extend(_frame_lines(frames))

    # 1.3.1 structure observations. Unlike every section below, this is computed
    # from the markup rather than measured on the live page — 1.3.1 has no probe.
    # It is placed here, straight after the three standard inputs, because it is
    # a reading OF those inputs rather than an additional source of evidence.
    names = _name_findings(element_html, row.get("parent_html"))
    if names:
        parts.append(
            "\n## NAME AND LABEL OBSERVATIONS — 4.1.2 (counted from the SOURCE/PARENT "
            "HTML above, and NOT a verdict)"
        )
        parts.append(
            "Which controls have a name source and which do not, which labels bind to "
            "what, which text is attached to nothing, and what is focusable without "
            "being a component. These are set operations over the markup, so they are "
            "settled. What is NOT settled is whether a name that exists is any good — "
            "a frame titled \"Facebook\" is reported as named, and whether that "
            "describes what it embeds is yours to judge."
        )
        parts.extend(names)

    structure = _table_findings(element_html, row.get("parent_html")) + _structure_findings(
        element_html, row.get("parent_html")
    )
    if structure:
        parts.append(
            "\n## STRUCTURE OBSERVATIONS — 1.3.1 (counted from the SOURCE/PARENT HTML "
            "above, not measured on the page, and NOT a verdict)"
        )
        parts.append(
            "These are mechanical counts of what the markup encodes. They settle the "
            "questions that are arithmetic — how wide each row really is once colspans "
            "are applied, which cells are empty once &nbsp; is resolved, whether a "
            "<caption> or a scope= exists, how much prose sits under how many headings. "
            "They do NOT settle whether a <table> is a data table or a layout table, "
            "whether an irregular shape actually breaks the row/column mapping, or "
            "whether the content has sections the markup fails to express. Those are "
            "yours to judge — but judge them from these numbers, not by re-counting the "
            "raw markup yourself."
        )
        parts.extend(structure)

    # Rendered appearance. Not --sc gated like the probes below: it is the
    # sample's own computed style, present whenever the sample has a link or a
    # generated-content rule, and absent (no section) otherwise.
    style = _computed_style(_val(row, "sr_computed_style"))
    if style:
        style_findings = _computed_style_findings(style)
        if style_findings:
            parts.append(
                "\n## RENDERED APPEARANCE — computed style (measured from the page, "
                "and the ONLY evidence for anything the stylesheet does)"
            )
            parts.extend(style_findings)

    # 4.1.2 control-activation probe: only present under --sc 4.1.2.
    control_activation = None
    activation_raw = _val(row, "sr_control_activation")
    if activation_raw:
        try:
            control_activation = json.loads(activation_raw)
        except (json.JSONDecodeError, TypeError):
            control_activation = None
    if isinstance(control_activation, dict):
        inert = [x for x in control_activation.get("inert") or [] if isinstance(x, dict)]
        live = [x for x in control_activation.get("triggers") or [] if isinstance(x, dict)]
        if inert or live:
            parts.append(
                "\n## CONTROL ACTIVATION — 4.1.2 probe (each in-page control was "
                "focused and activated, and what it did was recorded)"
            )
            for entry in inert:
                parts.append(
                    f'  <{entry.get("tag")} href="{entry.get("href")}"> '
                    f'"{entry.get("text")}" did NOTHING when activated — nothing was '
                    f"revealed, the DOM did not change, and the page did not navigate."
                )
            if inert:
                parts.append(
                    "  A control that does nothing still announces its role. Note that "
                    'href="#" is ALSO how an ordinary JavaScript-driven control is '
                    "written — the measurement above, not the attribute, is what "
                    "separates the two."
                )
            for entry in live:
                trigger = entry.get("trigger") or {}
                parts.append(
                    f'  <{trigger.get("tag")}> "{trigger.get("text")}" DID respond — it '
                    f'brought {len(entry.get("revealed") or [])} component(s) into the '
                    f"tab sequence. Its role is fulfilled."
                )

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

    # 4.1.2 interaction probe: only present for role/state/value control rows.
    # An empty string means the row was not a control (not probed) -> no section.
    rsv = _role_state_value(_val(row, "sr_role_state_value"))
    if rsv:
        before, after = rsv.get("before", {}), rsv.get("after", {})
        parts.append(
            "\n## ROLE / STATE / VALUE — 4.1.2 interaction probe (the reader read "
            "the control, it was clicked once, then read again; this observes "
            "whether a state/value change the user makes is actually announced)"
        )
        parts.append(f"BEFORE click: \"{before.get('phrase', '')}\"")
        parts.append(f"AFTER click:  \"{after.get('phrase', '')}\"")
        if before.get("phrase") == after.get("phrase") and before.get("html") != after.get("html"):
            parts.append(
                "(The announced phrase did NOT change even though the raw HTML "
                "did — something visibly responded to the click but the change "
                "never reached the accessibility tree. This is the decisive 4.1.2 "
                "failure signal for stateful controls, UNLESS this is a "
                "slider/spinbutton, which is typically keyboard- not click-driven; "
                "in that case fall back to the SOURCE HTML markup's "
                "aria-valuenow/min/max.)"
            )

    # 3.3.2 interaction probe: only present for form rows captured under
    # --sc 3.3.2. An empty list means the row was not probed -> no section.
    fields = _label_instruction(_val(row, "sr_label_instruction"))
    if fields:
        parts.append(
            "\n## LABELS / INSTRUCTIONS — 3.3.2 interaction probe (each field was "
            "read, a value was entered, then it was read again; this observes "
            "whether the label and any instruction are STILL announced once the "
            "field is in use)"
        )
        any_lost = False
        for entry in fields:
            before = str(entry.get("before", {}).get("phrase", ""))
            after = str(entry.get("after", {}).get("phrase", ""))
            lost = _lost_segments(before, after)
            any_lost = any_lost or bool(lost)
            parts.append(f'  field "{entry.get("field", "?")}"')
            parts.append(f'    BEFORE input: "{before}"')
            parts.append(f'    AFTER  input: "{after}"')
            if lost:
                parts.append(
                    "    LOST on input: " + ", ".join(f'"{seg}"' for seg in lost)
                )
        parts.append(
            "\nNote: the phrase ALWAYS differs before and after, because the "
            "entered value becomes one of the announced segments — that on its own "
            "means nothing. Only a LOST segment is a finding."
        )
        if any_lost:
            parts.append(
                "(At least one field LOST an announced label or instruction the "
                "moment a value was entered — it existed only while the field was "
                "empty. This is the decisive 3.3.2 failure signal.)"
            )
        else:
            parts.append(
                "(No field lost a label or instruction on input. Note that this "
                "probe reads each field in ISOLATION, so a <fieldset>/<legend> and "
                "any instruction attached to the GROUP will not appear above — "
                "check the transcript for a 'group, <legend>, <hint>' announcement "
                "before concluding an instruction is missing.)"
            )

    # 2.4.3 focus-order sweep: only present for page rows captured under --sc 2.4.3.
    focus = _focus_order(_val(row, "sr_focus_order"))
    if focus:
        stops = [s for s in focus.get("stops", []) if isinstance(s, dict)]
        parts.append(
            "\n## FOCUS ORDER — 2.4.3 keyboard sweep (Tab was pressed from the top of "
            "the page to the end of the cycle; each stop shows what the reader "
            "announces there, where it sits on screen, and where it sits in the source)"
        )
        parts.append(
            "  stop  tabindex  dom    x,y (document)  obscured  announced"
        )
        for s in stops:
            position = _format_position(s.get("rect"))
            parts.append(
                f"  {str(s.get('stop', '?')):>4}  "
                f"{str(s.get('tabindex') if s.get('tabindex') is not None else '-'):>8}  "
                f"{str(s.get('domIndex', '?')):>4}  "
                f"{position:>15}  "
                f"{('YES' if s.get('obscured') else '-'):>8}  "
                f"\"{s.get('phrase', '')}\""
            )

        if not focus.get("complete"):
            if focus.get("stalled"):
                parts.append(
                    "\n(The sweep STALLED — focus stopped advancing, which points at a "
                    "keyboard trap. That is WCAG 2.1.2's question, not 2.4.3's: report "
                    "it, but do not flag 2.4.3 for it. Note also that this sweep cannot "
                    "settle 2.1.2 either — only Tab was pressed here, and whether focus "
                    "can escape depends on Shift+Tab and Escape, which the 2.1.2 capture "
                    "tries and this one does not.)"
                )
            elif focus.get("truncated"):
                parts.append(
                    "\n(The sweep was TRUNCATED at its cap, so the full sequence was never "
                    "observed. Do not judge the order from a partial sweep.)"
                )

        findings = _focus_order_findings(stops)
        if findings:
            parts.append("\nObservations from the sweep:")
            parts.extend(f"  - {f}" for f in findings)
        elif len(stops) >= 2:
            parts.append(
                "\nTab order matches BOTH the visual reading order and the source order, "
                "no positive tabindex, nothing obscured, and any revealed content is "
                "reached from the control that reveals it."
            )
        parts.append(
            "\nNote: those observations are necessary, not sufficient. 2.4.3 turns on "
            "whether the order preserves MEANING, which no measurement settles — an "
            "order can match visual and source order exactly and still be wrong (an "
            "open dialog reached late, or content separated from the control that "
            "revealed it). Read the announced phrases in sequence and judge whether "
            "someone moving through the page this way could still understand and "
            "operate it."
        )

        activation = focus.get("activation")
        if isinstance(activation, dict):
            parts.extend(_activation_lines(activation, len(stops)))

    # 2.4.4 link purpose: only present for page rows captured under --sc 2.4.4.
    link_purpose = _link_purpose(_val(row, "sr_link_purpose"))
    if link_purpose:
        links = [x for x in link_purpose.get("links") or [] if isinstance(x, dict)]
        parts.append(
            "\n## LINK PURPOSE — 2.4.4 (every link with what the reader announces, where "
            "it goes, and its PROGRAMMATICALLY DETERMINED CONTEXT: the sentence, block, "
            "table header cells and aria-describedby text a screen reader can offer "
            "alongside it. That list is what WCAG limits the context to — a heading "
            "further up the page is NOT on it and cannot be used to excuse a link here.)"
        )
        for x in links:
            context = x.get("context") if isinstance(x.get("context"), dict) else {}
            parts.append(f"  - announced: \"{x.get('phrase', '')}\"   -> {x.get('href')}")
            name_from = []
            if x.get("ariaLabel"):
                name_from.append(f"aria-label=\"{x.get('ariaLabel')}\"")
            if x.get("labelledBy"):
                name_from.append(f"aria-labelledby -> \"{x.get('labelledBy')}\"")
            if x.get("title"):
                name_from.append(f"title=\"{x.get('title')}\"")
            if isinstance(x.get("imgAlt"), list):
                name_from.append(
                    "image alt: "
                    + ", ".join(
                        "(MISSING)" if a is None else f'"{a}"' for a in x["imgAlt"]
                    )
                )
            if name_from:
                parts.append(f"      name from: {'; '.join(name_from)}")
            sentence = context.get("sentence")
            block = context.get("block")
            parts.append(
                f"      sentence: \"{sentence}\"" if sentence else "      sentence: (none)"
            )
            if block and block != sentence:
                parts.append(f"      {context.get('blockTag') or 'block'}: \"{block}\"")
            if context.get("tableHeaders"):
                parts.append(
                    "      table headers: "
                    + ", ".join(f'"{h}"' for h in context["tableHeaders"])
                )
            if context.get("describedBy"):
                parts.append(f"      described by: \"{context.get('describedBy')}\"")

        if link_purpose.get("truncated"):
            parts.append(
                "\n(The probe stopped at its link cap, so not every link on the page is "
                "listed. A name that looks unique above may be repeated further down.)"
            )

        findings = _link_purpose_findings(links)
        if findings:
            parts.append("\nObservations:")
            parts.extend(f"  - {f}" for f in findings)
        elif links:
            parts.append(
                "\nNo announced name is used for more than one destination, none is on "
                "the generic action/position list, and none is a bare URL."
            )
        parts.append(
            "\nNote: those observations are necessary, not sufficient, and none of them "
            "is a verdict. 2.4.4 is satisfied when the purpose of each link can be "
            "determined FROM THE NAME ALONE **or** from the name together with the "
            "context above — so a perfectly generic name passes when its sentence names "
            "the destination, and a unique, specific-sounding name fails when it "
            "describes something other than where it goes. Judge each link on whether "
            "someone who heard the name, plus at most that context, would know what they "
            "are about to open."
        )

    # 2.4.6 rotor view: only present for page rows captured under --sc 2.4.6.
    rotor = _headings_labels(_val(row, "sr_headings_labels"))
    if rotor:
        parts.append(
            "\n## HEADINGS AND LABELS — 2.4.6 rotor view (every heading, control and "
            "link with what the reader announces for it, pulled OUT of document order "
            "— this is how assistive-tech users navigate: a headings menu, a "
            "form-controls list, a links list, each entry stripped of the page around it)"
        )

        headings = [h for h in rotor.get("headings") or [] if isinstance(h, dict)]
        labels = [x for x in rotor.get("labels") or [] if isinstance(x, dict)]
        links = [x for x in rotor.get("links") or [] if isinstance(x, dict)]

        if headings:
            parts.append("\n### Headings (announced, with the content each introduces)")
            for h in headings:
                parts.append(f"  - \"{h.get('phrase', '')}\"")
                parts.append(f"      introduces: \"{h.get('introduces', '')}\"")
        if labels:
            parts.append("\n### Form controls and buttons (announced)")
            for x in labels:
                section = x.get("underHeading")
                suffix = f'   [<{x.get("tag")}>, under heading "{section}"]' if section else f'   [<{x.get("tag")}>]'
                parts.append(f"  - \"{x.get('phrase', '')}\"{suffix}")
        if links:
            parts.append("\n### Links (announced, with destination)")
            for x in links:
                parts.append(f"  - \"{x.get('phrase', '')}\"   -> {x.get('href')}")

        findings = _headings_labels_findings(rotor)
        if findings:
            parts.append("\nObservations from the rotor view:")
            parts.extend(f"  - {f}" for f in findings)
        else:
            parts.append(
                "\nNo duplicated heading, no duplicated control label, and no link text "
                "resolving to more than one destination."
            )
        parts.append(
            "\nNote: those observations cover only what is objectively checkable — "
            "duplication and ambiguous destinations. They are NOT the criterion. Every "
            "entry can be unique and still describe nothing (\"Section 1\", \"More "
            "information\"), and a heading can be unique, specific AND wrong about the "
            "content it introduces. Judge each entry on whether it would identify "
            "itself, and be TRUE, to someone who heard only it."
        )

    # 1.3.2 reading-order walk: only present for page rows captured under --sc 1.3.2.
    reading = _reading_order(_val(row, "sr_reading_order"))
    if reading:
        all_steps = [s for s in reading.get("steps", []) if isinstance(s, dict)]
        content = _content_steps(all_steps)
        parts.append(
            "\n## READING ORDER — 1.3.2 sequence vs layout (the reader's own cursor "
            "walked the page; each step pairs what was announced with where on the "
            "page it came from, so the reading sequence and the visual sequence can "
            "be compared)"
        )
        parts.append("  step  x,y (document)   announced")
        for s in content:
            position = _format_position(s.get("rect"))
            phrase = str(s.get("phrase", ""))
            if len(phrase) > 88:
                phrase = phrase[:85] + "..."
            parts.append(f"  {str(s.get('step', '?')):>4}  {position:>14}   \"{phrase}\"")

        if reading.get("truncated"):
            parts.append(
                "\n(The walk was TRUNCATED at its cap, so the full sequence was never "
                "observed. Do not judge the order from a partial walk.)"
            )

        findings = _reading_order_findings(content)
        if findings:
            parts.append("\nObservations from the walk:")
            parts.extend(f"  - {f}" for f in findings)
        parts.append(
            "\nNote: a mismatch is only a 1.3.2 violation where the SEQUENCE CARRIES "
            "MEANING — continuous prose, numbered or dependent steps, a form, a "
            "heading and the content it introduces. Where the items are genuinely "
            "independent (a grid of unrelated tiles, a card deck), reading them in a "
            "different order loses nothing and this criterion does not apply: say so "
            "rather than flagging it. Establish that the order matters here BEFORE "
            "treating any mismatch above as a defect."
        )

    # 2.1.2 escape ladder: only present for page rows captured under --sc 2.1.2.
    trap = _keyboard_trap(_val(row, "sr_keyboard_trap"))
    if trap:
        stops = [s for s in trap.get("stops", []) if isinstance(s, dict)]
        outcome = str(trap.get("outcome") or "")
        parts.append(
            "\n## KEYBOARD TRAP — 2.1.2 escape ladder (Tab was pressed from the top of "
            "the page; if focus never left, Shift+Tab was tried, and then the Escape "
            "key — this observes whether the keyboard can get back OUT of whatever it "
            "can get into)"
        )
        parts.append("  stop  tabindex  dom   announced")
        for s in stops:
            parts.append(
                f"  {str(s.get('stop', '?')):>4}  "
                f"{str(s.get('tabindex') if s.get('tabindex') is not None else '-'):>8}  "
                f"{str(s.get('domIndex', '?')):>4}  "
                f"\"{s.get('phrase', '')}\""
            )

        summary = {
            "escaped": "the forward sweep left the document on its own",
            "stalled": "the forward sweep STALLED — the same control twice in a row",
            "cycled": "the forward sweep CYCLED — a control already visited came back",
            "cap": "the forward sweep hit its cap without resolving either way",
        }
        parts.append(f"\nHow the sweep ended: {outcome} — {summary.get(outcome, 'unknown')}.")

        reverse = trap.get("reverse") if isinstance(trap.get("reverse"), dict) else None
        if reverse:
            parts.append(
                f"  Shift+Tab, {reverse.get('presses')} press(es): "
                f"{'GOT OUT' if reverse.get('exited') else 'still inside'}"
            )
        escape = trap.get("escape") if isinstance(trap.get("escape"), dict) else None
        if escape:
            parts.append(
                f"  Escape then Tab: "
                f"{'GOT OUT' if escape.get('exited') else 'still inside'}"
                + (", and the region is no longer rendered" if escape.get("regionHidden") else "")
            )

        findings = _keyboard_trap_findings(trap)
        if findings:
            parts.append("\nObservations from the ladder:")
            parts.extend(f"  - {f}" for f in findings)

        parts.append(
            "\nNote: read this the opposite way round from a focus-order finding. "
            "CONTAINING focus is not a defect — a modal dialog is SUPPOSED to cycle Tab "
            "within itself while it is open, and a grid is entitled to use Tab for its "
            "own purposes. The defect is containment with no way out. So a loop or a "
            "stall is only half the evidence; the recovery attempts above are what "
            "decide it. Equally, this ladder presses only Tab, Shift+Tab and Escape: if "
            "the markup advertises some other method, judge whether a user would know "
            "to use it rather than assuming the component is sealed."
        )

    # 3.2.1 on-focus probe: only present for page rows captured under --sc 3.2.1.
    focus_context = _focus_context(_val(row, "sr_focus_context"))
    if focus_context:
        components = [c for c in focus_context.get("components", []) if isinstance(c, dict)]
        parts.append(
            "\n## ON FOCUS — 3.2.1 context probe (every focusable component was focused "
            "in turn, on its own, and what changed as a result was recorded; focus was "
            "applied programmatically, so each component is observed in isolation)"
        )
        parts.append("  component                                        what changed on focus")
        for entry in components:
            label = _component_label(entry.get("component") or {})
            changes = _context_changes(entry)
            mutations = entry.get("mutations") or {}
            if not changes:
                counts = (
                    mutations.get("added", 0),
                    mutations.get("removed", 0),
                    mutations.get("attributes", 0),
                )
                changes = (
                    [f"DOM only: +{counts[0]} node(s), -{counts[1]}, {counts[2]} attribute(s)"]
                    if any(counts)
                    else ["nothing"]
                )
            parts.append(f"  {label[:48]:48} {'; '.join(changes)}")

        findings = _focus_context_findings(focus_context)
        if findings:
            parts.append("\nObservations from the probe:")
            parts.extend(f"  - {f}" for f in findings)

        parts.append(
            "\nNote: read this the opposite way round from the keyboard-trap section. "
            "A component changing CONTENT when focused is ORDINARY and expected — a hint "
            "appearing, a tooltip showing, a combobox listbox expanding in place, a field "
            "being highlighted. None of those is a 3.2.1 failure, and flagging them would "
            "condemn most well-built forms. 3.2.1 is about a change of CONTEXT: focus "
            "moved somewhere the user did not ask for, the page navigated, a window "
            "opened, a form submitted, or content changed so much that the meaning of the "
            "page changed. Establish which of those happened before flagging anything. "
            "Two limits worth knowing: focus here is programmatic, so a handler gated on "
            "`event.isTrusted` or `:focus-visible` would not have fired at all; and a "
            "change of context triggered on CHANGING A SETTING rather than on receiving "
            "focus is 3.2.2's question, not this one's."
        )

    # 3.2.2 on-input probe: only present for page rows captured under --sc 3.2.2.
    input_context = _input_context(_val(row, "sr_input_context"))
    if input_context:
        components = [c for c in input_context.get("components", []) if isinstance(c, dict)]
        parts.append(
            "\n## ON INPUT — 3.2.2 context probe (every component with a SETTING had it "
            "changed, one at a time, and what changed as a result was recorded; each "
            "component was focused and allowed to settle BEFORE recording began, so "
            "anything its focus handler did is excluded and belongs to 3.2.1)"
        )
        parts.append("  component                                        what changed on input")
        for entry in components:
            label = _component_label(entry.get("component") or {})
            if entry.get("note"):
                parts.append(f"  {label[:48]:48} (not measurable — see observations)")
                continue
            changes = _context_changes(entry)
            mutations = entry.get("mutations") or {}
            if not changes:
                counts = (
                    mutations.get("added", 0),
                    mutations.get("removed", 0),
                    mutations.get("attributes", 0),
                )
                changes = (
                    [f"DOM only: +{counts[0]} node(s), -{counts[1]}, {counts[2]} attribute(s)"]
                    if any(counts)
                    else ["nothing"]
                )
            if not entry.get("settingChanged"):
                changes.append("(its setting could not be changed)")
            parts.append(f"  {label[:48]:48} {'; '.join(changes)}")

        findings = _input_context_findings(input_context)
        if findings:
            parts.append("\nObservations from the probe:")
            parts.extend(f"  - {f}" for f in findings)

        parts.append(
            "\nNote: 3.2.2 differs from 3.2.1 in one way that decides most pages. On "
            "focus, a change of context is simply a failure. On input it is a failure "
            "ONLY IF the user was not advised of the behaviour before using the "
            "component — the criterion says so explicitly. So an identical measurement "
            "can be a pass or a fail depending on the text beside the control, and any "
            "advisory quoted above has to be read on its own terms: does it actually "
            "tell the user this control will move them, or is it an ordinary hint that "
            "happens to sit nearby? A label naming the control is not advice. Also, as "
            "with 3.2.1, a change of CONTENT on input is ordinary — revealing "
            "conditional fields or updating a result count changes nothing about where "
            "the user is. And note the events are dispatched, not trusted, so a handler "
            "gated on `event.isTrusted` would not have fired at all."
        )

    # 1.3.3 sensory references: only present for page rows captured under --sc 1.3.3.
    sensory = _sensory_reference(_val(row, "sr_sensory_reference"))
    if sensory:
        candidates = [c for c in sensory.get("candidates", []) if isinstance(c, dict)]
        parts.append(
            "\n## SENSORY CHARACTERISTICS — 1.3.3 (the page's prose was scanned for "
            "references to shape, colour, size, position, orientation and sound; "
            "position and colour were then resolved against the RENDERED page, the "
            "other four could not be)"
        )

        findings = _sensory_reference_findings(sensory)
        parts.extend(findings)

        if candidates:
            parts.append(
                "\nComponents on the page an instruction could be pointing at "
                "(interactive elements, labels, named regions and headings), with where "
                "they actually render and what colour they actually compute to:"
            )
            parts.append("  name                             x,y (document)   colour")
            for candidate in candidates[:25]:
                colour = candidate.get("colour") or {}
                shade = colour.get("backgroundName") or colour.get("textName") or "-"
                position = _format_position(candidate.get("rect"))
                parts.append(
                    f"  {str(candidate.get('name') or '(unnamed)')[:32]:32} "
                    f"{position:>14}   {shade}"
                )

        parts.append(
            "\nNote: this section is the one place in this evidence where the detector "
            "is a WORD LIST, and it must be read that way. \"You have the right to "
            "appeal\", \"see below for our address\" and \"a large number of appeals\" "
            "all match it, and none of them is a 1.3.3 anything. Two questions decide "
            "each candidate, in order. FIRST: is this sentence an INSTRUCTION for "
            "understanding or operating content, and does it identify a component at "
            "all? Most matches fail here and should be dismissed in a clause. SECOND, "
            "only if it survives: is the sensory characteristic the SOLE identifier? "
            "Mentioning colour, shape or position is not the defect and never was — "
            "\"the green Confirm button\" is exemplary. Relying on it alone is the "
            "defect. Where colour conveys information but no instruction is involved, "
            "that is 1.4.1 Use of Color; report it under that key, not this one."
        )

    return Evidence(
        element_tag=element_tag,
        is_container=is_container,
        block="\n".join(parts),
    )
