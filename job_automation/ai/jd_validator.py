"""
ai/jd_validator.py — Deterministic JD technical relevance validator.

Filters out non-technical / bait postings (insurance, sales, etc.) before
any AI provider is called.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    is_pass: bool
    score: int
    matched_keywords: list[str] = field(default_factory=list)
    matched_deny_patterns: list[str] = field(default_factory=list)
    reason: str = ""


class JDValidator:
    """
    Validates a job description against a set of technical keywords and
    deny patterns loaded from config.

    Args:
        role_keywords:   list of technical keywords for the selected role profile.
        deny_patterns:   list of phrases that immediately disqualify a posting.
        min_keyword_hits: minimum number of keyword matches required to pass.
    """

    def __init__(
        self,
        role_keywords: list[str],
        deny_patterns: list[str],
        min_keyword_hits: int = 3,
    ) -> None:
        self._keywords = [k.lower() for k in role_keywords]
        self._deny_patterns = [p.lower() for p in deny_patterns]
        self._min_hits = min_keyword_hits

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, jd_text: str) -> ValidationResult:
        """
        Validate a job description string.

        Returns a ValidationResult indicating pass/fail and diagnostics.
        """
        normalized = self._normalize(jd_text)

        deny_hits = self._check_deny(normalized)
        if deny_hits:
            result = ValidationResult(
                is_pass=False,
                score=0,
                matched_deny_patterns=deny_hits,
                reason=f"Deny pattern(s) matched: {', '.join(deny_hits)}",
            )
            logger.info("JD FAILED — deny pattern(s): %s", deny_hits)
            return result

        kw_hits = self._count_keywords(normalized)
        score = len(kw_hits)
        passed = score >= self._min_hits

        if passed:
            reason = f"Passed with {score} keyword hit(s): {', '.join(kw_hits)}"
            logger.info("JD PASSED — score=%d keywords=%s", score, kw_hits)
        else:
            reason = (
                f"Only {score}/{self._min_hits} required keyword hits: {kw_hits or 'none'}"
            )
            logger.info("JD FAILED — score=%d (need %d)", score, self._min_hits)

        return ValidationResult(
            is_pass=passed,
            score=score,
            matched_keywords=kw_hits,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        """Lower-case and collapse whitespace."""
        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        return text

    def _check_deny(self, text: str) -> list[str]:
        return [p for p in self._deny_patterns if p in text]

    def _count_keywords(self, text: str) -> list[str]:
        return [k for k in self._keywords if k in text]


def build_validator_from_config(config: dict, role: str = "analyst") -> JDValidator:
    """
    Convenience factory that builds a JDValidator from the loaded config dict.

    Args:
        config: full config.yaml dict.
        role:   "analyst" or "engineer" — selects the keyword set.
    """
    val_cfg = config.get("validation", {})
    keyword_sets = val_cfg.get("role_keyword_sets", {})
    keywords = keyword_sets.get(role, [])
    deny_patterns = val_cfg.get("deny_patterns", [])
    min_hits = val_cfg.get("min_keyword_hits", 3)
    return JDValidator(
        role_keywords=keywords,
        deny_patterns=deny_patterns,
        min_keyword_hits=min_hits,
    )
