from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from adapters.base_adapter import SessionExpiredException
from adapters.careersfuture import CareersFutureAdapter
from adapters.indeed import IndeedAdapter
from adapters.jobstreet import JobStreetAdapter
from ai.jd_validator import build_validator_from_config
from ai.provider_router import ProviderRouter
from ai.tailor import ResumeTailor
from core.batch_processor import BatchProcessor
from core.rate_limiter import RateLimiter
from core.session_manager import SessionManager
from data.models import JobStatus
from data.tracker import ExcelTracker
from output.docx_renderer import build_renderer_from_config

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.yaml")


class Orchestrator:
    """
    Main execution loop.

    Phases (run in order, indefinitely):
      1. Scrape    — fetch new job listings from enabled portals.
      2. Validate  — deterministic JD relevance gate.
      3. Batch     — queue and process validated jobs via AI.
      4. (Apply phase not yet implemented — requires user APPROVED rows.)
    """

    def __init__(self) -> None:
        self.config = self._load_config()
        self.tracker = ExcelTracker()
        self.session_manager = SessionManager()
        self.rate_limiter = RateLimiter()
        self.router: ProviderRouter | None = None
        self.tailor: ResumeTailor | None = None
        self.batch_processor: BatchProcessor | None = None
        self._adapters: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config() -> dict:
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    async def start(self) -> None:
        await self.session_manager.start()

        # Configure rate limiters from config
        for portal_name, settings in self.config.get("portals", {}).items():
            if not settings.get("enabled", False):
                continue
            self.rate_limiter.configure(
                portal_name=portal_name,
                max_actions_per_hour=settings.get("max_actions_per_hour", 20),
                min_delay=settings.get("min_delay_seconds", 5),
                max_delay=settings.get("max_delay_seconds", 15),
            )

        # Initialise provider router, tailor, and batch processor
        try:
            self.router = ProviderRouter(self.config)
            self.tailor = ResumeTailor(self.router)
            batch_cfg = self.config.get("batch", {})
            if batch_cfg.get("enabled", True):
                docx_renderer = build_renderer_from_config(self.config)
                self.batch_processor = BatchProcessor(
                    self.tracker, self.tailor, batch_cfg, docx_renderer=docx_renderer
                )
                logger.info("BatchProcessor initialised (interval=%dmin).",
                            batch_cfg.get("interval_minutes", 30))
            logger.info("AI provider router initialised.")
        except Exception as exc:
            logger.warning("AI provider router could not be initialised: %s — tailoring disabled.", exc)

        # Build adapter instances
        portal_cfg = self.config.get("portals", {})
        credentials = self.config.get("credentials", {})

        if portal_cfg.get("careersfuture", {}).get("enabled"):
            ctx = await self.session_manager.get_context("careersfuture")
            self._adapters["careersfuture"] = CareersFutureAdapter(
                ctx, credentials.get("careersfuture", {})
            )

        if portal_cfg.get("jobstreet", {}).get("enabled"):
            ctx = await self.session_manager.get_context("jobstreet")
            self._adapters["jobstreet"] = JobStreetAdapter(ctx)

        if portal_cfg.get("indeed", {}).get("enabled"):
            ctx = await self.session_manager.get_context("indeed")
            self._adapters["indeed"] = IndeedAdapter(ctx)

        logger.info("Orchestrator started with portals: %s", list(self._adapters.keys()))

    async def stop(self) -> None:
        await self.session_manager.stop()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        while True:
            await self._phase_scrape()
            await self._phase_validate()
            await self._phase_batch()
            # Sleep before next cycle
            logger.info("Cycle complete. Sleeping 5 minutes before next cycle.")
            await asyncio.sleep(300)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_roles(self) -> list[str]:
        """
        Load job roles from the configured Excel file.
        Falls back to config.yaml keywords if the file is missing or empty.
        """
        roles_cfg = self.config.get("search", {}).get("roles_excel", {})
        excel_path = Path(roles_cfg.get("path", "job_roles.xlsx"))
        sheet      = roles_cfg.get("sheet", "Roles")
        column     = roles_cfg.get("column", "Job Role")

        if excel_path.exists():
            try:
                df = pd.read_excel(excel_path, sheet_name=sheet)
                roles = df[column].dropna().str.strip().tolist()
                if roles:
                    logger.info("Loaded %d job roles from %s", len(roles), excel_path)
                    return roles
                logger.warning("Column '%s' in %s is empty — falling back to config keywords.", column, excel_path)
            except Exception as exc:
                logger.warning("Could not read %s: %s — falling back to config keywords.", excel_path, exc)
        else:
            logger.info("%s not found — using config.yaml keywords.", excel_path)

        return self.config.get("search", {}).get("keywords", [])

    # ------------------------------------------------------------------
    # Phase 1: Scrape
    # ------------------------------------------------------------------

    async def _phase_scrape(self) -> None:
        roles = self._load_roles()
        for portal_name, adapter in self._adapters.items():
            for role in roles:
                last_page = self.tracker.get_last_page(portal_name)
                next_page = last_page + 1
                logger.info("[%s] Scraping '%s' page %d", portal_name, role, next_page)

                try:
                    await self.rate_limiter.wait(portal_name)
                    listings = await adapter.scrape_page(role, next_page)
                except SessionExpiredException:
                    logger.warning("[%s] Session expired — re-authenticating.", portal_name)
                    await self.session_manager.reauth(portal_name, adapter)
                    listings = await adapter.scrape_page(role, next_page)
                except NotImplementedError as exc:
                    logger.error("[%s] Adapter not ready: %s", portal_name, exc)
                    continue
                except Exception as exc:
                    logger.error("[%s] Scrape failed for page %d: %s", portal_name, next_page, exc)
                    continue

                for listing in listings:
                    try:
                        await self.rate_limiter.wait(portal_name)
                        raw_desc = await adapter.get_job_description(listing.url)
                        listing.raw_description = raw_desc
                        listing.status = JobStatus.SCRAPED
                    except SessionExpiredException:
                        await self.session_manager.reauth(portal_name, adapter)
                    except Exception as exc:
                        logger.warning("[%s] Could not fetch description for %s: %s",
                                       portal_name, listing.url, exc)
                        listing.status = JobStatus.MISSING

                    self.tracker.append(listing)

    # ------------------------------------------------------------------
    # Phase 2: JD Validation
    # ------------------------------------------------------------------

    async def _phase_validate(self) -> None:
        """
        Run deterministic keyword/deny-pattern validation on every SCRAPED row.
        Sets status to VALIDATION_PASSED or VALIDATION_FAILED_NON_TECH.
        """
        rows = (
            self.tracker.get_by_status(JobStatus.SCRAPED)
            + self.tracker.get_by_status(JobStatus.VALIDATION_PENDING)
        )
        if not rows:
            return

        # Determine default role for validator (analyst unless config says otherwise)
        default_role = self.config.get("ai", {}).get("default_role", "analyst")
        validator = build_validator_from_config(self.config, role=default_role)

        for row in rows:
            job_id = row.get("id")
            raw_desc = row.get("raw_description") or ""
            if not job_id:
                continue

            # Mark VALIDATION_PENDING before running the check
            self.tracker.update(job_id, status=JobStatus.VALIDATION_PENDING)
            result = validator.validate(raw_desc)
            if result.is_pass:
                self.tracker.mark_validation_result(
                    job_id,
                    status=JobStatus.VALIDATION_PASSED,
                    score=result.score,
                    reason=result.reason,
                )
            else:
                self.tracker.mark_validation_result(
                    job_id,
                    status=JobStatus.VALIDATION_FAILED_NON_TECH,
                    score=result.score,
                    reason=result.reason,
                )

    # ------------------------------------------------------------------
    # Phase 3: Batch AI processing
    # ------------------------------------------------------------------

    async def _phase_batch(self) -> None:
        if self.batch_processor is None:
            logger.debug("BatchProcessor not initialised — skipping batch phase.")
            return
        from ai.providers.base import BudgetExceededError
        try:
            await self.batch_processor.run_once()
        except BudgetExceededError as exc:
            logger.error("Budget cap reached — batch halted this cycle: %s", exc)
