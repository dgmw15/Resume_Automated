"""
ai/providers/base.py — Common interface all AI providers must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderResult:
    text: str
    model: str
    provider: str
    estimated_cost_usd: float
    raw_usage_tokens: int | None = None


class BaseProvider(ABC):
    """Abstract base for AI provider adapters."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ProviderResult:
        """
        Send a prompt and return a ProviderResult.

        Raises:
            BudgetExceededError: if the daily/monthly cap has been hit.
            RuntimeError: if all retries are exhausted.
        """


class BudgetExceededError(Exception):
    """Raised when a daily or monthly AI spend cap is reached."""
