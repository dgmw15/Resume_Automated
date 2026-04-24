"""
ai/employment_filter.py — Deterministic employment-type filter.

Detects internship and contract roles from job title, description, and tags,
then applies independent toggles from config. Runs before JD technical validation
so filtered rows never reach the AI queue.

Status values written to tracker:
  PASSED   — role is allowed through (permanent / unknown with allow policy)
  FILTERED — role is excluded by an active toggle
  SKIPPED  — employment filtering is disabled in config

Employment type heuristics (Prompt S4)
---------------------------------------
  internship  — intern, internship, trainee, student, attachment, industrial placement
  contract    — contract, contractor, 6-month, 12-month, fixed-term, fixed term, temp, temporary
  permanent   — permanent, full-time, full time (when no contract/intern signals)
  unknown     — cannot be determined; follows unknown_policy

All matching is case-insensitive, whole-word aware where possible.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_INTERNSHIP_PATTERNS = [
    r"\bintern\b",
    r"\binternship\b",
    r"\btrainee\b",
    r"\bstudent\b",
    r"\battachment\b",
    r"\bindustrial\s+placement\b",
    r"\bstudent\s+programme\b",
]

_CONTRACT_PATTERNS = [
    r"\bcontract\b",
    r"\bcontractor\b",
    r"\b6[\-\s]month\b",
    r"\b12[\-\s]month\b",
    r"\bfixed[\-\s]term\b",
    r"\btemporary\b",
    r"\btemp\b",
]

_INTERNSHIP_RE = re.compile("|".join(_INTERNSHIP_PATTERNS), re.IGNORECASE)
_CONTRACT_RE   = re.compile("|".join(_CONTRACT_PATTERNS),   re.IGNORECASE)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class FilterResult:
    status: str                    # "PASSED", "FILTERED", "SKIPPED"
    reason: str
    employment_type_raw: str       # matched phrase(s), or ""
    employment_type_normalized: str  # "internship", "contract", "permanent", "unknown"


# ---------------------------------------------------------------------------
# Filter class
# ---------------------------------------------------------------------------

class EmploymentFilter:
    """
    Deterministic employment-type filter driven by config.

    Args:
        enabled:            master toggle; if False all results are SKIPPED.
        exclude_internship: filter out internship/trainee roles.
        exclude_contract:   filter out contract/fixed-term roles.
        unknown_policy:     "allow" (default) or "deny" for unclassified roles.
    """

    def __init__(
        self,
        enabled: bool = True,
        exclude_internship: bool = True,
        exclude_contract: bool = False,
        unknown_policy: str = "allow",
    ) -> None:
        self._enabled = enabled
        self._exclude_internship = exclude_internship
        self._exclude_contract = exclude_contract
        self._unknown_policy = unknown_policy.lower()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def classify(self, title: str, description: str = "", tags: str = "") -> FilterResult:
        """
        Classify a job listing and return a FilterResult.

        Args:
            title:       job title string.
            description: raw job description text.
            tags:        any additional tag/category text from the portal.
        """
        if not self._enabled:
            return FilterResult(
                status="SKIPPED",
                reason="Employment filtering is disabled.",
                employment_type_raw="",
                employment_type_normalized="unknown",
            )

        combined = f"{title} {description} {tags}"

        # Detect type
        intern_match  = _INTERNSHIP_RE.search(combined)
        contract_match = _CONTRACT_RE.search(combined)

        if intern_match:
            emp_type = "internship"
            matched_phrase = intern_match.group(0)
        elif contract_match:
            emp_type = "contract"
            matched_phrase = contract_match.group(0)
        else:
            emp_type = "unknown"
            matched_phrase = ""

        # Apply toggles
        if emp_type == "internship" and self._exclude_internship:
            return FilterResult(
                status="FILTERED",
                reason=f"Internship role excluded (matched: {matched_phrase!r}).",
                employment_type_raw=matched_phrase,
                employment_type_normalized=emp_type,
            )

        if emp_type == "contract" and self._exclude_contract:
            return FilterResult(
                status="FILTERED",
                reason=f"Contract role excluded (matched: {matched_phrase!r}).",
                employment_type_raw=matched_phrase,
                employment_type_normalized=emp_type,
            )

        if emp_type == "unknown" and self._unknown_policy == "deny":
            return FilterResult(
                status="FILTERED",
                reason="Employment type unknown and unknown_policy is 'deny'.",
                employment_type_raw="",
                employment_type_normalized="unknown",
            )

        return FilterResult(
            status="PASSED",
            reason=f"Employment type {emp_type!r} — allowed.",
            employment_type_raw=matched_phrase,
            employment_type_normalized=emp_type,
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict) -> "EmploymentFilter":
        """Build an EmploymentFilter from the full config dict."""
        ef_cfg = config.get("employment_filter", {})
        return cls(
            enabled=bool(ef_cfg.get("enabled", True)),
            exclude_internship=bool(ef_cfg.get("exclude_internship", True)),
            exclude_contract=bool(ef_cfg.get("exclude_contract", False)),
            unknown_policy=str(ef_cfg.get("unknown_policy", "allow")),
        )
