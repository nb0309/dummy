"""Routing fixtures for the W3 CityLights misses — no LLM, no capture files.

Each case is a synthetic row: outermost tag + whether a probe column is filled.
The assertions lock the gates in skill YAML and ``requires_column_if_tag``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import evidence, router  # noqa: E402

STATUS_ID = "4.1.3/status-messages"
COLOUR_ID = "1.4.1/use-of-colour"
LABELS_ID = "3.3.2/labels-instructions"
ON_INPUT_ID = "3.2.2/on-input-context-change"
LINK_PURPOSE_ID = "2.4.4/link-purpose-in-context"


def _row(html: str, **cols: object) -> dict:
    row = {
        "element_html": html,
        "parent_html": cols.pop("parent_html", "<body></body>"),
        "sr_transcript": cols.pop("sr_transcript", "[]"),
    }
    row.update(cols)
    return row


def _ids(skills) -> list[str]:
    return [s.id for s in skills]


def _applied(row: Mapping[str, object]) -> tuple[list[str], list[str]]:
    ev = evidence.build(row)
    primary, secondary = router.partition(ev, row)
    return _ids(primary), _ids(secondary)


def test_nav_ul_does_not_get_status_messages():
    """W3 samples 2–3: ordinary nav lists are not 4.1.3, even if the column exists."""
    html = "<ul><li><a href='/'>Home</a></li></ul>"
    primary, secondary = _applied(_row(html))
    assert STATUS_ID not in primary + secondary

    primary, secondary = _applied(
        _row(html, sr_status_announcement="polite: 5 results found")
    )
    assert STATUS_ID not in primary + secondary


def test_status_probe_on_live_region_is_primary():
    html = '<div role="status">Saved</div>'
    primary, secondary = _applied(_row(html))
    assert STATUS_ID not in primary + secondary

    primary, secondary = _applied(
        _row(html, sr_status_announcement="polite: Saved")
    )
    assert STATUS_ID in primary
    assert STATUS_ID not in secondary


def test_link_and_table_without_computed_style_skip_use_of_colour():
    for html in (
        '<a href="https://www.w3.org/" title="W3C Home"><img alt="W3C logo" src="w3.png"></a>',
        "<table><tr><td>layout</td></tr></table>",
    ):
        primary, secondary = _applied(_row(html))
        assert COLOUR_ID not in primary + secondary


def test_use_of_colour_is_primary_when_style_probe_ran():
    html = '<a href="/more">Read more</a>'
    primary, _ = _applied(
        _row(
            html,
            sr_computed_style='{"color":"#0000ee","textDecoration":"none"}',
        )
    )
    assert COLOUR_ID in primary


def test_unlabelled_select_gets_labels_instructions():
    html = (
        '<select name="quicknav" onchange="location.href=this.value">'
        "<option>QUICKMENU -----></option>"
        '<option value="/news">News</option>'
        "</select>"
    )
    primary, secondary = _applied(_row(html))
    assert LABELS_ID in primary + secondary


def test_select_onchange_navigate_gets_on_input():
    html = (
        '<select name="quicknav" onchange="location.href=this.value">'
        "<option>QUICKMENU -----></option>"
        "</select>"
    )
    primary, secondary = _applied(_row(html))
    assert ON_INPUT_ID in primary + secondary
    assert ON_INPUT_ID not in primary


def test_body_without_input_probe_does_not_get_on_input():
    html = "<body><select onchange='location.href=this.value'></select></body>"
    primary, secondary = _applied(_row(html))
    assert ON_INPUT_ID not in primary + secondary


def test_body_with_input_probe_gets_on_input_primary():
    html = "<body><select onchange='location.href=this.value'></select></body>"
    primary, _ = _applied(
        _row(html, sr_input_context='{"components":[{"navigatedTo":"/news"}]}')
    )
    assert ON_INPUT_ID in primary


def test_anchor_without_link_purpose_probe_does_not_get_2_4_4():
    html = '<a href="https://www.w3.org/" title="W3C Home"><img alt="W3C logo" src="w3.png"></a>'
    primary, secondary = _applied(_row(html))
    assert LINK_PURPOSE_ID not in primary + secondary


def test_form_with_label_probe_promotes_3_3_2():
    html = '<form><label for="email">Email</label><input id="email"></form>'
    primary, secondary = _applied(_row(html))
    assert LABELS_ID in secondary
    assert LABELS_ID not in primary

    primary, secondary = _applied(
        _row(
            html,
            sr_label_instruction=(
                '[{"field":"email","before":{"phrase":"textbox, Email"},'
                '"after":{"phrase":"textbox, Email, a@b.c"}}]'
            ),
        )
    )
    assert LABELS_ID in primary
    assert LABELS_ID not in secondary


@pytest.mark.parametrize(
    "html",
    [
        '<input type="text" placeholder="Email">',
        "<textarea></textarea>",
        "<label>Name</label>",
    ],
)
def test_3_3_2_matches_control_tags(html):
    _, secondary = _applied(_row(html))
    assert LABELS_ID in secondary


PAGE_LEVEL_IDS = [
    "2.4.3/focus-order",
    "2.4.4/link-purpose-in-context",
    "2.4.6/headings-labels",
    "1.3.2/meaningful-sequence",
    "1.3.3/sensory-characteristics",
    "2.1.2/keyboard-trap",
    "3.2.1/on-focus-context-change",
    "3.2.2/on-input-context-change",
]


def test_body_without_probes_does_not_get_page_level_skills():
    """A content-block <body> must not be judged against probes that never ran."""
    primary, secondary = _applied(_row("<body><h1>Hello</h1><p>Content</p></body>"))
    applied = primary + secondary
    for skill_id in PAGE_LEVEL_IDS:
        assert skill_id not in applied
    assert applied, "ungated 1.3.1 / 4.1.2 skills should still attach"


def test_output_without_status_probe_stays_empty():
    """Dropping the only match must not re-attach it via the old empty-list fallback."""
    primary, secondary = _applied(_row("<output>Saved</output>"))
    assert STATUS_ID not in primary + secondary
    assert primary == []
    assert secondary == []
