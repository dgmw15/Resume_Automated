"""
ai/keyword_coverage.py — free, deterministic keyword-coverage check.

Diffs the technical skills mentioned in a job description against the
skills present in the tailored resume text. No AI call — reuses the same
regex/positional extractor already used for JD signal extraction, so a
skill is only "covered" if it would show up to the same detector an ATS
keyword scan approximates.

Always run this (it's free); the LLM-based AtsCritic is a separate,
heavier check layered on top.
"""
from __future__ import annotations

from dataclasses import dataclass

from ai.skills_signal_extractor import extract_technical_skills

# Comfortably above len(DEFAULT_SKILL_PATTERNS) so nothing is truncated.
_MAX_ITEMS = 100


@dataclass
class CoverageResult:
    score: float  # matched / total JD skills, 0.0-1.0 (1.0 if the JD has no detectable skills)
    matched: list[str]
    missing: list[str]


def check_coverage(job_description: str, tailored_resume: str) -> CoverageResult:
    jd_skills = extract_technical_skills(job_description, max_items=_MAX_ITEMS)
    if not jd_skills:
        return CoverageResult(score=1.0, matched=[], missing=[])

    resume_skills = set(extract_technical_skills(tailored_resume, max_items=_MAX_ITEMS))
    matched = [s for s in jd_skills if s in resume_skills]
    missing = [s for s in jd_skills if s not in resume_skills]
    return CoverageResult(score=len(matched) / len(jd_skills), matched=matched, missing=missing)


if __name__ == "__main__":
    # ponytail: minimal runnable check — see tests/test_keyword_coverage.py for the real suite
    jd = "Looking for a Data Analyst with SQL, Python, Tableau and AWS experience."
    resume = "Built SQL pipelines in Python. Familiar with dashboards."
    r = check_coverage(jd, resume)
    assert set(r.matched) == {"sql", "python"}
    assert set(r.missing) == {"tableau", "aws"}
    assert 0.0 < r.score < 1.0
    print("keyword_coverage self-check OK:", r)
