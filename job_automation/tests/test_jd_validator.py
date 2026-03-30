"""Tests for ai/jd_validator.py"""
import pytest
from ai.jd_validator import JDValidator, ValidationResult

ANALYST_KEYWORDS = [
    "sql", "python", "tableau", "power bi", "dashboard",
    "analytics", "metrics", "kpi", "reporting", "data analysis",
]
DENY_PATTERNS = [
    "insurance agent", "financial advisor", "sales agent",
    "commission only", "life insurance",
]
MIN_HITS = 3


@pytest.fixture
def validator():
    return JDValidator(
        role_keywords=ANALYST_KEYWORDS,
        deny_patterns=DENY_PATTERNS,
        min_keyword_hits=MIN_HITS,
    )


class TestJDValidatorPass:
    def test_clearly_technical_jd(self, validator):
        jd = (
            "We are looking for a Data Analyst proficient in SQL, Python, "
            "and Tableau. You will build dashboards, define KPIs, and support "
            "analytics reporting for the product team."
        )
        result = validator.validate(jd)
        assert result.is_pass is True
        assert result.score >= MIN_HITS
        assert len(result.matched_keywords) >= MIN_HITS
        assert result.matched_deny_patterns == []

    def test_score_counts_distinct_keywords(self, validator):
        # Repeating a keyword shouldn't inflate score
        jd = "sql sql sql python python tableau"
        result = validator.validate(jd)
        assert result.score == 3  # sql, python, tableau — each counted once


class TestJDValidatorFail:
    def test_insurance_sales_jd(self, validator):
        jd = (
            "We are recruiting Financial Advisors and Insurance Agents. "
            "Commission only role with life insurance product sales."
        )
        result = validator.validate(jd)
        assert result.is_pass is False
        assert len(result.matched_deny_patterns) > 0
        assert result.score == 0

    def test_insufficient_keyword_hits(self, validator):
        jd = "Looking for someone with SQL skills to join our growing team."
        result = validator.validate(jd)
        assert result.is_pass is False
        assert result.score == 1
        assert result.matched_deny_patterns == []
        assert "sql" in result.matched_keywords


class TestJDValidatorBorderline:
    def test_mixed_jd_borderline_count(self, validator):
        # Exactly at threshold — should pass
        jd = "The role requires SQL, Python, and Tableau experience."
        result = validator.validate(jd)
        assert result.score == 3
        assert result.is_pass is True

    def test_deny_pattern_overrides_keyword_hits(self, validator):
        # Even if keywords are present, deny pattern should fail it
        jd = (
            "This analytics role requires SQL, Python, Tableau. "
            "Note: this is a commission only financial advisor role."
        )
        result = validator.validate(jd)
        assert result.is_pass is False
        assert "commission only" in result.matched_deny_patterns

    def test_case_insensitive_matching(self, validator):
        jd = "SQL AND PYTHON AND TABLEAU DASHBOARD ANALYTICS METRICS"
        result = validator.validate(jd)
        assert result.is_pass is True


class TestJDValidatorEdge:
    def test_empty_jd(self, validator):
        result = validator.validate("")
        assert result.is_pass is False
        assert result.score == 0

    def test_whitespace_only_jd(self, validator):
        result = validator.validate("   \n\t  ")
        assert result.is_pass is False

    def test_validation_result_is_dataclass(self, validator):
        result = validator.validate("sql python tableau")
        assert isinstance(result, ValidationResult)
        assert isinstance(result.matched_keywords, list)
        assert isinstance(result.matched_deny_patterns, list)
