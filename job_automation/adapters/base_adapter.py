from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.models import JobListing


class SessionExpiredException(Exception):
    """Raised when an adapter detects a redirect to a login page."""


class ElementMissingException(Exception):
    """Raised when a required DOM element is not found within the timeout."""


class BaseJobAdapter(ABC):
    """
    Abstract base class that every job portal adapter must implement.

    Each adapter receives a Playwright `browser_context` from the SessionManager
    so it can share cookies / local storage across calls.
    """

    def __init__(self, browser_context) -> None:
        self.context = browser_context

    # ------------------------------------------------------------------
    # Required interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def login(self) -> None:
        """
        Navigate to the portal login page and authenticate.
        Should save cookies via `context.storage_state()` afterwards.
        """

    @abstractmethod
    async def scrape_page(self, job_role: str, page_num: int) -> list["JobListing"]:
        """
        Return a list of JobListing objects found on the given search results page.
        Must NOT fetch full job descriptions (that is done lazily in get_job_description).
        """

    @abstractmethod
    async def get_job_description(self, url: str) -> str:
        """
        Navigate to a specific job listing URL and return the raw description text.
        Raises ElementMissingException if the description container is not found.
        Raises SessionExpiredException if the page redirects to login.
        """

    # ------------------------------------------------------------------
    # Optional helpers (can override)
    # ------------------------------------------------------------------

    async def _check_session(self, page) -> None:
        """
        Inspect the current page URL. If it contains a login/auth path,
        raise SessionExpiredException so the SessionManager can re-auth.
        """
        if any(kw in page.url for kw in ("/login", "/signin", "/auth")):
            raise SessionExpiredException(
                f"Session expired — redirected to {page.url}"
            )
