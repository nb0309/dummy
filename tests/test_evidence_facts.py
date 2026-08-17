"""The evidence block must CONTAIN the fact that decides each known defect.

Why this suite exists
---------------------
The pipeline has two halves. The second half — whether the model reaches the right
verdict — needs Azure credentials and cannot be tested here. The first half is
entirely deterministic: given a captured row, the rendered evidence either states
the fact that settles the criterion or it does not. Every accuracy fix in this
repo so far has been a fix to that half, and each was verified once by eye and
then had nothing holding it in place.

So these tests assert the fact, not the verdict. A regression in the capture or in
`evidence.py` that silently stops reporting an empty table cell, or a link that
computes identically to its surrounding text, fails here — without an API key and
without a token spent.

They read the committed datasets under ``testcase/``. When a dataset is
re-captured, these run against the new one; if a fact stops being reported, that is
either a bug or a deliberate change that should be reflected here.

    python -m pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import evidence, orchestrator, router  # noqa: E402

TESTCASE = REPO_ROOT / "testcase"


# (dataset, sample_id, [substrings the evidence block must contain])
#
# Substrings are deliberately the load-bearing phrase and nothing more, so that
# rewording the prose around a finding does not fail the suite but dropping the
# finding does.
DECISIVE_FACTS = [
    # ---- round 1: 1.3.1 structure, computed style, capture scope -------------
    (
        "1.3.1",
        "tables-table-with-some-empty-cells::sample-0",
        ["are EMPTY once", "row 1, cell 0"],
    ),
    (
        "1.3.1",
        "tables-table-that-only-has-th-elements-in-it::sample-0",
        ["0 <td>", "NO data cells at all"],
    ),
    (
        "1.3.1",
        "tables-table-with-inconsistent-numbers-of-columns-in-rows::sample-0",
        ["DIFFERENT numbers of cells"],
    ),
    ("1.3.1", "tables-table-is-missing-a-caption::sample-0", ["NO <caption>"]),
    ("1.3.1", "unorganised_content::sample-0", ["blocks of prose are organised by"]),
    (
        "1.3.1",
        "links-link-not-clearly-identifiable-and-distinguishable-from-surrounding-text::sample-0",
        ["computes IDENTICALLY to the text around it"],
    ),
    (
        "1.3.1",
        "css-non-decorative-content-inserted-using-css::sample-0",
        ["::after renders", "Pizza"],
    ),
    # The widened parent for grouped controls: all three siblings must be in view,
    # because "is this group in a fieldset" cannot be answered from one of them.
    (
        "1.3.1",
        "forms-group-of-check-boxes-not-enclosed-in-a-fieldset::sample-0",
        ["waste-type-1", "waste-type-2", "waste-type-3"],
    ),
    # ---- round 2: the 2.4.3 activation pass ---------------------------------
    (
        "2.4.3",
        "keyboard-access-lightbox-focus-is-not-moved-immediately-to-lightbox::sample-0",
        ["FOCUS ORDER AFTER ACTIVATION", "Focus did NOT move into the revealed content"],
    ),
    (
        "2.4.3",
        "keyboard-access-lightbox-focus-is-not-retained-within-the-lightbox::sample-0",
        ["FOCUS ORDER AFTER ACTIVATION", "Focus did NOT move into the revealed content"],
    ),
    (
        "2.4.3",
        "keyboard-access-tabindex-greater-than-0::sample-0",
        ["Positive tabindex in use"],
    ),
    # ---- round 3: 4.1.2 name, label and dead controls ------------------------
    (
        "4.1.2",
        "forms-two-unique-labels-but-identical-for-attributes::sample-0",
        ['point at for="two-labels-day"'],
    ),
    (
        "4.1.2",
        "forms-field-hint-not-associated-with-input::sample-0",
        ["referenced by no aria-describedby"],
    ),
    (
        "4.1.2",
        "keyboard-access-keyboard-focus-assigned-to-a-non-focusable-element-using-tabindex0::sample-0",
        ["is focusable but has NO role"],
    ),
    (
        "4.1.2",
        "frames-iframe-is-missing-a-title-attribute::sample-0",
        ["NO title and NO aria-label"],
    ),
    (
        "4.1.2",
        "links-link-to--invalid-hypertext-reference::sample-0",
        ["did NOTHING when activated"],
    ),
]

# Facts that must NOT be reported. Each one is a false positive that was actually
# produced during development and then designed out; without these the guard is
# only a comment.
ABSENT_FACTS = [
    # A page with no in-page trigger has no activation section to show.
    (
        "2.4.3",
        "keyboard-access-focus-order-in-wrong-order::sample-0",
        ["FOCUS ORDER AFTER ACTIVATION"],
    ),
    # `<th scope="row">Jackie</th>` varies per row and is a CORRECT row header.
    # Reporting it as data mis-marked as a header flags a conforming table.
    (
        "1.3.1",
        "tables-table-is-missing-a-caption::sample-0",
        ["every <th> holds a DIFFERENT value"],
    ),
]


def _dataset(name: str) -> pd.DataFrame:
    path = TESTCASE / f"{name}_dataset.csv"
    if not path.exists():
        pytest.skip(f"dataset not captured: {path.name}")
    return pd.read_csv(path).set_index("sample_id")


def _block(dataset: str, sample_id: str) -> str:
    frame = _dataset(dataset)
    if sample_id not in frame.index:
        pytest.fail(
            f"{dataset}: no sample '{sample_id}'. The capture changed which elements "
            f"it samples; available: {list(frame.index)[:8]}"
        )
    return evidence.build(frame.loc[sample_id]).block


@pytest.mark.parametrize(
    "dataset,sample_id,expected",
    DECISIVE_FACTS,
    ids=[f"{d}-{s.split('::')[0][:40]}" for d, s, _ in DECISIVE_FACTS],
)
def test_decisive_fact_is_reported(dataset, sample_id, expected):
    block = _block(dataset, sample_id)
    for fragment in expected:
        assert fragment in block, (
            f"{dataset}/{sample_id}: evidence no longer states {fragment!r}. "
            f"The model cannot decide this criterion without it."
        )


@pytest.mark.parametrize(
    "dataset,sample_id,forbidden",
    ABSENT_FACTS,
    ids=[f"{d}-{s.split('::')[0][:40]}" for d, s, _ in ABSENT_FACTS],
)
def test_false_positive_stays_absent(dataset, sample_id, forbidden):
    block = _block(dataset, sample_id)
    for fragment in forbidden:
        assert fragment not in block, (
            f"{dataset}/{sample_id}: evidence reports {fragment!r}, which is a false "
            f"positive this fixture was used to design out."
        )


def test_accessible_rows_get_no_name_findings():
    """4.1.3's passing fixtures are the corpus's only false-positive guard.

    They contain inputs whose labels have no `for` — a real 4.1.2 defect — but the
    capture is of a live region, not of those inputs. Auditing controls the row
    never claimed to be about is what would flag five conforming files.
    """
    frame = _dataset("4.1.3")
    accessible = frame[frame["label"] == "accessible"]
    assert len(accessible) == 5, "the 4.1.3 guard changed shape; re-check this test"
    for sample_id, row in accessible.iterrows():
        findings = evidence._name_findings(row["element_html"], row["parent_html"])
        assert not findings, f"{sample_id} would now be flagged: {findings}"


def _all_matches_dropped_for_missing_columns(ev, row) -> bool:
    """True when every tag match was probe-gated and the probe data is empty."""
    selected = orchestrator.route(ev.element_tag)
    if not selected:
        return False
    for skill in selected:
        required = skill.applies_when.get("requires_column", [])
        if not required:
            return False
        if router._has_columns(row, required):
            return False
        if "requires_column_if_tag" not in skill.applies_when:
            continue
        if ev.element_tag in skill.applies_when["requires_column_if_tag"]:
            continue
        return False
    return True


@pytest.mark.parametrize(
    "dataset", sorted(p.name.split("_")[0] for p in TESTCASE.glob("*_dataset.csv"))
)
def test_every_row_routes_to_a_skill(dataset):
    """Every row gets a skill, unless every tag match was a probe-gated drop."""
    for sample_id, row in _dataset(dataset).iterrows():
        ev = evidence.build(row)
        primary, secondary = router.partition(ev, row)
        if primary or secondary:
            continue
        assert _all_matches_dropped_for_missing_columns(ev, row), (
            f"{dataset}/{sample_id} routed to no skill"
        )


@pytest.mark.parametrize(
    "dataset", ["2.4.3", "2.4.4", "2.4.6", "1.3.2", "1.3.3", "2.1.2", "3.2.1", "3.2.2"]
)
def test_probe_backed_skill_is_primary(dataset):
    """A page captured for a criterion must be asked that criterion first.

    Before this, a `<body>` row matched nine skills in load order and the one
    holding the decisive probe was buried among them.
    """
    for sample_id, row in _dataset(dataset).iterrows():
        ev = evidence.build(row)
        primary, _ = router.partition(ev, row)
        assert primary, f"{dataset}/{sample_id} has no primary skill"
        assert primary[0].sc == dataset, (
            f"{dataset}/{sample_id}: primary skill is {primary[0].id}, "
            f"not the criterion this page was captured for"
        )


def _synth(element_html: str, parent_html: object = "<body></body>", **cols: object) -> dict:
    row = {
        "element_html": element_html,
        "parent_html": parent_html,
        "sr_transcript": "[]",
    }
    row.update(cols)
    return row


def test_parent_context_replaces_nested_element_with_marker():
    element = '<input id="a" type="checkbox">'
    parent = (
        f'<form><label for="a">{element} One</label>'
        '<input id="b" type="checkbox"></form>'
    )
    block = evidence.build(_synth(element, parent)).block
    assert block.count(element) == 1
    assert evidence._ELEMENT_HOLE in block
    assert '<input id="b" type="checkbox">' in block
    assert "## PARENT CONTEXT HTML" in block


def test_parent_context_omitted_when_identical_to_element():
    html = "<main><p>hello</p></main>"
    block = evidence.build(_synth(html, html)).block
    assert "## PARENT CONTEXT HTML" not in block
    assert html in block


def test_parent_context_omitted_when_missing():
    block = evidence.build(_synth("<p>x</p>", None)).block
    assert "## PARENT CONTEXT HTML" not in block
    assert "No HTML context provided" not in block


def test_parent_context_left_intact_when_element_is_not_nested():
    element = '<input id="a" type="text">'
    parent = "<body><h1>Title</h1></body>"
    block = evidence.build(_synth(element, parent)).block
    assert evidence._ELEMENT_HOLE not in block
    assert parent in block


def test_page_level_parent_keeps_head_and_drops_body():
    body = "<body><h1>Focus order</h1><main><a href='#'>First</a></main></body>"
    parent = (
        '<html lang="en"><head><title>Test</title>'
        '<link rel="stylesheet" href="tests.css"></head>' + body + "</html>"
    )
    block = evidence.build(_synth(body, parent)).block
    assert block.count(body) == 1
    assert evidence._ELEMENT_HOLE in block
    assert '<link rel="stylesheet" href="tests.css">' in block
    assert "<title>Test</title>" in block


def test_fact_finders_still_see_full_stored_parent():
    """The hole is prompt-only; label arithmetic still uses stored parent_html."""
    element = '<input id="empty" type="text">'
    parent = f'<form><label for="missing"></label>{element}</form>'
    block = evidence.build(_synth(element, parent)).block
    assert "names an id that does not exist" in block
    assert evidence._ELEMENT_HOLE in block


def test_widened_parent_keeps_siblings_after_hole_punch():
    block = _block(
        "1.3.1", "forms-group-of-check-boxes-not-enclosed-in-a-fieldset::sample-0"
    )
    sample = (
        '<input id="waste-type-1" name="waste-types" type="checkbox" '
        'value="waste-animal">'
    )
    assert evidence._ELEMENT_HOLE in block
    assert block.count(sample) == 1
    assert "waste-type-2" in block
    assert "waste-type-3" in block


def test_skipped_cross_origin_frame_is_reported():
    block = evidence.build(
        _synth(
            "<body><h1>Checkout</h1></body>",
            sr_frames=[
                {
                    "index": 0,
                    "tag": "iframe",
                    "src": "https://js.stripe.com/v3/controller",
                    "title": "Payment",
                    "url": "https://js.stripe.com/v3/controller",
                    "status": "skipped",
                    "skipped": "cross-origin",
                    "inner": None,
                    "sampled": 0,
                }
            ],
        )
    ).block
    assert "## FRAMES" in block
    assert "SKIPPED" in block
    assert "cross-origin" in block
    assert "js.stripe.com" in block
    assert "not sampled, not walked, not judged" in block


def test_inspected_frame_lists_inner_counts():
    block = evidence.build(
        _synth(
            "<body></body>",
            sr_frames=[
                {
                    "index": 0,
                    "tag": "iframe",
                    "src": "/chat.html",
                    "title": "Support",
                    "status": "inspected",
                    "skipped": None,
                    "sampled": 2,
                    "inner": {
                        "forms": 1,
                        "inputs": 3,
                        "media": 0,
                        "headings": 1,
                        "links": 0,
                        "textPreview": "How can we help",
                    },
                }
            ],
        )
    ).block
    assert "INSPECTED" in block
    assert "3 control(s)" in block
    assert "sampled 2 element(s) inside" in block
    assert "How can we help" in block


def test_no_frames_section_when_absent():
    block = evidence.build(_synth("<p>hi</p>")).block
    assert "## FRAMES" not in block


def test_no_frames_section_when_pandas_nan():
    block = evidence.build(_synth("<p>hi</p>", sr_frames=float("nan"))).block
    assert "## FRAMES" not in block
    assert evidence._frames(float("nan")) is None


