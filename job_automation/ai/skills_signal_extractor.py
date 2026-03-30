from __future__ import annotations

import re

# Ordered by importance and frequency in technical JDs
DEFAULT_SKILL_PATTERNS: list[tuple[str, str]] = [
    ("sql", r"\bsql\b"),
    ("python", r"\bpython\b"),
    ("tableau", r"\btableau\b"),
    ("power bi", r"\bpower\s*bi\b|\bpbi\b"),
    ("excel", r"\bexcel\b"),
    ("etl", r"\betl\b|\belt\b"),
    ("airflow", r"\bairflow\b"),
    ("dbt", r"\bdbt\b"),
    ("spark", r"\bspark\b"),
    ("kafka", r"\bkafka\b"),
    ("databricks", r"\bdatabricks\b"),
    ("snowflake", r"\bsnowflake\b"),
    ("bigquery", r"\bbigquery\b"),
    ("redshift", r"\bredshift\b"),
    ("aws", r"\baws\b|\bamazon\s+web\s+services\b"),
    ("gcp", r"\bgcp\b|\bgoogle\s+cloud\b"),
    ("azure", r"\bazure\b"),
    ("git", r"\bgit\b"),
    ("rest api", r"\brest\s*api\b|\bapis?\b"),
    ("docker", r"\bdocker\b"),
    ("kubernetes", r"\bkubernetes\b|\bk8s\b"),
]

HEADING_HINTS = (
    "skill",
    "requirement",
    "qualification",
    "tech stack",
    "technology",
    "must have",
    "nice to have",
)

STOP_TOKENS = {
    "and", "or", "with", "for", "the", "to", "in", "of", "on", "a", "an", "is", "are", "be",
    "experience", "required", "preferred", "strong", "good", "knowledge", "skills", "ability",
}

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{1,}")


def _positional_candidates(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    candidates: list[str] = []

    for i, line in enumerate(lines):
        lowered = line.lower()
        if any(h in lowered for h in HEADING_HINTS):
            segment = [line]
            segment.extend(lines[i + 1:i + 4])
            joined = " ".join(segment)
            candidates.extend(TOKEN_RE.findall(joined))

    return candidates


def _normalize_token(token: str) -> str:
    return token.strip().lower().replace("_", " ")


def extract_technical_skills(
    job_description: str,
    max_items: int = 15,
    skill_patterns: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Extract technical skills via regex + positional hints.

    Returns canonical skill labels in a stable, deduplicated order.
    """
    text = job_description or ""
    lowered = text.lower()
    patterns = skill_patterns or DEFAULT_SKILL_PATTERNS

    found: list[str] = []
    seen: set[str] = set()

    # 1) Regex-driven canonical extraction
    for canonical, pattern in patterns:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            if canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
            if len(found) >= max_items:
                return found

    # 2) Positional extraction for additional skills near requirement headings
    positional = _positional_candidates(text)
    lookup = {canonical: re.compile(pattern, re.IGNORECASE) for canonical, pattern in patterns}

    for token in positional:
        normalized = _normalize_token(token)
        if normalized in STOP_TOKENS or len(normalized) < 2:
            continue

        for canonical, compiled in lookup.items():
            if compiled.search(normalized) and canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
                break

        if len(found) >= max_items:
            break

    return found
