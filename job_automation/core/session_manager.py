from __future__ import annotations

import json
import logging
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Playwright

logger = logging.getLogger(__name__)

SESSION_DIR = Path(".sessions")


class SessionManager:
    """
    Manages a single persistent Playwright Chromium context per portal.

    Cookies and local-storage are saved to disk so the user only has to
    log in once.  If a SessionExpiredException is caught by the orchestrator,
    it calls `reauth(portal_name)` which re-runs the adapter's login() method
    and saves the refreshed state.
    """

    def __init__(self) -> None:
        SESSION_DIR.mkdir(exist_ok=True)
        self._playwright: Playwright | None = None
        self._contexts: dict[str, BrowserContext] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the underlying Playwright instance. Call once at boot."""
        self._playwright = await async_playwright().start()
        logger.info("Playwright started.")

    async def stop(self) -> None:
        """Close all open contexts and stop Playwright."""
        for name, ctx in self._contexts.items():
            await ctx.close()
            logger.info("Closed context for %s", name)
        if self._playwright:
            await self._playwright.stop()

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    async def get_context(self, portal_name: str) -> BrowserContext:
        """
        Return a live BrowserContext for the given portal.
        Creates one from saved storage state if it exists, otherwise a fresh one.
        """
        if portal_name in self._contexts:
            return self._contexts[portal_name]

        state_file = SESSION_DIR / f"{portal_name}.json"
        storage_state = str(state_file) if state_file.exists() else None

        context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR / portal_name),
            headless=False,          # Visible so the user can solve CAPTCHAs
            storage_state=storage_state,
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        self._contexts[portal_name] = context
        logger.info("Created browser context for %s", portal_name)
        return context

    async def save_state(self, portal_name: str) -> None:
        """Persist cookies + localStorage to disk for a given portal."""
        ctx = self._contexts.get(portal_name)
        if ctx is None:
            return
        state_file = SESSION_DIR / f"{portal_name}.json"
        await ctx.storage_state(path=str(state_file))
        logger.info("Session state saved for %s → %s", portal_name, state_file)

    async def reauth(self, portal_name: str, adapter) -> None:
        """
        Close the stale context, open a fresh one, run adapter.login(),
        and save the new state.
        """
        if portal_name in self._contexts:
            await self._contexts[portal_name].close()
            del self._contexts[portal_name]

        # Also clear the stale state file so we start clean
        state_file = SESSION_DIR / f"{portal_name}.json"
        if state_file.exists():
            state_file.unlink()

        fresh_context = await self.get_context(portal_name)
        adapter.context = fresh_context
        await adapter.login()
        await self.save_state(portal_name)
        logger.info("Re-authentication complete for %s", portal_name)
