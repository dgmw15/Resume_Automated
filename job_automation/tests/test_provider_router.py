"""Tests for ai/provider_router.py"""
import pytest
from unittest.mock import MagicMock, patch

from ai.provider_router import BudgetGuard, ProviderRouter
from ai.providers.base import BudgetExceededError, ProviderResult


class TestBudgetGuard:
    def test_not_exceeded_initially(self):
        bg = BudgetGuard(daily_cap=5.0, monthly_cap=50.0, hard_stop=True)
        assert bg.is_exceeded() is False

    def test_daily_cap_exceeded(self):
        bg = BudgetGuard(daily_cap=1.0, monthly_cap=50.0, hard_stop=True)
        bg.record_spend(1.01)
        assert bg.is_exceeded() is True

    def test_monthly_cap_exceeded(self):
        bg = BudgetGuard(daily_cap=100.0, monthly_cap=5.0, hard_stop=True)
        bg.record_spend(5.01)
        assert bg.is_exceeded() is True

    def test_hard_stop_false_never_exceeded(self):
        bg = BudgetGuard(daily_cap=0.01, monthly_cap=0.01, hard_stop=False)
        bg.record_spend(999.0)
        assert bg.is_exceeded() is False

    def test_exceeded_reason_daily(self):
        bg = BudgetGuard(daily_cap=1.0, monthly_cap=50.0, hard_stop=True)
        bg.record_spend(2.0)
        assert "Daily cap" in bg.exceeded_reason()

    def test_cumulative_spend(self):
        bg = BudgetGuard(daily_cap=10.0, monthly_cap=100.0, hard_stop=True)
        bg.record_spend(4.0)
        bg.record_spend(4.0)
        assert bg.is_exceeded() is False
        bg.record_spend(3.0)
        assert bg.is_exceeded() is True


class TestProviderRouter:
    def _make_config(self, provider="anthropic"):
        return {
            "ai": {
                "provider": provider,
                "fallback_order": [provider],
                "model_map": {"analyst": "claude-sonnet-4-6", "engineer": "claude-sonnet-4-6"},
                "budget": {"daily_cap_usd": 5.0, "monthly_cap_usd": 50.0, "hard_stop": True},
            }
        }

    def test_generate_returns_provider_result(self):
        config = self._make_config("anthropic")
        mock_result = ProviderResult(
            text="tailored resume",
            model="claude-sonnet-4-6",
            provider="anthropic",
            estimated_cost_usd=0.01,
        )
        with patch("ai.provider_router.ProviderRouter._build_provider") as mock_build:
            mock_provider = MagicMock()
            mock_provider.generate.return_value = mock_result
            mock_build.return_value = mock_provider

            router = ProviderRouter(config)
            result = router.generate("prompt", "system", track="analyst")

        assert result.text == "tailored resume"
        assert result.provider == "anthropic"

    def test_budget_exceeded_raises(self):
        config = self._make_config("anthropic")
        with patch("ai.provider_router.ProviderRouter._build_provider") as mock_build:
            mock_provider = MagicMock()
            mock_provider.generate.side_effect = BudgetExceededError("cap hit")
            mock_build.return_value = mock_provider

            router = ProviderRouter(config)
            with pytest.raises(BudgetExceededError):
                router.generate("prompt", "system", track="analyst")

    def test_fallback_to_second_provider(self):
        config = {
            "ai": {
                "provider": "anthropic",
                "fallback_order": ["anthropic", "openrouter"],
                "model_map": {"analyst": "claude-sonnet-4-6"},
                "budget": {"daily_cap_usd": 5.0, "monthly_cap_usd": 50.0, "hard_stop": True},
            }
        }
        mock_result = ProviderResult(
            text="ok", model="gpt-4", provider="openrouter",
            estimated_cost_usd=0.005,
        )
        call_count = {"n": 0}

        def build_side_effect(name):
            mock = MagicMock()
            if name == "anthropic":
                mock.generate.side_effect = RuntimeError("anthropic down")
            else:
                mock.generate.return_value = mock_result
            return mock

        with patch("ai.provider_router.ProviderRouter._build_provider", side_effect=build_side_effect):
            router = ProviderRouter(config)
            result = router.generate("prompt", "system", track="analyst")

        assert result.provider == "openrouter"

    def test_all_providers_fail_raises_runtime_error(self):
        config = self._make_config("anthropic")
        with patch("ai.provider_router.ProviderRouter._build_provider") as mock_build:
            mock_provider = MagicMock()
            mock_provider.generate.side_effect = RuntimeError("fail")
            mock_build.return_value = mock_provider

            router = ProviderRouter(config)
            with pytest.raises(RuntimeError, match="All configured AI providers failed"):
                router.generate("prompt", "system", track="analyst")
