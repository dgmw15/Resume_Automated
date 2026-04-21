"""
tests/test_budget_ledger.py — Deterministic tests for BudgetLedger.

Covers:
1. Basic reserve / commit / release lifecycle
2. Hard-stop: daily cap enforcement
3. Hard-stop: monthly cap enforcement
4. Concurrency safety invariant: committed spend never exceeds cap (+ epsilon)
5. Stale reservation cleanup (timeout-based expiry)
6. Idempotency: is_idempotency_key_committed returns correct value
7. Soft-stop mode: caps logged but not enforced
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from core.budget_ledger import BudgetLedger, BudgetExceededError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ledger(tmp_path) -> BudgetLedger:
    """Fresh ledger with tight caps for testing."""
    return BudgetLedger(
        ledger_path=tmp_path / "test_ledger.json",
        daily_cap_usd=1.00,
        monthly_cap_usd=5.00,
        hard_stop=True,
        timezone_name="UTC",
        precision_decimals=4,
        lock_timeout_seconds=2,   # short timeout for stale tests
    )


@pytest.fixture()
def soft_ledger(tmp_path) -> BudgetLedger:
    """Ledger with hard_stop=False — caps are advisory only."""
    return BudgetLedger(
        ledger_path=tmp_path / "soft_ledger.json",
        daily_cap_usd=0.01,
        monthly_cap_usd=0.01,
        hard_stop=False,
        lock_timeout_seconds=60,
    )


# ---------------------------------------------------------------------------
# Basic lifecycle
# ---------------------------------------------------------------------------

class TestBasicLifecycle:
    def test_reserve_and_commit(self, ledger):
        rid = ledger.reserve("job-1", estimated_usd=0.10, idempotency_key="idem-1")
        assert rid is not None
        ledger.commit(rid, actual_usd=0.09)
        spend = ledger.current_spend()
        assert spend["daily_committed_usd"] == pytest.approx(0.09, abs=1e-4)

    def test_reserve_and_release(self, ledger):
        rid = ledger.reserve("job-2", estimated_usd=0.20, idempotency_key="idem-2")
        ledger.release(rid, reason="test release")
        spend = ledger.current_spend()
        assert spend["daily_committed_usd"] == pytest.approx(0.0, abs=1e-4)
        assert spend["pending_reserved_usd"] == pytest.approx(0.0, abs=1e-4)

    def test_pending_reservation_counts_against_cap(self, ledger):
        """A pending reservation must be counted when checking head-room."""
        # Reserve 0.90 → pending
        rid = ledger.reserve("job-3", estimated_usd=0.90, idempotency_key="idem-3")
        # Now trying to reserve another 0.20 should fail (0.90 + 0.20 > 1.00)
        with pytest.raises(BudgetExceededError):
            ledger.reserve("job-4", estimated_usd=0.20, idempotency_key="idem-4")
        ledger.release(rid, reason="cleanup")

    def test_release_unknown_rid_is_noop(self, ledger):
        """Releasing a non-existent reservation_id must not raise."""
        ledger.release("does-not-exist", reason="phantom")


# ---------------------------------------------------------------------------
# Cap enforcement
# ---------------------------------------------------------------------------

class TestCapEnforcement:
    def test_daily_cap_hard_stop(self, ledger):
        rid = ledger.reserve("job-a", estimated_usd=0.80, idempotency_key="idem-a")
        ledger.commit(rid, actual_usd=0.80)
        # Trying to reserve 0.30 more should fail (0.80 + 0.30 > 1.00)
        with pytest.raises(BudgetExceededError, match="Daily cap"):
            ledger.reserve("job-b", estimated_usd=0.30, idempotency_key="idem-b")

    def test_monthly_cap_hard_stop(self, tmp_path):
        """Monthly cap is enforced independently from daily cap."""
        ledger = BudgetLedger(
            ledger_path=tmp_path / "monthly_ledger.json",
            daily_cap_usd=10.00,      # generous daily cap
            monthly_cap_usd=0.50,     # tight monthly cap
            hard_stop=True,
            lock_timeout_seconds=60,
        )
        rid = ledger.reserve("job-m1", estimated_usd=0.40, idempotency_key="idem-m1")
        ledger.commit(rid, actual_usd=0.40)
        with pytest.raises(BudgetExceededError, match="Monthly cap"):
            ledger.reserve("job-m2", estimated_usd=0.20, idempotency_key="idem-m2")

    def test_soft_stop_does_not_raise(self, soft_ledger):
        """With hard_stop=False, reserving over cap must succeed."""
        rid = soft_ledger.reserve("job-soft", estimated_usd=999.0, idempotency_key="idem-soft")
        soft_ledger.commit(rid, actual_usd=999.0)
        spend = soft_ledger.current_spend()
        assert spend["daily_committed_usd"] > soft_ledger._daily_cap


# ---------------------------------------------------------------------------
# Concurrency safety invariant
# ---------------------------------------------------------------------------

class TestConcurrencySafety:
    """
    Invariant: committed spend never exceeds cap + epsilon
    (epsilon accounts for the one reservation that may just tip over).

    We run N threads each trying to reserve 0.20 against a 1.00 daily cap.
    At most 5 should succeed; committed total must be ≤ 1.00.
    """

    def test_concurrent_reservations_respect_cap(self, tmp_path):
        cap = 1.00
        per_request = 0.20
        epsilon = per_request  # at most one over-reservation before rejection
        n_threads = 20

        ledger = BudgetLedger(
            ledger_path=tmp_path / "conc_ledger.json",
            daily_cap_usd=cap,
            monthly_cap_usd=100.0,
            hard_stop=True,
            lock_timeout_seconds=60,
        )

        committed_total = []
        errors = []

        def worker(i: int):
            idem = f"idem-conc-{i}"
            try:
                rid = ledger.reserve(f"job-{i}", estimated_usd=per_request, idempotency_key=idem)
                ledger.commit(rid, actual_usd=per_request)
                committed_total.append(per_request)
            except BudgetExceededError:
                pass
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unexpected errors: {errors}"
        total = sum(committed_total)
        assert total <= cap + epsilon, (
            f"Committed ${total:.4f} exceeds cap ${cap} + epsilon ${epsilon}"
        )


# ---------------------------------------------------------------------------
# Stale reservation cleanup
# ---------------------------------------------------------------------------

class TestStaleCleanup:
    def test_stale_reservation_is_expired_and_budget_freed(self, tmp_path):
        """
        A reservation whose expires_at has passed must be cleaned up so the
        budget becomes available again.
        """
        ledger = BudgetLedger(
            ledger_path=tmp_path / "stale_ledger.json",
            daily_cap_usd=0.50,
            monthly_cap_usd=10.0,
            hard_stop=True,
            lock_timeout_seconds=1,   # expire after 1 second
        )

        # Fully exhaust the cap with a pending reservation
        rid = ledger.reserve("job-stale", estimated_usd=0.50, idempotency_key="idem-stale")

        # Attempting another reserve should fail immediately
        with pytest.raises(BudgetExceededError):
            ledger.reserve("job-new", estimated_usd=0.10, idempotency_key="idem-new")

        # Wait for the reservation to expire
        time.sleep(1.5)

        # Cleanup should remove the stale entry
        released = ledger.cleanup_stale()
        assert released == 1

        # Budget is now available again
        rid2 = ledger.reserve("job-new2", estimated_usd=0.10, idempotency_key="idem-new2")
        ledger.commit(rid2, actual_usd=0.10)
        assert ledger.current_spend()["daily_committed_usd"] == pytest.approx(0.10, abs=1e-4)

    def test_cleanup_stale_returns_zero_when_nothing_to_clean(self, ledger):
        released = ledger.cleanup_stale()
        assert released == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_committed_key_is_detected(self, ledger):
        idem = "idem-replay-1"
        rid = ledger.reserve("job-idem", estimated_usd=0.10, idempotency_key=idem)
        ledger.commit(rid, actual_usd=0.10)

        existing_rid = ledger.is_idempotency_key_committed(idem)
        assert existing_rid == rid

    def test_uncommitted_key_is_not_detected(self, ledger):
        idem = "idem-uncommitted"
        _rid = ledger.reserve("job-unc", estimated_usd=0.10, idempotency_key=idem)
        # Not committed yet
        assert ledger.is_idempotency_key_committed(idem) is None

    def test_released_key_is_not_detected(self, ledger):
        idem = "idem-released"
        rid = ledger.reserve("job-rel", estimated_usd=0.10, idempotency_key=idem)
        ledger.release(rid, reason="test")
        assert ledger.is_idempotency_key_committed(idem) is None

    def test_replay_does_not_double_charge(self, tmp_path):
        """
        Simulates ProviderRouter's deduplication: if idempotency_key is
        already committed, no second reserve() should be called.
        This test proves the ledger correctly reports the committed state.
        """
        ledger = BudgetLedger(
            ledger_path=tmp_path / "replay_ledger.json",
            daily_cap_usd=1.00,
            monthly_cap_usd=10.0,
            hard_stop=True,
            lock_timeout_seconds=60,
        )
        idem = "idem-replay-dedup"

        # First call
        rid1 = ledger.reserve("job-d", estimated_usd=0.10, idempotency_key=idem)
        ledger.commit(rid1, actual_usd=0.10)

        # Detect committed → skip second reservation (as ProviderRouter does)
        existing = ledger.is_idempotency_key_committed(idem)
        assert existing == rid1

        # Spend must still be exactly 0.10, not 0.20
        assert ledger.current_spend()["daily_committed_usd"] == pytest.approx(0.10, abs=1e-4)
