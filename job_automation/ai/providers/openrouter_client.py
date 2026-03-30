"""
ai/providers/openrouter_client.py — OpenRouter provider (OpenAI-compatible API).

Requires OPENROUTER_API_KEY environment variable.
"""
from __future__ import annotations

import logging
import os
import time

import requests

from ai.providers.base import BaseProvider, BudgetExceededError, ProviderResult

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Fallback cost estimate when the API doesn't return usage data
_FALLBACK_COST_PER_1K_TOKENS = 0.002
MAX_RETRIES = 3
BASE_WAIT = 10


class OpenRouterProvider(BaseProvider):
    """Calls any model via OpenRouter's OpenAI-compatible endpoint."""

    def __init__(self, budget_guard: "BudgetGuard | None" = None) -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise EnvironmentError("OPENROUTER_API_KEY environment variable is not set.")
        self._api_key = api_key
        self._budget = budget_guard

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ProviderResult:
        if self._budget and self._budget.is_exceeded():
            raise BudgetExceededError(self._budget.exceeded_reason())

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }

        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    OPENROUTER_API_URL, headers=headers, json=payload, timeout=120
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                usage = data.get("usage", {})
                total_tokens = usage.get("total_tokens", 0)
                cost = total_tokens / 1000 * _FALLBACK_COST_PER_1K_TOKENS
                if self._budget:
                    self._budget.record_spend(cost)
                logger.info(
                    "OpenRouter generation OK (attempt %d) model=%s tokens=%d cost=$%.4f",
                    attempt, model, total_tokens, cost,
                )
                return ProviderResult(
                    text=text,
                    model=model,
                    provider="openrouter",
                    estimated_cost_usd=cost,
                    raw_usage_tokens=total_tokens or None,
                )
            except BudgetExceededError:
                raise
            except Exception as exc:
                last_err = exc
                wait = BASE_WAIT * (2 ** (attempt - 1))
                logger.warning(
                    "OpenRouter error attempt %d/%d: %s — retrying in %ds",
                    attempt, MAX_RETRIES, exc, wait,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(wait)

        raise RuntimeError(
            f"OpenRouter failed after {MAX_RETRIES} attempts. Last error: {last_err}"
        )
