"""
core/budget_ledger.py — Persistent atomic budget reservation ledger.

Solves the race-condition gap in the in-memory BudgetGuard: concurrent
batch workers could each check the cap, see it is not exceeded, and all
fire API calls simultaneously, blowing past the daily/monthly limit.

Design
------
- Reservations are written to a JSON ledger file before any provider call.
- A file-level lock (via a .lock sidecar) serialises concurrent writes so
  only one worker holds the lock at a time.
- If the cap would be exceeded after adding a new reservation, the reserve()
  call raises BudgetExceededError immediately — before the provider is hit.
- Stale reservations (older than cost_lock_timeout_seconds) are released
  automatically during every reserve() and during scheduled cleanup.

Budget boundary semantics
-------------------------
- Daily cap resets at 00:00:00 in the configured timezone.
- Monthly cap resets on the 1st of each calendar month at 00:00:00.
- All cost amounts are rounded to budget_precision_decimals decimal places
  before comparison, preventing float drift from triggering false stops.

Thread / process safety
-----------------------
This ledger is safe for a single machine running multiple async workers.
For distributed workers sharing a network drive it is sufficient; for
true multi-machine deployments replace the file lock with a database
or distributed lock (e.g. Redis SETNX).
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows — _FileLock degrades to a no-op below.

logger = logging.getLogger(__name__)

_LEDGER_DEFAULT = Path("budget_ledger.json")
_LOCK_SUFFIX = ".lock"


class BudgetExceededError(Exception):
    """Raised when a cost reservation would exceed the configured cap."""


class BudgetLedger:
    """
    Persistent, file-locked budget reservation ledger.

    Usage
    -----
        ledger = BudgetLedger.from_config(config)
        rid = ledger.reserve("job-123", estimated_usd=0.05, idempotency_key="idem-abc")
        try:
            result = provider.generate(...)
            ledger.commit(rid, actual_usd=result.cost)
        except Exception:
            ledger.release(rid, reason="provider error")
            raise

    Args
    ----
        ledger_path:          where to store the JSON ledger file.
        daily_cap_usd:        maximum spend per calendar day.
        monthly_cap_usd:      maximum spend per calendar month.
        hard_stop:            if False, caps are logged but not enforced.
        timezone_name:        IANA timezone for daily/monthly reset boundaries.
        precision_decimals:   decimal places for cost rounding.
        lock_timeout_seconds: seconds before an unconfirmed reservation expires.
    """

    def __init__(
        self,
        ledger_path: Path = _LEDGER_DEFAULT,
        daily_cap_usd: float = 5.0,
        monthly_cap_usd: float = 50.0,
        hard_stop: bool = True,
        timezone_name: str = "UTC",
        precision_decimals: int = 4,
        lock_timeout_seconds: int = 60,
    ) -> None:
        self._path = Path(ledger_path)
        self._lock_path = self._path.with_suffix(_LOCK_SUFFIX)
        self._daily_cap = self._round(daily_cap_usd, precision_decimals)
        self._monthly_cap = self._round(monthly_cap_usd, precision_decimals)
        self._hard_stop = hard_stop
        self._tz = ZoneInfo(timezone_name)
        self._precision = precision_decimals
        self._lock_timeout = lock_timeout_seconds
        self._ensure_ledger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reserve(
        self,
        job_id: str,
        estimated_usd: float,
        idempotency_key: str,
    ) -> str:
        """
        Attempt to reserve estimated_usd from the budget.

        Returns the reservation_id (UUID) on success.
        Raises BudgetExceededError if the cap would be exceeded.
        """
        amount = self._round(estimated_usd, self._precision)
        reservation_id = str(uuid.uuid4())
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=self._lock_timeout)
        ).isoformat()

        with self._file_lock():
            ledger = self._read()
            self._expire_stale(ledger)

            daily_used = self._daily_committed(ledger) + self._pending_reserved(ledger)
            monthly_used = self._monthly_committed(ledger) + self._pending_reserved(ledger)

            if self._hard_stop:
                if self._round(daily_used + amount, self._precision) > self._daily_cap:
                    raise BudgetExceededError(
                        f"Daily cap ${self._daily_cap} would be exceeded "
                        f"(used ${daily_used:.{self._precision}f} + "
                        f"reserving ${amount:.{self._precision}f})"
                    )
                if self._round(monthly_used + amount, self._precision) > self._monthly_cap:
                    raise BudgetExceededError(
                        f"Monthly cap ${self._monthly_cap} would be exceeded "
                        f"(used ${monthly_used:.{self._precision}f} + "
                        f"reserving ${amount:.{self._precision}f})"
                    )

            ledger["reservations"][reservation_id] = {
                "job_id": job_id,
                "idempotency_key": idempotency_key,
                "reserved_usd": amount,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at,
            }
            self._write(ledger)

        logger.info(
            "Budget reserved %.{p}f for job %s (rid=%s, daily_used=%.{p}f/%.{p}f)".format(
                p=self._precision
            ),
            amount, job_id, reservation_id, daily_used, float(self._daily_cap),
        )
        return reservation_id

    def commit(self, reservation_id: str, actual_usd: float) -> None:
        """
        Confirm a reservation with the actual cost from the provider response.
        Moves the entry from pending → committed.
        """
        actual = self._round(actual_usd, self._precision)
        with self._file_lock():
            ledger = self._read()
            entry = ledger["reservations"].get(reservation_id)
            if entry is None:
                logger.warning("commit() called for unknown reservation %s", reservation_id)
                return
            entry["status"] = "committed"
            entry["actual_usd"] = actual
            entry["committed_at"] = datetime.now(timezone.utc).isoformat()
            # Remove expiry — committed entries are permanent until reset
            entry.pop("expires_at", None)
            self._write(ledger)
        logger.info("Budget committed %.{p}f for rid=%s".format(p=self._precision), actual, reservation_id)

    def release(self, reservation_id: str, reason: str = "") -> None:
        """
        Release a pending reservation without charging (e.g. on provider error).
        """
        with self._file_lock():
            ledger = self._read()
            entry = ledger["reservations"].pop(reservation_id, None)
            if entry is None:
                logger.debug("release() called for unknown/already-released rid=%s", reservation_id)
                return
            self._write(ledger)
        logger.info("Budget reservation released (rid=%s reason=%r)", reservation_id, reason)

    def cleanup_stale(self) -> int:
        """
        Expire stale reservations. Returns count of released entries.
        Call this on a periodic cadence (reservation_cleanup_interval_seconds).
        """
        with self._file_lock():
            ledger = self._read()
            before = len(ledger["reservations"])
            self._expire_stale(ledger)
            released = before - len(ledger["reservations"])
            if released:
                self._write(ledger)
        if released:
            logger.info("Stale reservation cleanup: released %d entries.", released)
        return released

    def current_spend(self) -> dict[str, float]:
        """Return a snapshot of committed spend (daily and monthly)."""
        with self._file_lock():
            ledger = self._read()
            self._expire_stale(ledger)
        return {
            "daily_committed_usd": float(self._daily_committed(ledger)),
            "monthly_committed_usd": float(self._monthly_committed(ledger)),
            "pending_reserved_usd": float(self._pending_reserved(ledger)),
            "daily_cap_usd": float(self._daily_cap),
            "monthly_cap_usd": float(self._monthly_cap),
        }

    def is_idempotency_key_committed(self, idempotency_key: str) -> Optional[str]:
        """
        Return the reservation_id if this idempotency_key has already been
        committed, else None. Used to deduplicate replayed jobs.
        """
        with self._file_lock():
            ledger = self._read()
        for rid, entry in ledger["reservations"].items():
            if (
                entry.get("idempotency_key") == idempotency_key
                and entry.get("status") == "committed"
            ):
                return rid
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_ledger(self) -> None:
        if not self._path.exists():
            self._write({"reservations": {}})

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {"reservations": {}}

    def _write(self, ledger: dict) -> None:
        self._path.write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _file_lock(self):
        """Context manager that acquires an exclusive file lock."""
        return _FileLock(self._lock_path)

    def _expire_stale(self, ledger: dict) -> None:
        """Remove pending reservations whose expires_at is in the past. Mutates ledger."""
        now = datetime.now(timezone.utc)
        stale = [
            rid
            for rid, entry in ledger["reservations"].items()
            if entry.get("status") == "pending"
            and "expires_at" in entry
            and datetime.fromisoformat(entry["expires_at"]) <= now
        ]
        for rid in stale:
            logger.debug("Expiring stale reservation %s", rid)
            ledger["reservations"].pop(rid)

    def _now_local(self) -> datetime:
        return datetime.now(self._tz)

    def _daily_committed(self, ledger: dict) -> float:
        """Sum committed spend for the current calendar day (in configured timezone)."""
        today = self._now_local().date()
        total = 0.0
        for entry in ledger["reservations"].values():
            if entry.get("status") != "committed":
                continue
            committed_at_str = entry.get("committed_at", "")
            if not committed_at_str:
                continue
            committed_at = datetime.fromisoformat(committed_at_str).astimezone(self._tz)
            if committed_at.date() == today:
                total += float(entry.get("actual_usd", 0.0))
        return self._round(total, self._precision)

    def _monthly_committed(self, ledger: dict) -> float:
        """Sum committed spend for the current calendar month."""
        now = self._now_local()
        total = 0.0
        for entry in ledger["reservations"].values():
            if entry.get("status") != "committed":
                continue
            committed_at_str = entry.get("committed_at", "")
            if not committed_at_str:
                continue
            committed_at = datetime.fromisoformat(committed_at_str).astimezone(self._tz)
            if committed_at.year == now.year and committed_at.month == now.month:
                total += float(entry.get("actual_usd", 0.0))
        return self._round(total, self._precision)

    def _pending_reserved(self, ledger: dict) -> float:
        """Sum of all non-expired pending reservations (conservative: counts against cap)."""
        total = sum(
            float(entry.get("reserved_usd", 0.0))
            for entry in ledger["reservations"].values()
            if entry.get("status") == "pending"
        )
        return self._round(total, self._precision)

    @staticmethod
    def _round(value: float, decimals: int) -> float:
        return float(
            Decimal(str(value)).quantize(
                Decimal(10) ** -decimals, rounding=ROUND_HALF_UP
            )
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict, ledger_path: Path = _LEDGER_DEFAULT) -> "BudgetLedger":
        ai_cfg = config.get("ai", {})
        budget = ai_cfg.get("budget", {})
        return cls(
            ledger_path=ledger_path,
            daily_cap_usd=float(budget.get("daily_cap_usd", 5.0)),
            monthly_cap_usd=float(budget.get("monthly_cap_usd", 50.0)),
            hard_stop=bool(budget.get("hard_stop", True)),
            timezone_name=str(budget.get("budget_timezone", "UTC")),
            precision_decimals=int(budget.get("budget_precision_decimals", 4)),
            lock_timeout_seconds=int(budget.get("cost_lock_timeout_seconds", 60)),
        )


class _FileLock:
    """
    Simple exclusive file lock using fcntl (POSIX).

    On Windows, fcntl is not available; fall back to a no-op context so the
    ledger still works (single-process only on Windows).
    """

    def __init__(self, lock_path: Path) -> None:
        self._path = lock_path
        self._fd: Optional[int] = None

    def __enter__(self):
        try:
            self._fd = os.open(str(self._path), os.O_CREAT | os.O_WRONLY)
            fcntl.flock(self._fd, fcntl.LOCK_EX)
        except (ImportError, AttributeError, OSError):
            # fcntl not available (Windows) or lock path not writable — degrade gracefully
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
        return self

    def __exit__(self, *_):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
