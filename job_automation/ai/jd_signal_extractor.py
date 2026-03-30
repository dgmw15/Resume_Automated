from __future__ import annotations

from dataclasses import dataclass
import re


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_YEARS_RE = re.compile(r"(\d+)\+?\s+years?", re.IGNORECASE)


@dataclass
class JdSignals:
    keywords: list[str]
    responsibilities: list[str]
    requirements: list[str]
    years_experience: int | None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _top_matching_keywords(text: str, keyword_pool: list[str], limit: int = 12) -> list[str]:
    lowered = text.lower()
    matched: list[str] = []
    seen: set[str] = set()
    for kw in keyword_pool:
        key = kw.strip().lower()
        if not key or key in seen:
            continue
        if key in lowered:
            seen.add(key)
            matched.append(kw.strip())
            if len(matched) >= limit:
                break
    return matched


def _pick_sentences(text: str, include_tokens: tuple[str, ...], limit: int = 5) -> list[str]:
    sentences = _SENTENCE_SPLIT_RE.split(_normalize(text))
    picked: list[str] = []
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        lowered = s.lower()
        if any(token in lowered for token in include_tokens):
            picked.append(s)
            if len(picked) >= limit:
                break
    return picked


def _extract_years_experience(text: str) -> int | None:
    matches = _YEARS_RE.findall(text)
    if not matches:
        return None
    values = [int(m) for m in matches]
    return max(values) if values else None


def extract_jd_signals(
    job_description: str,
    keyword_pool: list[str],
    keyword_limit: int = 12,
) -> JdSignals:
    """Extract compact, prompt-friendly signals from a raw job description."""
    normalized = _normalize(job_description)
    keywords = _top_matching_keywords(normalized, keyword_pool, limit=keyword_limit)
    responsibilities = _pick_sentences(
        normalized,
        include_tokens=("responsible", "responsibilities", "own", "lead", "deliver", "build", "design"),
        limit=5,
    )
    requirements = _pick_sentences(
        normalized,
        include_tokens=("require", "required", "must", "qualification", "experience", "skills"),
        limit=5,
    )
    years_experience = _extract_years_experience(normalized)

    return JdSignals(
        keywords=keywords,
        responsibilities=responsibilities,
        requirements=requirements,
        years_experience=years_experience,
    )
