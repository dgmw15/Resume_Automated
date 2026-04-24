"""
core/salary_parser.py — Deterministic salary parsing for job listings.

Parses salary text extracted from CareersFuture DOM into structured fields:
  salary_raw      — raw text captured from the DOM
  salary_min      — numeric minimum (float)
  salary_max      — numeric maximum (float)
  salary_currency — ISO currency code (e.g. "SGD")
  salary_period   — "monthly", "annual", or "unknown"
  salary_status   — "OK" | "MISSING" | "AMBIGUOUS" | "ERROR"

Design rules
------------
- No AI calls; fully deterministic regex + heuristics.
- Never raises on unparseable input — returns AMBIGUOUS or MISSING status.
- If only a single amount is found, salary_min == salary_max.
- Strips thousands-separators and currency symbols before parsing.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS = {"$": "SGD", "S$": "SGD", "SGD": "SGD", "USD": "USD", "£": "GBP", "€": "EUR"}
_PERIOD_ANNUAL_RE = re.compile(r"\b(per\s+year|annual|yearly|p\.a\.?)\b", re.IGNORECASE)
_PERIOD_MONTHLY_RE = re.compile(r"\b(per\s+month|monthly|p\.m\.?|/month|/mo)\b", re.IGNORECASE)

# Matches numbers like "4,500" or "4500" or "4.5k"
_AMOUNT_RE = re.compile(r"[\$S]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?:k\b)?", re.IGNORECASE)
_K_SUFFIX_RE = re.compile(r"(\d+(?:\.\d+)?)k\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SalaryResult:
    salary_raw: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "SGD"
    salary_period: str = "unknown"
    salary_status: str = "MISSING"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_currency_and_amount(text: str) -> tuple[str, Optional[float]]:
    """
    Extract a currency code and numeric amount from a text token.

    Returns (currency_code, amount) or (default_currency, None) on failure.

    Examples:
        "$4,500"   → ("SGD", 4500.0)
        "S$6,500"  → ("SGD", 6500.0)
        "4500"     → ("SGD", 4500.0)
        "4.5k"     → ("SGD", 4500.0)
        "To"       → ("SGD", None)
    """
    if not text or not isinstance(text, str):
        return ("SGD", None)

    cleaned = text.strip()
    currency = "SGD"  # default

    # Detect currency prefix
    for symbol, code in sorted(_CURRENCY_SYMBOLS.items(), key=lambda x: -len(x[0])):
        if cleaned.upper().startswith(symbol.upper()):
            currency = code
            cleaned = cleaned[len(symbol):].strip()
            break

    # Handle "k" suffix (e.g. "4.5k" → 4500)
    k_match = _K_SUFFIX_RE.match(cleaned.replace(",", ""))
    if k_match:
        return (currency, float(k_match.group(1)) * 1000)

    # Strip commas and try to parse as float
    numeric_str = cleaned.replace(",", "").strip()
    try:
        return (currency, float(numeric_str))
    except ValueError:
        return (currency, None)


def _infer_period(raw_text: str) -> str:
    """Infer salary period from surrounding text."""
    if _PERIOD_ANNUAL_RE.search(raw_text):
        return "annual"
    if _PERIOD_MONTHLY_RE.search(raw_text):
        return "monthly"
    return "unknown"


def parse_salary_range(
    raw_text: str,
    min_text: str = "",
    max_text: str = "",
    default_currency: str = "SGD",
    enable_period_inference: bool = True,
) -> SalaryResult:
    """
    Parse a salary range from raw DOM text and optional min/max token strings.

    CareersFuture DOM structure:
      - raw_text: full text of span[data-testid="salary-range"], e.g. "$4,500 to $6,500"
      - min_text: first span.dib text (e.g. "$4,500")
      - max_text: second span.dib text (may include "to" label, e.g. "to $6,500")

    Status codes:
      OK        — both min and max (or single amount) parsed successfully
      MISSING   — no salary wrapper found or empty raw_text
      AMBIGUOUS — text present but no numeric amounts could be extracted
      ERROR     — unexpected exception during parsing
    """
    result = SalaryResult(salary_raw=raw_text, salary_currency=default_currency)

    if not raw_text or not raw_text.strip():
        result.salary_status = "MISSING"
        return result

    try:
        # Strip "to" from max_text (CareersFuture nests it in the second span)
        clean_max = re.sub(r"^\s*to\s*", "", max_text, flags=re.IGNORECASE).strip()

        # Determine period from full raw text
        if enable_period_inference:
            result.salary_period = _infer_period(raw_text)

        # Parse min amount
        currency_min, min_val = parse_currency_and_amount(min_text)
        currency_max, max_val = parse_currency_and_amount(clean_max)

        # If span-level tokens failed, fall back to extracting from raw_text
        if min_val is None and max_val is None:
            amounts = []
            for m in _AMOUNT_RE.finditer(raw_text):
                _, val = parse_currency_and_amount(m.group(0))
                if val is not None and val > 0:
                    amounts.append(val)
            if not amounts:
                logger.debug("No numeric amounts found in salary text: %r", raw_text)
                result.salary_status = "AMBIGUOUS"
                return result
            min_val = amounts[0]
            max_val = amounts[-1] if len(amounts) > 1 else amounts[0]

        # If only min is found, set max = min
        if min_val is not None and max_val is None:
            max_val = min_val
        if max_val is not None and min_val is None:
            min_val = max_val

        result.salary_min = min_val
        result.salary_max = max_val
        result.salary_currency = currency_min or currency_max or default_currency
        result.salary_status = "OK"
        logger.debug(
            "Salary parsed OK: %s %.0f–%.0f %s",
            result.salary_currency, result.salary_min, result.salary_max, result.salary_period,
        )

    except Exception as exc:
        logger.warning("Unexpected salary parse error for text %r: %s", raw_text, exc)
        result.salary_status = "ERROR"

    return result
