"""Load skill specs from markdown-with-frontmatter files.

A *skill* is a self-describing WCAG check. Each ``.md`` file under
``src/skills`` has a YAML frontmatter block (machine-readable routing predicates
and evidence hints) followed by a markdown body (the rubric shown to the LLM).

Example::

    ---
    sc: "1.3.1"
    technique: "data-table-missing-headers"
    title: "Data table missing header cells"
    applies_when:
      element_tag: [table]
      ax_role: [table, grid]
    signals:
      - field: ax_subtree
        look_for: "every data cell announces as 'cell', never 'columnheader'"
    ---
    ## Violation criteria
    ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import yaml

from ..config import SKILLS_DIR

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass
class Signal:
    field: str
    look_for: str


@dataclass
class Skill:
    sc: str
    technique: str
    title: str
    applies_when: Dict[str, List[str]]
    signals: List[Signal]
    body: str
    source_path: Path
    axe_ids: List[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """Stable identifier, e.g. ``1.3.1/data-table-missing-headers``."""
        return f"{self.sc}/{self.technique}"

    def prompt_block(self) -> str:
        """Render this skill for injection into the system prompt."""
        signal_lines = "\n".join(
            f"  - `{s.field}`: {s.look_for}" for s in self.signals
        )
        return (
            f"### SKILL {self.sc} — {self.title}  (technique: {self.technique})\n"
            f"Diagnostic signals to inspect:\n{signal_lines}\n\n"
            f"{self.body.strip()}\n"
        )


def _parse_skill(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"Skill file missing YAML frontmatter: {path}")

    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2)

    signals = [
        Signal(field=str(s.get("field", "")), look_for=str(s.get("look_for", "")))
        for s in (meta.get("signals") or [])
    ]
    applies = {
        key: [str(v).lower() for v in vals]
        for key, vals in (meta.get("applies_when") or {}).items()
    }

    return Skill(
        sc=str(meta["sc"]),
        technique=str(meta["technique"]),
        title=str(meta.get("title", meta["technique"])),
        applies_when=applies,
        signals=signals,
        body=body,
        source_path=path,
        axe_ids=[str(a).lower() for a in (meta.get("axe_ids") or [])],
    )


@lru_cache(maxsize=1)
def load_skills() -> List[Skill]:
    """Load and cache every skill spec under ``src/skills`` (recursively)."""
    skills = [_parse_skill(p) for p in sorted(SKILLS_DIR.rglob("*.md"))]
    if not skills:
        raise RuntimeError(f"No skill specs found under {SKILLS_DIR}")
    return skills
