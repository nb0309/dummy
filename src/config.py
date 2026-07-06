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

# Default dataset the new pipeline classifies. Unlike the legacy script (which
# expected a hand-renamed ``input.csv``) we read the rich capture directly.
DEFAULT_INPUT_CSV = REPO_ROOT / "dataset.csv"
DEFAULT_OUTPUT_CSV = REPO_ROOT / "predictions_skill_based.csv"
DEFAULT_LOG_FILE = REPO_ROOT / "llm_calls.log"

# Routing mode:
#   "blind"  -> the router never looks at the ground-truth ``wcag_sc`` column
#               (this reflects real usage where the SC is unknown).
#   "oracle" -> narrow candidate skills to the row's ``wcag_sc`` (debug only).
ROUTING_MODE = os.getenv("ROUTING_MODE", "blind").strip().lower()


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return an environment variable, treating empty strings as unset."""
    value = os.getenv(name)
    return value if value not in (None, "") else default
