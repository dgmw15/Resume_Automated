# Job Application Automation Plan (Updated)

## 1. Objective

Implement the five approved changes in one coherent rollout:

1. JD pass/fail validator gate for technical relevance.
2. 24-hour batch processing model.
3. Migration from Gemini to OpenRouter and/or Claude with hard budget stop.
4. Two-prompt pipeline for Data Analyst and Data Engineer tracks.
5. DOCX downstream output as final artifact.

## 2. Delivery Strategy

Use incremental phases so scraping remains stable while AI and output logic evolve.

### Phase 1: Foundation Refactor

- Create AI provider abstraction layer and router.
- Add config schema for providers, budget caps, batch settings, validator rules, and output paths.
- Keep existing flow working with feature flags disabled by default.

Exit criteria:

- Existing scrape loop still runs.
- New config loads without runtime errors.

### Phase 2: JD Validation Pipeline

- Implement `jd_validator.py` and keyword rule packs.
- Add tracker status transitions for validation outcomes.
- Block non-technical jobs from entering AI queue.

Exit criteria:

- Rows receive deterministic pass/fail with reason text.
- Non-technical listings are skipped and logged.

### Phase 3: Batch Processor (24h SLA)

- Add queue selection from `VALIDATION_PASSED` rows.
- Process by interval and batch size controls.
- Add retry and deferred requeue logic.

Exit criteria:

- Queue drains predictably within 24h target window under normal load.
- Failures are retried with capped attempts.

### Phase 4: Provider Migration + Budget Guardrails

- Implement OpenRouter and Anthropic clients.
- Add provider fallback order.
- Add hard budget stop and spend ledger.

Exit criteria:

- Runtime blocks requests after cap breach.
- Spend reports are persisted daily.

### Phase 5: Two-Prompt Curation

- Add analyst and engineer prompt templates.
- Implement routing mode (`role_hint` first, optional classifier).
- Save selected track metadata in tracker.

Exit criteria:

- Each tailored output has explicit prompt track attribution.
- Prompt route is reproducible from logged metadata.

### Phase 6: DOCX Output and Review Integration

- Add `python-docx` renderer and optional template-based formatting.
- Save document path in tracker.
- Update review flow to use DOCX artifact.

Exit criteria:

- Every successful tailored row emits a valid `.docx` file.
- Reviewer can open generated document directly from tracked path.

## 3. Detailed Work Breakdown

## 3.1 Code-Level Changes

- `job_automation/ai/providers/base.py`: provider interface.
- `job_automation/ai/providers/openrouter_client.py`: OpenRouter implementation.
- `job_automation/ai/providers/anthropic_client.py`: Claude implementation.
- `job_automation/ai/provider_router.py`: provider selection and fallback.
- `job_automation/ai/jd_validator.py`: keyword + deny-pattern scoring.
- `job_automation/ai/pipeline.py`: analyst/engineer orchestration.
- `job_automation/core/batch_processor.py`: queue execution.
- `job_automation/output/docx_renderer.py`: final DOCX generation.
- `job_automation/data/tracker.py`: status and metadata columns.
- `job_automation/core/orchestrator.py`: split scraping and batch processing flows.
- `job_automation/config.yaml`: new config sections.

## 3.2 Config Additions

Add these top-level keys:

- `validation`
- `batch`
- `ai`
- `output`

Suggested starting values:

- `batch.target_sla_hours: 24`
- `batch.interval_minutes: 30`
- `batch.batch_size: 5`
- `ai.budget.hard_stop: true`

## 3.3 Excel Tracker Evolution

Add columns:

- `validation_score`
- `validation_reason`
- `pipeline_track`
- `ai_provider_used`
- `cost_usd`
- `docx_path`
- `processed_at`

Backward compatibility plan:

- On startup, detect missing columns and append them automatically.

## 4. Automation Timing Model

Recommended schedule:

1. Scraper loop runs continuously (existing behavior).
2. Batch worker wakes every `interval_minutes`.
3. Worker computes budget and throughput gates before each execution.
4. If budget exceeded, worker sets rows to deferred state and exits gracefully.

Throughput sizing formula:

$$
	ext{batch size per run} = \left\lceil \frac{\text{queue depth}}{\text{runs remaining in 24h}} \right\rceil
$$

This keeps processing slow and cost-aware while still meeting the 24h objective.

## 5. Quality and Risk Controls

1. Prompt hallucination guard: deterministic checks for additions not present in base resume.
2. Provider outage risk: fallback order and capped retries.
3. Cost overrun risk: hard stop with explicit reason logging.
4. False negatives in validator: maintain reviewed allowlist to recover edge-case technical roles.
5. DOCX formatting drift: template-anchored rendering with smoke tests.

## 6. Test Plan

Minimum automated tests to add:

1. `jd_validator` unit tests for pass/fail thresholds and deny-pattern matches.
2. `provider_router` tests for primary/fallback/budget-stop behavior.
3. `pipeline` tests for analyst vs engineer route selection.
4. `batch_processor` tests for queue slicing and retry/defer logic.
5. `docx_renderer` tests for file creation and non-empty output.

Manual checks:

1. Run end-to-end with at least 10 mixed SG listings.
2. Verify insurance-style listings are blocked before AI call.
3. Verify generated DOCX opens cleanly in Microsoft Word.

## 7. Acceptance Criteria by Line Item

1. JD validation: AI is never called when listing fails technical threshold.
2. Batch processing: all queued valid jobs processed within 24 hours in normal operations.
3. Provider switch: Gemini removed from active path; OpenRouter/Claude operational with hard cap.
4. Two-prompt pipeline: every output tagged as analyst or engineer stream.
5. DOCX output: every tailored row has an accessible `.docx` artifact path.

## 8. Recommended Execution Order (Practical)

1. Implement provider abstraction and config migration.
2. Implement validator gate and tracker status migration.
3. Implement batch processor.
4. Implement dual-prompt pipeline.
5. Implement DOCX rendering and review handoff.
6. Run full integration and tune keyword thresholds on real SG samples.
