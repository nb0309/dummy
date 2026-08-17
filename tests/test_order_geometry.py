"""Visual-order ranking must ignore unpositioned component hosts."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import evidence  # noqa: E402


def _stop(n: int, x: int, y: int, w: int = 40, h: int = 20, **extra: object) -> dict:
    return {"stop": n, "step": n, "rect": {"x": x, "y": y, "w": w, "h": h}, **extra}


def test_zero_size_rect_is_not_a_position():
    assert not evidence._usable_rect(None)
    assert not evidence._usable_rect({})
    assert not evidence._usable_rect({"x": 0, "y": 0, "w": 0, "h": 0})
    assert evidence._usable_rect({"x": 10, "y": 20, "w": 1, "h": 0})
    assert evidence._format_position({"x": 0, "y": 0, "w": 0, "h": 0}) == "unknown"


def test_visual_rank_skips_empty_boxes_instead_of_origin():
    stops = [
        _stop(1, 200, 80),
        {"stop": 2, "step": 2, "rect": {"x": 0, "y": 0, "w": 0, "h": 0}},
        _stop(3, 40, 80),
    ]
    # Without the skip, stop 2 ranks first at (0,0) and the row reads 2,3,1.
    assert evidence._visual_rank(stops) == [3, 1]


def test_focus_findings_do_not_let_unknown_scramble_tab_vs_source():
    stops = [
        {**_stop(1, 10, 10), "domIndex": 5, "tabindex": None},
        {
            "stop": 2,
            "rect": {"x": 0, "y": 0, "w": 0, "h": 0},
            "domIndex": 9,
            "tabindex": None,
        },
        {**_stop(3, 10, 80), "domIndex": 12, "tabindex": None},
    ]
    findings = evidence._focus_order_findings(stops)
    joined = "\n".join(findings)
    assert "omitted from the visual-order comparison" in joined
    assert "does NOT match source" not in joined


def test_content_steps_keep_component_text_and_drop_empty_boxes():
    steps = [
        {
            "step": 1,
            "phrase": "button",
            "isLeaf": False,
            "nodeType": 1,
            "domIndex": 4,
            "rect": {"x": 10, "y": 10, "w": 80, "h": 24},
        },
        {
            "step": 2,
            "phrase": "Save",
            "isLeaf": False,
            "nodeType": 3,
            "domIndex": 4,
            "rect": {"x": 28, "y": 12, "w": 40, "h": 16},
        },
        {
            "step": 3,
            "phrase": "ghost",
            "isLeaf": True,
            "nodeType": 3,
            "domIndex": 7,
            "rect": {"x": 0, "y": 0, "w": 0, "h": 0},
        },
    ]
    kept = evidence._content_steps(steps)
    assert [s["phrase"] for s in kept] == ["Save"]
