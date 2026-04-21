"""
ai/tailor.py — Resume tailoring via the ProviderRouter.

The legacy Vertex AI / Gemini path has been replaced.
"""
from __future__ import annotations

import logging

from ai.provider_router import ProviderRouter
from ai.providers.base import BudgetExceededError, ProviderResult

logger = logging.getLogger(__name__)


class ResumeTailor:
    """
    Generates tailored resumes using the configured AI provider via ProviderRouter.

    Usage:
        tailor = ResumeTailor(router)
        result = tailor.generate(base_resume_text, job_description, track="analyst")
    """

    def __init__(self, router: ProviderRouter) -> None:
        self._router = router

    def generate(
        self,
        base_resume_text: str,
        job_description: str,
        track: str = "analyst",
        system_prompt: str = "",
        user_template: str = "",
        idempotency_key: str | None = None,
        job_id: str | None = None,
    ) -> ProviderResult:
        """
        Generate a tailored resume.

        Args:
            base_resume_text: plain-text base resume.
            job_description:  raw JD text.
            track:            "analyst" or "engineer" — selects model + prompt.
            system_prompt:    override system prompt (supplied by pipeline.py).
            user_template:    override user template (supplied by pipeline.py).
            idempotency_key:  stable key reused across retries to prevent duplicate charges.
            job_id:           used for budget ledger reservation metadata.

        Returns:
            ProviderResult with the tailored text and cost metadata.

        Raises:
            BudgetExceededError: spend cap reached.
            RuntimeError: all providers exhausted.
        """
        prompt = user_template.format(
            job_description=job_description.strip(),
            base_resume=base_resume_text.strip(),
        )

        logger.info("Generating tailored resume for track=%s", track)
        result = self._router.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            track=track,
            idempotency_key=idempotency_key,
            job_id=job_id,
        )
        logger.info(
            "Resume tailored OK via %s model=%s cost=$%.4f",
            result.provider, result.model, result.estimated_cost_usd,
        )
        return result
