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
from ai.employment_filter import EmploymentFilter
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
            await self._phase_data_check()          # C2: optional pre-pipeline gate
            await self._phase_employment_filter()   # S5: runs before JD validation
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
    # Phase 1b: Data Completeness Check  (Prompt C2)
    # Optional pre-pipeline gate. Runs after scrape, before employment filter.
    # Controlled by data_checker.enabled + data_checker.run_stage in config.
    # ------------------------------------------------------------------

    async def _phase_data_check(self) -> None:
        """
        Run the data completeness checker on configured target workbooks.

        Behaviour is fully config-driven:
          data_checker.enabled=false  → skipped silently
          data_checker.mode=audit_only → report only, no writes
          data_checker.mode=recover   → backfill recoverable salary fields
          data_checker.dry_run=true   → reports produced but workbook not mutated
        """
        dc_cfg = self.config.get("data_checker", {})
        if not dc_cfg.get("enabled", False):
            return

        run_stage = dc_cfg.get("run_stage", "pre_pipeline")
        if run_stage != "pre_pipeline":
            return

        try:
            from core.data_checker import DataChecker
            checker = DataChecker.from_config(self.config)
            reports = await checker.run()
            for report in reports:
                counts = report.outcome_counts
                logger.info(
                    "[data_checker] %s: COMPLETE=%d RECOVERED=%d UNRESOLVED=%d",
                    report.workbook_path,
                    counts.get("COMPLETE", 0),
                    counts.get("RECOVERED_LOCAL", 0) + counts.get("RECOVERED_REFETCH", 0),
                    counts.get("UNRESOLVED", 0),
                )
        except Exception as exc:
            logger.warning(
                "[data_checker] Phase skipped due to error: %s — pipeline continues.", exc
            )

    # ------------------------------------------------------------------
    # Phase 2a: Employment Type Filter  (Prompt S5)
    # Runs before JD validation. Filtered rows never enter the AI queue.
    # ------------------------------------------------------------------

    async def _phase_employment_filter(self) -> None:
        """
        Apply employment-type filter to all SCRAPED rows.

        Flow: SCRAPED → employment filter → (SCRAPED if PASSED/SKIPPED)
        Filtered rows have employment_filter_status=FILTERED and are
        excluded from the JD validation phase by checking that field.
        When disabled (enabled=false) all rows are marked SKIPPED and pass through.
        """
        ef_cfg = self.config.get("employment_filter", {})
        if not ef_cfg:
            return

        emp_filter = EmploymentFilter.from_config(self.config)

        rows = self.tracker.get_by_status(JobStatus.SCRAPED)
        if not rows:
            return

        passed = filtered = skipped = 0
        for row in rows:
            job_id = row.get("id")
            if not job_id:
                continue

            result = emp_filter.classify(
                title=row.get("role", ""),
                description=row.get("raw_description", ""),
            )

            self.tracker.mark_employment_filter(
                job_id=job_id,
                status=result.status,
                reason=result.reason,
                emp_type_raw=result.employment_type_raw,
                emp_type_normalized=result.employment_type_normalized,
            )

            if result.status == "FILTERED":
                filtered += 1
                logger.info(
                    "[employment_filter] FILTERED job %s (%s): %s",
                    job_id, row.get("role", ""), result.reason,
                )
            elif result.status == "SKIPPED":
                skipped += 1
            else:
                passed += 1

        logger.info(
            "[employment_filter] Phase done: %d passed, %d filtered, %d skipped.",
            passed, filtered, skipped,
        )

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
            # Skip rows already filtered by employment filter (S5)
            if row.get("employment_filter_status") == "FILTERED":
                continue

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
