"""
ai/provider_router.py — Routes AI generation calls to the configured provider
with budget enforcement and fallback support.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from ai.providers.base import BaseProvider, BudgetExceededError, ProviderResult

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.yaml")


class BudgetGuard:
    """
    In-process spend tracker.  Resets on daily/monthly boundary.
    For simplicity the counters are in-memory — they reset when the process
    restarts.  For persistent tracking write to a sidecar file.
    """

    def __init__(self, daily_cap: float, monthly_cap: float, hard_stop: bool) -> None:
        self._daily_cap = daily_cap
        self._monthly_cap = monthly_cap
        self._hard_stop = hard_stop
        self._daily_spend = 0.0
        self._monthly_spend = 0.0

    def record_spend(self, amount: float) -> None:
        self._daily_spend += amount
        self._monthly_spend += amount
        logger.debug(
            "Budget: +$%.4f  daily=$%.4f/%.2f  monthly=$%.4f/%.2f",
            amount,
            self._daily_spend, self._daily_cap,
            self._monthly_spend, self._monthly_cap,
        )

    def is_exceeded(self) -> bool:
        if not self._hard_stop:
            return False
        return self._daily_spend >= self._daily_cap or self._monthly_spend >= self._monthly_cap

    def exceeded_reason(self) -> str:
        if self._daily_spend >= self._daily_cap:
            return f"Daily cap ${self._daily_cap:.2f} reached (spent ${self._daily_spend:.4f})"
        return f"Monthly cap ${self._monthly_cap:.2f} reached (spent ${self._monthly_spend:.4f})"


class ProviderRouter:
    """
    Selects the configured primary provider, falls back to secondary providers
    on failure, and enforces the budget guard.
    """

    def __init__(self, config: dict) -> None:
        ai_cfg = config.get("ai", {})
        budget_cfg = ai_cfg.get("budget", {})

        self._budget = BudgetGuard(
            daily_cap=float(budget_cfg.get("daily_cap_usd", 5.0)),
            monthly_cap=float(budget_cfg.get("monthly_cap_usd", 50.0)),
            hard_stop=bool(budget_cfg.get("hard_stop", True)),
        )
        self._fallback_order: list[str] = ai_cfg.get(
            "fallback_order", [ai_cfg.get("provider", "anthropic")]
        )
        self._model_map: dict[str, str] = ai_cfg.get("model_map", {})
        self._providers: dict[str, BaseProvider] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        for name in self._fallback_order:
            try:
                provider = self._build_provider(name)
                self._providers[name] = provider
                logger.info("Provider '%s' initialised.", name)
            except EnvironmentError as exc:
                logger.warning("Provider '%s' unavailable: %s", name, exc)

    def _build_provider(self, name: str) -> BaseProvider:
        if name == "anthropic":
            from ai.providers.anthropic_client import AnthropicProvider
            return AnthropicProvider(budget_guard=self._budget)
        if name == "openrouter":
            from ai.providers.openrouter_client import OpenRouterProvider
            return OpenRouterProvider(budget_guard=self._budget)
        raise ValueError(f"Unknown provider: {name!r}")

    def model_for_track(self, track: str) -> str:
        """Return the configured model name for a pipeline track."""
        return self._model_map.get(track, "claude-sonnet-4-6")

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        track: str = "analyst",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ProviderResult:
        """
        Try providers in fallback order.  Returns the first successful result.
        Raises BudgetExceededError immediately if cap hit.
        Raises RuntimeError if all providers fail.
        """
        model = self.model_for_track(track)

        for name in self._fallback_order:
            provider = self._providers.get(name)
            if provider is None:
                continue
            try:
                return provider.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except BudgetExceededError:
                raise
            except Exception as exc:
                logger.warning("Provider '%s' failed: %s — trying next.", name, exc)

        raise RuntimeError("All configured AI providers failed.")
