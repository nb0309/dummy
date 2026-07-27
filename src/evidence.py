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
    """

    def key(stop: Mapping[str, Any]) -> tuple:
        rect = stop.get("rect") or {}
        y = int(rect.get("y") or 0)
        x = int(rect.get("x") or 0)
        if major == "column":
            return (x // band, y)
        return (y // band, x)

    return [int(s.get(id_key) or 0) for s in sorted(stops, key=key)]


def _focus_order_findings(stops: List[Mapping[str, Any]]) -> List[str]:
    """Derive the near-mechanical focus-order signals a person would eyeball.

    Deliberately does NOT decide the verdict — 2.4.3 turns on whether the order
    preserves *meaning*, which is the judgement handed to the model. These are the
    observations that judgement should start from.
    """
    findings: List[str] = []
    tab_order = [int(s.get("stop") or 0) for s in stops]

    visual = _visual_rank(stops)
    if visual != tab_order:
        findings.append(
            f"Tab order does NOT match visual reading order.\n"
            f"    tab order    : {tab_order}\n"
            f"    visual order : {visual}   (top-to-bottom, then left-to-right)"
        )

    dom_order = [
        int(s.get("stop") or 0)
        for s in sorted(stops, key=lambda s: int(s.get("domIndex") or 0))
    ]
    if dom_order != tab_order:
        findings.append(
            f"Tab order does NOT match source (DOM) order.\n"
            f"    tab order    : {tab_order}\n"
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


def _content_steps(steps: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """The steps worth comparing positions for.

    The walk emits two steps per element — its role ("paragraph") then its text —
    sharing a ``domIndex``, plus "end of …" boundary phrases. It also passes
    through containers like ``<body>``, whose rect spans the whole page and would
    distort any ranking. So: drop boundaries, keep only leaves, and collapse each
    element to one step.

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
        if not step.get("isLeaf") or not step.get("rect"):
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

    # The one fully objective link check: same announced text, different
    # destinations. Repetition alone is NOT the defect -- a "Contact us" link in
    # header, body and footer pointing at one page is ordinary markup.
    for text, group_entries in group(links, "text").items():
        destinations = {str(e.get("href") or "") for e in group_entries}
        if len(group_entries) > 1 and len(destinations) > 1:
            findings.append(
                f'AMBIGUOUS link text "{text}" is used {len(group_entries)} times for '
                f"{len(destinations)} different destinations "
                f"({', '.join(sorted(destinations))}). Report this under 2.4.4, not 2.4.6."
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
            rect = s.get("rect") or {}
            position = f"{rect.get('x', '?')},{rect.get('y', '?')}"
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
            rect = s.get("rect") or {}
            position = f"{rect.get('x', '?')},{rect.get('y', '?')}"
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

    return Evidence(
        element_tag=element_tag,
        is_container=is_container,
        block="\n".join(parts),
    )
