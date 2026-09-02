"""
ai/critic.py — ATS critic: a second AI call that critiques (never rewrites)
a tailored resume against the job description it was tailored for.

Design: layered on top of the free ai/keyword_coverage.py check, not a
replacement for it. This call goes through ProviderRouter like any other
generation call, so it is budgeted/idempotent/fallback-routed the same way.
Failures here must never fail the job — batch_processor treats this as
best-effort and only logs a warning (see core/batch_processor.py).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ai.prompts import CRITIC_SYSTEM_PROMPT, CRITIC_USER_TEMPLATE
from ai.provider_router import ProviderRouter

logger = logging.getLogger(__name__)

# Parses the 4-line CRITIC_SYSTEM_PROMPT output contract.
_LINE_RE = re.compile(r"^(COVERAGE|MISSING|CONCERNS|VERDICT):\s*(.*)$", re.IGNORECASE | re.MULTILINE)
_VALID_VERDICTS = {"PASS", "WEAK", "FAIL"}


@dataclass
class CritiqueResult:
    coverage_pct: int
    missing: list[str]
    concerns: str
    verdict: str  # "PASS" | "WEAK" | "FAIL" | "UNKNOWN" (UNKNOWN = model didn't follow format)
    raw_text: str


def _parse_critique(text: str) -> CritiqueResult:
    fields = {m.group(1).upper(): m.group(2).strip() for m in _LINE_RE.finditer(text)}

    try:
        coverage_pct = int(re.sub(r"[^\d]", "", fields.get("COVERAGE", "")) or 0)
    except ValueError:
        coverage_pct = 0
    coverage_pct = max(0, min(100, coverage_pct))

    missing_raw = fields.get("MISSING", "none")
    missing = [] if missing_raw.strip().lower() == "none" else [
        s.strip() for s in missing_raw.split(",") if s.strip()
    ]

    verdict = fields.get("VERDICT", "").upper()
    if verdict not in _VALID_VERDICTS:
        verdict = "UNKNOWN"

    return CritiqueResult(
        coverage_pct=coverage_pct,
        missing=missing,
        concerns=fields.get("CONCERNS", ""),
        verdict=verdict,
        raw_text=text,
    )


class AtsCritic:
    """Calls the AI provider to critique a tailored resume. Never rewrites."""

    def __init__(self, router: ProviderRouter) -> None:
        self._router = router

    def critique(
        self,
        job_description: str,
        tailored_resume: str,
        idempotency_key: str | None = None,
        job_id: str | None = None,
    ) -> CritiqueResult:
        prompt = CRITIC_USER_TEMPLATE.format(
            job_description=job_description.strip(),
            tailored_resume=tailored_resume.strip(),
        )
        result = self._router.generate(
            prompt=prompt,
            system_prompt=CRITIC_SYSTEM_PROMPT,
            track="analyst",  # only selects model_map entry; critic prompt is track-agnostic
            idempotency_key=idempotency_key,
            job_id=job_id,
        )
        logger.info(
            "ATS critique OK via %s cost=$%.4f", result.provider, result.estimated_cost_usd
        )
        return _parse_critique(result.text)


if __name__ == "__main__":
    # ponytail: minimal runnable check — see tests/test_critic.py for the real suite
    sample = "COVERAGE: 72\nMISSING: airflow, kafka\nCONCERNS: none\nVERDICT: WEAK\n"
    parsed = _parse_critique(sample)
    assert parsed.coverage_pct == 72
    assert parsed.missing == ["airflow", "kafka"]
    assert parsed.verdict == "WEAK"

    malformed = _parse_critique("the model rambled instead of following the format")
    assert malformed.verdict == "UNKNOWN"
    assert malformed.coverage_pct == 0

    print("critic self-check OK")
