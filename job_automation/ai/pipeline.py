"""
ai/pipeline.py — Selects the correct prompt track (analyst / engineer) for a job.

Two selection modes:
  role_hint   — default; uses job title keywords from config role_keyword_sets.
  classifier  — placeholder for a future ML/AI-based classifier.
"""
from __future__ import annotations

import logging
import re

from ai.prompts import (
    ANALYST_SYSTEM_PROMPT,
    ANALYST_USER_TEMPLATE,
    ENGINEER_SYSTEM_PROMPT,
    ENGINEER_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)

# Title keywords that lean toward each track.
# Order matters: first match wins.
_ENGINEER_TITLE_KEYWORDS = [
    "data engineer",
    "data engineering",
    "pipeline engineer",
    "etl engineer",
    "analytics engineer",
    "platform engineer",
    "infrastructure engineer",
    "backend engineer",
    "ml engineer",
    "machine learning engineer",
    "mlops",
]

_ANALYST_TITLE_KEYWORDS = [
    "data analyst",
    "business analyst",
    "bi analyst",
    "business intelligence",
    "product analyst",
    "marketing analyst",
    "operations analyst",
    "insights analyst",
    "reporting analyst",
]


def select_track(role: str, mode: str = "role_hint") -> str:
    """
    Return "analyst" or "engineer" for the given job role string.

    Args:
        role: job title / role string scraped from the portal.
        mode: "role_hint" (keyword match) or "classifier" (future).
    """
    if mode == "classifier":
        # Placeholder — fall through to role_hint for now
        logger.debug("Classifier mode not yet implemented; falling back to role_hint.")

    normalized = role.lower()
    for kw in _ENGINEER_TITLE_KEYWORDS:
        if kw in normalized:
            logger.debug("Track=engineer matched keyword '%s' in role '%s'", kw, role)
            return "engineer"
    for kw in _ANALYST_TITLE_KEYWORDS:
        if kw in normalized:
            logger.debug("Track=analyst matched keyword '%s' in role '%s'", kw, role)
            return "analyst"

    # Default to analyst for ambiguous titles
    logger.debug("No keyword match for role '%s' — defaulting to analyst track.", role)
    return "analyst"


def get_prompts(track: str) -> tuple[str, str]:
    """
    Return (system_prompt, user_template) for the given track.

    Args:
        track: "analyst" or "engineer".

    Returns:
        Tuple of (system_prompt, user_template).
    """
    if track == "engineer":
        return ENGINEER_SYSTEM_PROMPT, ENGINEER_USER_TEMPLATE
    return ANALYST_SYSTEM_PROMPT, ANALYST_USER_TEMPLATE
