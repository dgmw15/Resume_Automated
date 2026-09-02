from ai.keyword_coverage import check_coverage


def test_full_coverage():
    jd = "Need SQL and Python."
    resume = "Wrote SQL queries in Python daily."
    result = check_coverage(jd, resume)
    assert result.score == 1.0
    assert result.missing == []
    assert set(result.matched) == {"sql", "python"}


def test_partial_coverage():
    jd = "Looking for SQL, Python, Tableau and AWS experience."
    resume = "Built SQL pipelines in Python."
    result = check_coverage(jd, resume)
    assert set(result.matched) == {"sql", "python"}
    assert set(result.missing) == {"tableau", "aws"}
    assert 0.0 < result.score < 1.0


def test_no_jd_skills_is_full_coverage():
    result = check_coverage("General role, no specific tech mentioned.", "Some resume text.")
    assert result.score == 1.0
    assert result.matched == []
    assert result.missing == []


def test_zero_coverage():
    jd = "Requires Kafka and Databricks."
    resume = "Managed a retail store."
    result = check_coverage(jd, resume)
    assert result.score == 0.0
    assert set(result.missing) == {"kafka", "databricks"}
