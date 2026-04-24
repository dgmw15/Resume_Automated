from __future__ import annotations

"""
CareersFuture (mycareersfuture.gov.sg) Playwright adapter.

All selectors confirmed from live DOM inspection.
"""

import logging
from typing import TYPE_CHECKING

from adapters.base_adapter import BaseJobAdapter, ElementMissingException, SessionExpiredException
from core.login_utils import wait_with_progress
from data.models import JobListing, JobStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

PORTAL_NAME = "careersfuture"
BASE_SEARCH_URL = (
    "https://www.mycareersfuture.gov.sg/search"
    "?search={role}&sortBy=new_posting_date&page={page}"
)

# ── Confirmed selectors ────────────────────────────────────────────────────────
# The <a data-testid="job-card-link"> IS the card wrapper AND the link — href lives on it.
CSS_JOB_CARD    = 'a[data-testid="job-card-link"]'           # ✅ card wrapper + link
CSS_CARD_TITLE   = 'span[data-testid="job-card__job-title"]' # ✅ job title inside card
CSS_CARD_COMPANY = 'p[data-testid="company-hire-info"]'      # ✅ company name inside card
CSS_JOB_DESCRIPTION = 'div[data-testid="description-content"]'  # ✅ full description body
# ── Salary selectors (S2/S3) ───────────────────────────────────────────────────
CSS_SALARY_RANGE = 'span[data-testid="salary-range"]'
CSS_SALARY_MIN   = 'span[data-testid="salary-range"] span.dib:nth-of-type(1)'
CSS_SALARY_MAX   = 'span[data-testid="salary-range"] span.dib:nth-of-type(2)'
# ── Login ──────────────────────────────────────────────────────────────────────
MCF_HOME_URL  = "https://www.mycareersfuture.gov.sg/search?page=0"
CSS_LOGIN_BTN = 'button[data-testid="navbar-login"]'   # ✅ confirmed
# ───────────────────────────────────────────────────────────────────────────────

TIMEOUT_MS       = 15_000
LOGIN_TIMEOUT_MS = 120_000   # 2 min for SingPass manual interaction


class CareersFutureAdapter(BaseJobAdapter):
    def __init__(self, browser_context, credentials: dict) -> None:
        super().__init__(browser_context)
        self._credentials = credentials  # kept for API compatibility; MCF uses SingPass

    async def login(self) -> None:
        """
        Navigate to MCF, click Log In, then wait for the user to complete
        SingPass authentication (QR scan / app approval). Times out after 2 min.
        """
        page = await self.context.new_page()
        await page.goto(MCF_HOME_URL, timeout=TIMEOUT_MS)
        await page.wait_for_load_state("domcontentloaded")

        logger.info("[%s] Manual login window opened (2 minutes).", PORTAL_NAME)
        try:
            await page.click(CSS_LOGIN_BTN, timeout=5_000)
            logger.info("[%s] Login button clicked.", PORTAL_NAME)
        except Exception:
            logger.info("[%s] Login button not clickable now; continue with manual flow.", PORTAL_NAME)

        await wait_with_progress(
            page=page,
            total_ms=LOGIN_TIMEOUT_MS,
            label=f"[{PORTAL_NAME}] Login time remaining",
        )
        await page.close()
        logger.info("[%s] Manual login window ended.", PORTAL_NAME)

    async def scrape_page(self, job_role: str, page_num: int) -> list[JobListing]:
        """
        Return JobListing objects (without full descriptions) for one results page.
        Descriptions are fetched lazily by get_job_description().
        Note: CSS_JOB_CARD is the <a> element — href is read directly from it.
        """
        url = BASE_SEARCH_URL.format(role=job_role, page=page_num)
        page = await self.context.new_page()
        try:
            await page.goto(url, timeout=TIMEOUT_MS)
            await page.wait_for_load_state("networkidle")
            await self._check_session(page)

            cards = await page.query_selector_all(CSS_JOB_CARD)
            if not cards:
                logger.info("[%s] No job cards found on page %d.", PORTAL_NAME, page_num)
                return []

            listings: list[JobListing] = []
            for card in cards:
                try:
                    title_el   = await card.query_selector(CSS_CARD_TITLE)
                    company_el = await card.query_selector(CSS_CARD_COMPANY)

                    role    = (await title_el.inner_text()).strip()   if title_el   else "Unknown"
                    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

                    # The card <a> element carries the href directly
                    href = await card.get_attribute("href")
                    if href and not href.startswith("http"):
                        href = "https://www.mycareersfuture.gov.sg" + href

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
