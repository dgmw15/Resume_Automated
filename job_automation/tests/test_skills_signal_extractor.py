from ai.skills_signal_extractor import extract_technical_skills


def test_extract_technical_skills_regex_and_positional() -> None:
    jd = """
Required Skills:
- SQL, Python, Airflow
- Spark on Databricks
Nice to have: Power BI
"""
    skills = extract_technical_skills(jd)

    assert "sql" in skills
    assert "python" in skills
    assert "airflow" in skills
    assert "spark" in skills
    assert "databricks" in skills
    assert "power bi" in skills


def test_extract_technical_skills_empty() -> None:
    assert extract_technical_skills("") == []


def test_extract_technical_skills_custom_patterns() -> None:
    jd = "Strong Rust and Terraform skills required"
    patterns = [
        ("rust", r"\brust\b"),
        ("terraform", r"\bterraform\b"),
    ]
    skills = extract_technical_skills(jd, skill_patterns=patterns)
    assert skills == ["rust", "terraform"]
