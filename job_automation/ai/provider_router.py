"""
ai/provider_router.py — Routes AI generation calls to the configured provider
with persistent atomic budget enforcement and fallback support.

Budget enforcement is delegated to core.budget_ledger.BudgetLedger, which
serialises reservations through a file lock so concurrent workers cannot
each see "cap not exceeded" and simultaneously blow past the limit.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

import yaml

from ai.providers.base import BaseProvider, BudgetExceededError, ProviderResult
from core.budget_ledger import BudgetLedger

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.yaml")

# Conservative cost estimate per request used for the pre-call reservation.
# Real cost is confirmed (committed) after the provider responds.
_ESTIMATED_COST_PER_REQUEST_USD = 0.05


class ProviderRouter:
    """
    Selects the configured primary provider, falls back to secondary providers
    on failure, and enforces budget caps via the persistent BudgetLedger.

    Args:
        config:       full config dict (from config.yaml).
        ledger:       optional pre-built BudgetLedger; if None, one is created
                      from the config.  Pass a custom ledger in tests.
        ledger_path:  path for the ledger JSON file (default: budget_ledger.json).
    """

    def __init__(
        self,
        config: dict,
        ledger: Optional[BudgetLedger] = None,
        ledger_path: Optional[Path] = None,
    ) -> None:
        ai_cfg = config.get("ai", {})

        self._fallback_order: list[str] = ai_cfg.get(
            "fallback_order", [ai_cfg.get("provider", "anthropic")]
        )
        self._model_map: dict[str, str] = ai_cfg.get("model_map", {})
        self._providers: dict[str, BaseProvider] = {}

        # Budget ledger (persistent, file-locked)
        if ledger is not None:
            self._ledger = ledger
        else:
            path = ledger_path or Path("budget_ledger.json")
            self._ledger = BudgetLedger.from_config(config, ledger_path=path)

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
            return AnthropicProvider()
        if name == "openrouter":
            from ai.providers.openrouter_client import OpenRouterProvider
            return OpenRouterProvider()
        if name == "claude_code":
            from ai.providers.claude_code_client import ClaudeCodeProvider
            return ClaudeCodeProvider()
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
        idempotency_key: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> ProviderResult:
        """
        Reserve budget, try providers in fallback order, then commit.

        If idempotency_key is provided and already committed in the ledger,
        the call is a no-op replay — returns a stub result without re-charging.

        Raises:
            BudgetExceededError: spend cap would be exceeded.
            RuntimeError: all providers exhausted.
        """
        idem_key = idempotency_key or str(uuid.uuid4())

        # --- Idempotency deduplication ---
        existing_rid = self._ledger.is_idempotency_key_committed(idem_key)
        if existing_rid:
            logger.info(
                "Idempotency key %r already committed (rid=%s) — skipping provider call.",
                idem_key, existing_rid,
            )
            # Return a zero-cost stub so the caller can proceed normally
            return ProviderResult(
                text="[DEDUPLICATED — see original committed result]",
                model=self.model_for_track(track),
                provider="dedup",
                estimated_cost_usd=0.0,
            )

        # --- Budget reservation (blocks if cap would be exceeded) ---
        reservation_id = self._ledger.reserve(
            job_id=job_id or "unknown",
            estimated_usd=_ESTIMATED_COST_PER_REQUEST_USD,
            idempotency_key=idem_key,
        )

        model = self.model_for_track(track)
        result: Optional[ProviderResult] = None

        try:
            for name in self._fallback_order:
                provider = self._providers.get(name)
                if provider is None:
                    continue
                try:
                    result = provider.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    break
                except Exception as exc:
                    logger.warning("Provider '%s' failed: %s — trying next.", name, exc)

            if result is None:
                raise RuntimeError("All configured AI providers failed.")

            # --- Confirm actual cost against the reservation ---
            self._ledger.commit(reservation_id, actual_usd=result.estimated_cost_usd)
            return result

        except BudgetExceededError:
            # Already raised from reserve() — no reservation to release
            raise

        except Exception:
            # Release the reservation so the budget becomes available again
            self._ledger.release(reservation_id, reason="provider error or all failed")
            raise

    @property
    def ledger(self) -> BudgetLedger:
        return self._ledger
