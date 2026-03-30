"""Tests for core/batch_processor.py"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ai.providers.base import BudgetExceededError, ProviderResult
from core.batch_processor import BatchProcessor
from data.models import JobStatus


def _make_batch_cfg(**overrides):
    cfg = {
        "batch_size": 5,
        "target_sla_hours": 24,
        "max_retries": 3,
        "interval_minutes": 30,
    }
    cfg.update(overrides)
    return cfg


def _make_row(job_id="job-1", role="Data Analyst", raw_description="sql python tableau"):
    return {
        "id": job_id,
        "role": role,
        "raw_description": raw_description,
        "company": "Acme",
        "url": "http://example.com",
    }


def _make_processor(tracker, tailor, cfg=None, docx_renderer=None):
    return BatchProcessor(tracker, tailor, cfg or _make_batch_cfg(), docx_renderer=docx_renderer)


@pytest.fixture
def base_resume_file(tmp_path):
    p = tmp_path / "base_resume.txt"
    p.write_text("My resume content.")
    return p


class TestBatchProcessorComputeJobsPerRun:
    def test_small_queue_small_run(self):
        proc = _make_processor(MagicMock(), MagicMock())
        # 10 queued, 48 runs in sla => ceil(10/48) = 1, capped at 5
        result = proc._compute_jobs_per_run(10)
        assert result >= 1
        assert result <= 5

    def test_large_queue_respects_batch_size(self):
        proc = _make_processor(MagicMock(), MagicMock(), _make_batch_cfg(batch_size=3))
        result = proc._compute_jobs_per_run(1000)
        assert result <= 3


class TestBatchProcessorEnqueue:
    def test_enqueues_validation_passed_rows(self):
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row("j1"), _make_row("j2")]
        proc = _make_processor(tracker, MagicMock())
        proc._enqueue_validated()
        assert tracker.mark_batch_queued.call_count == 2


class TestBatchProcessorRunOnce:
    def test_skips_if_no_base_resume(self, tmp_path):
        tracker = MagicMock()
        proc = _make_processor(tracker, MagicMock())
        # Patch BASE_RESUME_PATH to non-existent
        with patch("core.batch_processor.BASE_RESUME_PATH", tmp_path / "missing.txt"):
            result = asyncio.run(proc.run_once())
        assert result == 0

    def test_processes_queued_rows(self, base_resume_file):
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row()]
        mock_result = ProviderResult(
            text="tailored", model="m", provider="anthropic",
            estimated_cost_usd=0.01,
        )
        tailor = MagicMock()
        tailor.generate.return_value = mock_result
        proc = _make_processor(tracker, tailor)

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            count = asyncio.run(proc.run_once())

        assert count == 1
        tracker.mark_ai_result.assert_called_once()

    def test_budget_exceeded_re_queues_and_raises(self, base_resume_file):
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row()]
        tailor = MagicMock()
        tailor.generate.side_effect = BudgetExceededError("cap hit")
        proc = _make_processor(tracker, tailor)

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            with pytest.raises(BudgetExceededError):
                asyncio.run(proc.run_once())

        # Row should be re-queued (mark_batch_queued called)
        tracker.mark_batch_queued.assert_called()

    def test_retry_exhaustion_marks_failed(self, base_resume_file):
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row()]
        tailor = MagicMock()
        tailor.generate.side_effect = RuntimeError("transient error")
        proc = _make_processor(tracker, tailor, _make_batch_cfg(max_retries=2))

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                count = asyncio.run(proc.run_once())

        assert count == 0
        tracker.update.assert_called()
        # Verify the update was called with FAILED status
        call_args = tracker.update.call_args
        assert call_args.kwargs.get("status") == JobStatus.FAILED or \
               (len(call_args.args) > 1 and call_args.args[1] == JobStatus.FAILED)

    def test_docx_rendered_on_success(self, base_resume_file):
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row()]
        mock_result = ProviderResult(
            text="tailored", model="m", provider="anthropic",
            estimated_cost_usd=0.01,
        )
        tailor = MagicMock()
        tailor.generate.return_value = mock_result
        docx_renderer = MagicMock()
        docx_renderer.render.return_value = Path("/output/docs/job-1.docx")
        proc = _make_processor(tracker, tailor, docx_renderer=docx_renderer)

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            asyncio.run(proc.run_once())

        docx_renderer.render.assert_called_once_with("job-1", "tailored")
        tracker.mark_docx_ready.assert_called_once()
