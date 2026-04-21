"""
ai/providers/anthropic_client.py — Anthropic Claude provider.

Requires ANTHROPIC_API_KEY environment variable.
"""
from __future__ import annotations

import logging
import os
import re
import time

import anthropic

from ai.providers.base import BaseProvider, BudgetExceededError, ProviderResult

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (input/output blended) for claude-sonnet-4-6
# Adjust if pricing changes.
_COST_PER_1M_INPUT = 3.00
_COST_PER_1M_OUTPUT = 15.00

MAX_RETRIES = 3
BASE_WAIT = 10  # seconds

_MARKDOWN_STRIP_RE = re.compile(r"(\*{1,3}|_{1,3}|`{1,3}|~~|#{1,6}\s?)")


def _strip_markdown(text: str) -> str:
    """Remove markdown decorators the model may emit despite prompt instructions."""
    return _MARKDOWN_STRIP_RE.sub("", text)


class AnthropicProvider(BaseProvider):
    """Calls Claude via the Anthropic Messages API.

    Budget enforcement is handled upstream by ProviderRouter / BudgetLedger.
    This class is a pure "call the API and return a result" adapter.
    """

    def __init__(self) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set.")
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ProviderResult:
        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = _strip_markdown(response.content[0].text.strip())
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                total_tokens = input_tokens + output_tokens
                cost = (
                    input_tokens / 1_000_000 * _COST_PER_1M_INPUT
                    + output_tokens / 1_000_000 * _COST_PER_1M_OUTPUT
                )
                logger.info(
                    "Anthropic generation OK (attempt %d) tokens=%d cost=$%.4f",
                    attempt, total_tokens, cost,
                )
                return ProviderResult(
                    text=text,
                    model=model,
                    provider="anthropic",
                    estimated_cost_usd=cost,
                    raw_usage_tokens=total_tokens,
                )
            except Exception as exc:
                last_err = exc
                wait = BASE_WAIT * (2 ** (attempt - 1))
                logger.warning(
                    "Anthropic error attempt %d/%d: %s — retrying in %ds",
                    attempt, MAX_RETRIES, exc, wait,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(wait)

        raise RuntimeError(
            f"Anthropic failed after {MAX_RETRIES} attempts. Last error: {last_err}"
        )
