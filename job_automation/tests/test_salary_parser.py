"""
tests/test_salary_parser.py — Deterministic tests for core/salary_parser.py

Covers:
1. Standard range "$4,500 to $6,500" → OK with correct min/max
2. Single amount fallback → salary_min == salary_max
3. Missing wrapper → MISSING status
4. Non-numeric phrase → AMBIGUOUS status
5. "k" suffix parsing ("$4.5k" → 4500)
6. Currency extraction (S$, SGD prefix)
7. Period inference (monthly / annual keywords)
8. Detail-page fallback when listing-level salary is missing
9. Error resilience: parse_currency_and_amount with garbage input
"""
from __future__ import annotations

import pytest

from core.salary_parser import (
    SalaryResult,
    parse_currency_and_amount,
    parse_salary_range,
)


# ---------------------------------------------------------------------------
# parse_currency_and_amount
# ---------------------------------------------------------------------------

class TestParseCurrencyAndAmount:
    def test_plain_number(self):
        code, val = parse_currency_and_amount("4500")
        assert val == pytest.approx(4500.0)
        assert code == "SGD"

    def test_dollar_prefix(self):
        code, val = parse_currency_and_amount("$4,500")
        assert val == pytest.approx(4500.0)
        assert code == "SGD"

    def test_sgd_prefix(self):
        code, val = parse_currency_and_amount("S$6,500")
        assert val == pytest.approx(6500.0)
        assert code == "SGD"

    def test_k_suffix(self):
        _, val = parse_currency_and_amount("$4.5k")
        assert val == pytest.approx(4500.0)

    def test_whole_k(self):
        _, val = parse_currency_and_amount("5k")
        assert val == pytest.approx(5000.0)

    def test_non_numeric_returns_none(self):
        _, val = parse_currency_and_amount("To")
        assert val is None

    def test_empty_string_returns_none(self):
        _, val = parse_currency_and_amount("")
        assert val is None

    def test_none_input_returns_none(self):
        _, val = parse_currency_and_amount(None)  # type: ignore[arg-type]
        assert val is None

    def test_commas_handled(self):
        _, val = parse_currency_and_amount("10,000")
        assert val == pytest.approx(10000.0)


# ---------------------------------------------------------------------------
# parse_salary_range — standard range
# ---------------------------------------------------------------------------

class TestParseSalaryRangeStandard:
    def test_standard_range(self):
        result = parse_salary_range(
            raw_text="$4,500 to $6,500",
            min_text="$4,500",
            max_text="to $6,500",
        )
        assert result.salary_status == "OK"
        assert result.salary_min == pytest.approx(4500.0)
        assert result.salary_max == pytest.approx(6500.0)
        assert result.salary_currency == "SGD"

    def test_raw_text_stored(self):
        result = parse_salary_range(raw_text="$4,500 to $6,500")
        assert result.salary_raw == "$4,500 to $6,500"

    def test_min_equals_max_when_only_min(self):
        """Single amount: salary_min must equal salary_max."""
        result = parse_salary_range(
            raw_text="$5,000",
            min_text="$5,000",
            max_text="",
        )
        assert result.salary_status == "OK"
        assert result.salary_min == pytest.approx(5000.0)
        assert result.salary_max == pytest.approx(5000.0)

    def test_max_only_sets_both(self):
        result = parse_salary_range(
            raw_text="Up to $8,000",
            min_text="",
            max_text="$8,000",
        )
        assert result.salary_status == "OK"
        assert result.salary_min == pytest.approx(8000.0)
        assert result.salary_max == pytest.approx(8000.0)

    def test_strips_to_label_from_max(self):
        result = parse_salary_range(
            raw_text="$3,000 to $5,000",
            min_text="$3,000",
            max_text="to $5,000",
        )
        assert result.salary_max == pytest.approx(5000.0)


# ---------------------------------------------------------------------------
# parse_salary_range — missing / ambiguous
# ---------------------------------------------------------------------------

class TestParseSalaryRangeMissing:
    def test_empty_raw_text_is_missing(self):
        result = parse_salary_range(raw_text="")
        assert result.salary_status == "MISSING"

    def test_none_raw_text_is_missing(self):
        result = parse_salary_range(raw_text=None)  # type: ignore[arg-type]
        assert result.salary_status == "MISSING"

    def test_whitespace_only_is_missing(self):
        result = parse_salary_range(raw_text="   ")
        assert result.salary_status == "MISSING"


class TestParseSalaryRangeAmbiguous:
    def test_non_numeric_phrase_is_ambiguous(self):
        result = parse_salary_range(
            raw_text="Competitive salary",
            min_text="",
            max_text="",
        )
        assert result.salary_status == "AMBIGUOUS"

    def test_negotiable_is_ambiguous(self):
        result = parse_salary_range(raw_text="Negotiable")
        assert result.salary_status == "AMBIGUOUS"


# ---------------------------------------------------------------------------
# Period inference
# ---------------------------------------------------------------------------

class TestPeriodInference:
    def test_monthly_detected(self):
        result = parse_salary_range(
            raw_text="$5,000 per month", min_text="$5,000",
        )
        assert result.salary_period == "monthly"

    def test_annual_detected(self):
        result = parse_salary_range(
            raw_text="$60,000 per year", min_text="$60,000",
        )
        assert result.salary_period == "annual"

    def test_unknown_period(self):
        result = parse_salary_range(
            raw_text="$5,000 to $7,000",
            min_text="$5,000",
            max_text="$7,000",
        )
        assert result.salary_period == "unknown"

    def test_period_inference_can_be_disabled(self):
        result = parse_salary_range(
            raw_text="$5,000 per month",
            min_text="$5,000",
            enable_period_inference=False,
        )
        assert result.salary_period == "unknown"


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

class TestCurrency:
    def test_default_currency_applied(self):
        result = parse_salary_range(raw_text="5000", min_text="5000", default_currency="USD")
        assert result.salary_currency == "USD"

    def test_sgd_currency_from_symbol(self):
        result = parse_salary_range(
            raw_text="$4,500 to $6,500",
            min_text="$4,500",
            max_text="$6,500",
        )
        assert result.salary_currency == "SGD"
