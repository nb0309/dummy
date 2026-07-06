"""Paths and environment configuration.

Centralises filesystem locations and environment lookups so the rest of the
package never has to know where the repo root or the dataset live. The Azure
credential loading logic is ported verbatim from the legacy ``testing.py``.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# ``config.py`` lives in ``<repo>/src``; the repo root is one level up.
SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent
SKILLS_DIR = SRC_DIR / "skills"

# Default dataset the new pipeline classifies. Each row carries only the three
# model inputs (element HTML, parent HTML, screen-reader transcript) plus a
# label and a sample_id.
DEFAULT_INPUT_CSV = REPO_ROOT / "dataset.csv"
DEFAULT_OUTPUT_CSV = REPO_ROOT / "predictions_skill_based.csv"
DEFAULT_LOG_FILE = REPO_ROOT / "llm_calls.log"


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return an environment variable, treating empty strings as unset."""
    value = os.getenv(name)
    return value if value not in (None, "") else default
