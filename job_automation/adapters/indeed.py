from __future__ import annotations

"""
Indeed Playwright adapter.

⚠️  SELECTORS ARE PLACEHOLDERS ⚠️
Indeed has strict bot detection. To fill these in safely:
  1. Open https://sg.indeed.com/jobs?q=<role>&start=<(page-1)*10>
  2. Right-click a job card on the SEARCH RESULTS page → Inspect Element
  3. Paste the HTML block for ONE job card here.
  4. Click a job — the description appears in a RIGHT-HAND PANEL (not a new page).
  5. Inspect that panel and paste its HTML too.

⚠️  Bot protection note: Indeed detects automation aggressively. The rate limiter
    is applied on EVERY action here (page nav + card click). Do not reduce delays.
"""

import logging

from adapters.base_adapter import BaseJobAdapter, ElementMissingException, SessionExpiredException
from data.models import JobListing, JobStatus

logger = logging.getLogger(__name__)

PORTAL_NAME = "indeed"
# Indeed SG pagination: start=0 (p1), start=10 (p2), start=20 (p3) ...
BASE_SEARCH_URL = "https://sg.indeed.com/jobs?q={role}&start={start}&sort=date"

# ── TODO: fill after inspecting the live DOM ───────────────────────────────────
CSS_JOB_CARD = "TODO"               # e.g. 'div.job_seen_beacon' or 'li.css-...'
CSS_CARD_TITLE = "TODO"             # <h2> or <a> inside CSS_JOB_CARD
CSS_CARD_COMPANY = "TODO"           # company name element inside CSS_JOB_CARD
CSS_CARD_LINK = "TODO"              # <a> with the job URL inside CSS_JOB_CARD
CSS_JOB_DESCRIPTION = "TODO"       # right-hand description panel on the results page
# ───────────────────────────────────────────────────────────────────────────────

TIMEOUT_MS = 20_000
RESULTS_PER_PAGE = 10


class IndeedAdapter(BaseJobAdapter):
    def __init__(self, browser_context) -> None:
        super().__init__(browser_context)

    async def login(self) -> None:
        # Indeed public search doesn't require login for scraping.
        # Login is only needed for Easy Apply — implement in the Apply phase.
        logger.info("[%s] login() called — no-op for scrape phase.", PORTAL_NAME)

    async def scrape_page(self, job_role: str, page_num: int) -> list[JobListing]:
        """
        page_num is 1-based; converted to Indeed's `start` offset internally.
        """
        if CSS_JOB_CARD == "TODO":
            raise NotImplementedError(
                "CSS selectors not set. Inspect the DOM and update the TODO constants."
            )

        start = (page_num - 1) * RESULTS_PER_PAGE
        url = BASE_SEARCH_URL.format(role=job_role, start=start)
        page = await self.context.new_page()
        try:
            await page.goto(url, timeout=TIMEOUT_MS)
            await page.wait_for_load_state("networkidle")
            await self._check_session(page)

            cards = await page.query_selector_all(CSS_JOB_CARD)
            if not cards:
                logger.info("[%s] No job cards on page %d (start=%d).", PORTAL_NAME, page_num, start)
                return []

            listings: list[JobListing] = []
            for card in cards:
                try:
                    title_el = await card.query_selector(CSS_CARD_TITLE)
                    company_el = await card.query_selector(CSS_CARD_COMPANY)
                    link_el = await card.query_selector(CSS_CARD_LINK)

                    role = (await title_el.inner_text()).strip() if title_el else "Unknown"
                    company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                    href = await link_el.get_attribute("href") if link_el else None
                    if href and not href.startswith("http"):
                        href = "https://sg.indeed.com" + href

                    if href:
                        listings.append(JobListing(
                            portal_name=PORTAL_NAME,
                            role=role,
                            company=company,
                            url=href,
                            status=JobStatus.SCRAPED,
                            page_num=page_num,
                        ))
                except Exception as exc:
                    logger.warning("[%s] Error parsing card: %s", PORTAL_NAME, exc)

            logger.info("[%s] Scraped %d listings from page %d.", PORTAL_NAME, len(listings), page_num)
            return listings
        finally:
            await page.close()

    async def get_job_description(self, url: str) -> str:
        """
        Indeed shows the description in a side panel after clicking a card.
        We navigate directly to the job URL and scrape the description container.
        """
        if CSS_JOB_DESCRIPTION == "TODO":
            raise NotImplementedError(
                "CSS_JOB_DESCRIPTION not set. Inspect the job details panel DOM."
            )

        page = await self.context.new_page()
        try:
            await page.goto(url, timeout=TIMEOUT_MS)
            await page.wait_for_load_state("networkidle")
            await self._check_session(page)

            desc_el = await page.wait_for_selector(CSS_JOB_DESCRIPTION, timeout=TIMEOUT_MS)
            if not desc_el:
                raise ElementMissingException(f"Description not found at {url}")

            return (await desc_el.inner_text()).strip()
        finally:
            await page.close()
