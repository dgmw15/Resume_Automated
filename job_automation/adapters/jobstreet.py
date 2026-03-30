from __future__ import annotations

"""
JobStreet Playwright adapter.

⚠️  SELECTORS ARE PLACEHOLDERS ⚠️
JobStreet uses a modern React/JS framework — selectors change frequently.
To fill these in:
  1. Open https://www.jobstreet.com.sg/jobs?q=<role>&pg=<page>
  2. Right-click a job card on the SEARCH RESULTS page → Inspect Element
  3. Paste the HTML block for ONE job card here.
  4. Then click into a job listing, right-click the description section → Inspect
  5. Paste that HTML block too.
"""

import logging

from adapters.base_adapter import BaseJobAdapter, ElementMissingException, SessionExpiredException
from data.models import JobListing, JobStatus

logger = logging.getLogger(__name__)

PORTAL_NAME = "jobstreet"
BASE_SEARCH_URL = "https://www.jobstreet.com.sg/jobs?q={role}&pg={page}"

# ── TODO: fill after inspecting the live DOM ───────────────────────────────────
CSS_JOB_CARD = "TODO"               # e.g. 'article[data-automation="normalJob"]'
CSS_CARD_TITLE = "TODO"             # relative to CSS_JOB_CARD
CSS_CARD_COMPANY = "TODO"           # relative to CSS_JOB_CARD
CSS_CARD_LINK = "TODO"              # <a> with the job URL
CSS_JOB_DESCRIPTION = "TODO"       # container on the job details page
# ───────────────────────────────────────────────────────────────────────────────

TIMEOUT_MS = 20_000   # JobStreet can be slow — longer timeout


class JobStreetAdapter(BaseJobAdapter):
    def __init__(self, browser_context) -> None:
        super().__init__(browser_context)

    async def login(self) -> None:
        # JobStreet search is publicly accessible — login only needed for applying.
        # Leave as a no-op until the Apply phase is implemented.
        logger.info("[%s] login() called — no-op for scrape phase.", PORTAL_NAME)

    async def scrape_page(self, job_role: str, page_num: int) -> list[JobListing]:
        if CSS_JOB_CARD == "TODO":
            raise NotImplementedError(
                "CSS selectors not set. Inspect the DOM and update the TODO constants."
            )

        url = BASE_SEARCH_URL.format(role=job_role, page=page_num)
        page = await self.context.new_page()
        try:
            await page.goto(url, timeout=TIMEOUT_MS)
            # JobStreet uses JS rendering — wait for network to settle
            await page.wait_for_load_state("networkidle")
            await self._check_session(page)

            cards = await page.query_selector_all(CSS_JOB_CARD)
            if not cards:
                logger.info("[%s] No job cards on page %d.", PORTAL_NAME, page_num)
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
                        href = "https://www.jobstreet.com.sg" + href

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
        if CSS_JOB_DESCRIPTION == "TODO":
            raise NotImplementedError(
                "CSS_JOB_DESCRIPTION not set. Inspect the job details page DOM."
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
