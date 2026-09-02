"""
tests/test_batch_processor.py — Tests for core/batch_processor.py.

Covers:
1. SLA batch sizing (compute_jobs_per_run)
2. Enqueue: moves VALIDATION_PASSED → BATCH_QUEUED
3. run_once: skips when base_resume.txt is missing
4. run_once: processes queued rows successfully
5. BudgetExceededError re-queues and propagates
6. Retry exhaustion marks FAILED
7. DOCX rendered after successful AI call
8. DOCX validation failure sets DOCX_GENERATION_FAILED (not FAILED)
9. Idempotency: stable key derived from job_id, reused across retries
10. SLA drift logging when queue is too deep
"""
import asyncio
import uuid
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

from ai.providers.base import BudgetExceededError, ProviderResult
from core.batch_processor import BatchProcessor
from data.models import JobStatus
from output.docx_renderer import DocxValidationError


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

    def test_docx_validation_failure_marks_docx_generation_failed(self, base_resume_file):
        """
        When DocxRenderer raises DocxValidationError, the job should be marked
        DOCX_GENERATION_FAILED — not FAILED — because AI tailoring succeeded.
        """
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row()]
        mock_result = ProviderResult(
            text="tailored", model="m", provider="anthropic",
            estimated_cost_usd=0.01,
        )
        tailor = MagicMock()
        tailor.generate.return_value = mock_result
        docx_renderer = MagicMock()
        docx_renderer.render.side_effect = DocxValidationError("Body is empty")
        proc = _make_processor(tracker, tailor, docx_renderer=docx_renderer)

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            count = asyncio.run(proc.run_once())

        # AI succeeded → counted as processed
        assert count == 1
        tracker.mark_docx_failed.assert_called_once()
        call_args = tracker.mark_docx_failed.call_args
        assert "job-1" in str(call_args)


class TestIdempotencyKey:
    def test_stable_key_derived_from_job_id(self):
        """The same job_id must always produce the same idempotency_key."""
        key1 = BatchProcessor._make_idempotency_key("job-xyz")
        key2 = BatchProcessor._make_idempotency_key("job-xyz")
        assert key1 == key2

    def test_different_job_ids_produce_different_keys(self):
        key1 = BatchProcessor._make_idempotency_key("job-aaa")
        key2 = BatchProcessor._make_idempotency_key("job-bbb")
        assert key1 != key2

    def test_key_is_valid_uuid(self):
        key = BatchProcessor._make_idempotency_key("job-test")
        # Must not raise
        parsed = uuid.UUID(key)
        assert str(parsed) == key

    def test_idempotency_key_passed_to_tailor(self, base_resume_file):
        """batch_processor must forward idempotency_key to tailor.generate()."""
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row("job-idem")]
        mock_result = ProviderResult(
            text="tailored", model="m", provider="anthropic",
            estimated_cost_usd=0.01,
        )
        tailor = MagicMock()
        tailor.generate.return_value = mock_result
        proc = _make_processor(tracker, tailor)

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            asyncio.run(proc.run_once())

        call_kwargs = tailor.generate.call_args.kwargs
        assert "idempotency_key" in call_kwargs
        assert call_kwargs["idempotency_key"] == BatchProcessor._make_idempotency_key("job-idem")


class TestCoverageAndCritic:
    def test_keyword_coverage_written_on_success(self, base_resume_file):
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row(raw_description="sql python tableau")]
        mock_result = ProviderResult(
            text="tailored resume mentioning sql and python",
            model="m", provider="anthropic", estimated_cost_usd=0.01,
        )
        tailor = MagicMock()
        tailor.generate.return_value = mock_result
        proc = _make_processor(tracker, tailor)

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            asyncio.run(proc.run_once())

        coverage_calls = [
            c for c in tracker.update.call_args_list
            if "keyword_coverage_score" in c.kwargs
        ]
        assert len(coverage_calls) == 1
        assert coverage_calls[0].kwargs["keyword_coverage_score"] > 0

    def test_critic_invoked_and_result_written_when_configured(self, base_resume_file):
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row()]
        mock_result = ProviderResult(
            text="tailored", model="m", provider="anthropic", estimated_cost_usd=0.01,
        )
        tailor = MagicMock()
        tailor.generate.return_value = mock_result
        critic = MagicMock()
        from ai.critic import CritiqueResult
        critic.critique.return_value = CritiqueResult(
            coverage_pct=90, missing=[], concerns="none", verdict="PASS", raw_text="raw"
        )
        proc = BatchProcessor(tracker, tailor, _make_batch_cfg(), critic=critic)

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            asyncio.run(proc.run_once())

        critic.critique.assert_called_once()
        ats_calls = [c for c in tracker.update.call_args_list if "ats_verdict" in c.kwargs]
        assert len(ats_calls) == 1
        assert ats_calls[0].kwargs["ats_verdict"] == "PASS"

    def test_critic_failure_does_not_fail_job(self, base_resume_file):
        tracker = MagicMock()
        tracker.list_rows_by_status.return_value = [_make_row()]
        mock_result = ProviderResult(
            text="tailored", model="m", provider="anthropic", estimated_cost_usd=0.01,
        )
        tailor = MagicMock()
        tailor.generate.return_value = mock_result
        critic = MagicMock()
        critic.critique.side_effect = RuntimeError("provider down")
        proc = BatchProcessor(tracker, tailor, _make_batch_cfg(), critic=critic)

        with patch("core.batch_processor.BASE_RESUME_PATH", base_resume_file):
            count = asyncio.run(proc.run_once())

        assert count == 1  # job still counts as processed despite critique failure


class TestSLADrift:
    def test_sla_drift_warning_logged(self, caplog):
        """When queue_depth > max_clearable, a warning must be logged."""
        import logging
        proc = _make_processor(
            MagicMock(), MagicMock(),
            _make_batch_cfg(batch_size=1, interval_minutes=60, target_sla_hours=1)
        )
        # With batch_size=1, interval=60min, sla=1h → runs_in_sla=1, max_clearable=1
        # queue_depth=5 → drift
        with caplog.at_level(logging.WARNING, logger="core.batch_processor"):
            proc._check_sla_drift(queue_depth=5)

        assert any("SLA DRIFT" in r.message for r in caplog.records)
