"""
core/batch_processor.py — 24-hour SLA batch worker.

Pulls VALIDATION_PASSED rows, queues them as BATCH_QUEUED, then processes
them in chunks, respecting batch_size, interval_minutes, and max_retries
from config.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from pathlib import Path

from ai.pipeline import get_prompts, select_track
from ai.providers.base import BudgetExceededError
from ai.tailor import ResumeTailor
from data.models import JobStatus
from data.tracker import ExcelTracker
from output.docx_renderer import DocxRenderer

logger = logging.getLogger(__name__)

BASE_RESUME_PATH = Path("base_resume.txt")


class BatchProcessor:
    """
    Processes validated jobs via the AI tailor in controlled batches.

    Args:
        tracker:     shared ExcelTracker instance.
        tailor:      ResumeTailor backed by ProviderRouter.
        batch_cfg:   dict from config["batch"].
    """

    def __init__(
        self,
        tracker: ExcelTracker,
        tailor: ResumeTailor,
        batch_cfg: dict,
        docx_renderer: DocxRenderer | None = None,
    ) -> None:
        self._tracker = tracker
        self._tailor = tailor
        self._docx_renderer = docx_renderer
        self._batch_size: int = int(batch_cfg.get("batch_size", 5))
        self._sla_hours: int = int(batch_cfg.get("target_sla_hours", 24))
        self._max_retries: int = int(batch_cfg.get("max_retries", 3))
        self._interval_minutes: int = int(batch_cfg.get("interval_minutes", 30))

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def run_once(self) -> int:
        """
        Execute one batch cycle:
          1. Move VALIDATION_PASSED rows to BATCH_QUEUED.
          2. Compute how many to process this run.
          3. Process up to that many BATCH_QUEUED rows.

        Returns the number of jobs successfully processed this cycle.
        """
        if not BASE_RESUME_PATH.exists():
            logger.warning("base_resume.txt not found — skipping batch cycle.")
            return 0

        base_resume = BASE_RESUME_PATH.read_text(encoding="utf-8")

        # Stage: move VALIDATION_PASSED → BATCH_QUEUED
        self._enqueue_validated()

        queued = self._tracker.list_rows_by_status(JobStatus.BATCH_QUEUED)
        if not queued:
            logger.info("BatchProcessor: no queued jobs.")
            return 0

        jobs_this_run = self._compute_jobs_per_run(len(queued))
        logger.info(
            "BatchProcessor: %d queued, processing %d this run (batch_size=%d).",
            len(queued), jobs_this_run, self._batch_size,
        )

        processed = 0
        for row in queued[:jobs_this_run]:
            success = await self._process_row(row, base_resume)
            if success:
                processed += 1

        logger.info("BatchProcessor: cycle done. Processed %d/%d.", processed, jobs_this_run)
        return processed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enqueue_validated(self) -> None:
        rows = self._tracker.list_rows_by_status(JobStatus.VALIDATION_PASSED)
        for row in rows:
            job_id = row.get("id")
            if job_id:
                self._tracker.mark_batch_queued(job_id)
                logger.debug("Queued job %s for batch processing.", job_id)

    def _compute_jobs_per_run(self, queue_depth: int) -> int:
        """
        Compute how many jobs to process per run to meet the SLA.

        jobs_per_run = ceil(queue_depth / runs_in_sla)
        runs_in_sla  = (sla_hours * 60) / interval_minutes
        """
        runs_in_sla = max(1, (self._sla_hours * 60) // self._interval_minutes)
        per_run = math.ceil(queue_depth / runs_in_sla)
        return min(per_run, self._batch_size)

    async def _process_row(self, row: dict, base_resume: str) -> bool:
        job_id = row.get("id")
        if not job_id:
            return False

        raw_desc = row.get("raw_description") or ""
        role = row.get("role") or ""

        if not raw_desc:
            logger.warning("Job %s has no raw_description — marking FAILED.", job_id)
            self._tracker.update(job_id, status=JobStatus.FAILED,
                                 validation_reason="No raw_description")
            return False

        track = select_track(role)
        system_prompt, user_template = get_prompts(track)

        self._tracker.update(job_id, status=JobStatus.AI_IN_PROGRESS)

        last_err: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                result = self._tailor.generate(
                    base_resume_text=base_resume,
                    job_description=raw_desc,
                    track=track,
                    system_prompt=system_prompt,
                    user_template=user_template,
                )
                self._tracker.mark_ai_result(
                    job_id=job_id,
                    tailored_text=result.text,
                    provider=result.provider,
                    cost_usd=result.estimated_cost_usd,
                    pipeline_track=track,
                )
                logger.info(
                    "Job %s tailored OK via %s track=%s cost=$%.4f",
                    job_id, result.provider, track, result.estimated_cost_usd,
                )

                # Render DOCX if renderer is available
                if self._docx_renderer:
                    try:
                        docx_path = self._docx_renderer.render(job_id, result.text)
                        self._tracker.mark_docx_ready(job_id, str(docx_path))
                        logger.info("DOCX ready for job %s at %s", job_id, docx_path)
                    except Exception as docx_exc:
                        logger.warning("DOCX render failed for job %s: %s", job_id, docx_exc)

                return True

            except BudgetExceededError as exc:
                logger.error("Budget exceeded — halting batch: %s", exc)
                self._tracker.update(job_id, status=JobStatus.BATCH_QUEUED)  # re-queue
                raise  # propagate so orchestrator can stop

            except Exception as exc:
                last_err = exc
                wait = 10 * (2 ** (attempt - 1))
                logger.warning(
                    "Job %s AI attempt %d/%d failed: %s. Retrying in %ds.",
                    job_id, attempt, self._max_retries, exc, wait,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(wait)

        logger.error(
            "Job %s permanently failed after %d attempts: %s",
            job_id, self._max_retries, last_err,
        )
        self._tracker.update(
            job_id,
            status=JobStatus.FAILED,
            validation_reason=f"AI failed after {self._max_retries} attempts: {last_err}",
        )
        return False
