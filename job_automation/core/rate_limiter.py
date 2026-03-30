from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PortalLimits:
    max_actions_per_hour: int = 20
    min_delay: float = 5.0
    max_delay: float = 15.0


class RateLimiter:
    """
    Per-portal token-bucket rate limiter.

    Usage:
        limiter = RateLimiter()
        limiter.configure("careersfuture", max_actions_per_hour=30, min_delay=5, max_delay=15)

        await limiter.wait("careersfuture")   # call before every page action
    """

    def __init__(self) -> None:
        self._limits: dict[str, PortalLimits] = {}
        self._action_log: dict[str, list[float]] = {}   # portal → list of timestamps

    def configure(self, portal_name: str, max_actions_per_hour: int = 20,
                  min_delay: float = 5.0, max_delay: float = 15.0) -> None:
        self._limits[portal_name] = PortalLimits(
            max_actions_per_hour=max_actions_per_hour,
            min_delay=min_delay,
            max_delay=max_delay,
        )
        self._action_log.setdefault(portal_name, [])

    async def wait(self, portal_name: str) -> None:
        """
        Block until it is safe to perform the next action for this portal.
        Enforces both the per-hour cap and a random human-like delay.
        """
        limits = self._limits.get(portal_name, PortalLimits())
        log = self._action_log.setdefault(portal_name, [])

        # Prune timestamps older than 1 hour
        now = time.monotonic()
        one_hour_ago = now - 3600
        self._action_log[portal_name] = [t for t in log if t > one_hour_ago]
        log = self._action_log[portal_name]

        # If at the hourly cap, wait until the oldest action falls out of the window
        if len(log) >= limits.max_actions_per_hour:
            sleep_until = log[0] + 3600
            wait_secs = max(0.0, sleep_until - time.monotonic())
            logger.warning(
                "[%s] Hourly limit reached (%d actions). Sleeping %.0fs.",
                portal_name, limits.max_actions_per_hour, wait_secs,
            )
            await asyncio.sleep(wait_secs)
            # Prune again after sleep
            self._action_log[portal_name] = [
                t for t in self._action_log[portal_name] if t > time.monotonic() - 3600
            ]

        # Human-like random delay
        delay = random.uniform(limits.min_delay, limits.max_delay)
        logger.debug("[%s] Rate-limit delay: %.1fs", portal_name, delay)
        await asyncio.sleep(delay)

        self._action_log[portal_name].append(time.monotonic())
