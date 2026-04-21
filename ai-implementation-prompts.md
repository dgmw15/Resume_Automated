# AI Implementation Prompt Pack (Updated)

Use these prompts in order. Each block is designed for copy-paste into your AI coding assistant.

Goal of this pack:

1. Add JD technical pass/fail validation.
2. Add 24-hour batch processing.
3. Replace Gemini path with OpenRouter and/or Claude with hard budget stop.
4. Add dual prompt tracks (Data Analyst + Data Engineer).
5. Generate DOCX outputs for downstream review and submission.

---

## Critical Risk Planning Layer

### Risk: DOCX Render Failure is Silent

**Problem Statement:**
When `docx_renderer.py` generates a DOCX file, the orchestrator marks status as `DOCX_READY` upon successful write. However:
- File corruption during write is not detected
- Writer crashes mid-document leave incomplete files
- Tracker shows "ready" but file is unreadable
- User downloads corrupt document with no warning

**Planning Implications:**
- **Prompt 7** must implement defensive file generation:
  - Write to temporary file first
  - Validate generated file is readable (re-open and check)
  - Only move to final location after validation passes
  - If validation fails, retain temp file for debugging, set status to `DOCX_GENERATION_FAILED`
- Add to tracker schema: `docx_validation_error` field for error details
- Add test: generate DOCX, verify it opens and contains expected content

**Why This Matters:**
Silent corruption is worse than obvious failure (user wastes time, trust lost).

---

### Risk: Provider Cost Overrun Between Checks

**Problem Statement:**
Hard cost stop is checked once per minute/poll cycle. In that interval:
- Multiple batch jobs can queue up
- All fire simultaneous API requests
- By the time next check runs, monthly/daily cap is already exceeded
- System incurs debt before hard stop engages

**Example Scenario:**
- Daily cap: $50
- Current spend: $49
- Batch processor queues 5 concurrent jobs
- All 5 hit Claude API before next cost check
- Spend jumps to $65 before hard stop detects overage
- Bill now 30% over budget

**Planning Implications:**
- **Prompt 4** (Provider Abstraction) must implement cost-per-request locking:
  - Before calling provider, acquire cost "reservation" (tentative deduct from daily cap)
  - On provider response, confirm actual usage or release unused reservation
  - If cap exceeded during reservation, reject request immediately with `BudgetExceededError`
- Track estimated vs actual costs separately in tracker
- Add to config: `cost_lock_timeout` (seconds to hold reservation if provider hangs)
- Add test: simulate concurrent requests, verify hard stop catches overrun in first request not fifth

**Why This Matters:**
Cost is user's sole hard constraint. Overruns break trust and business model.

---

### Additional Critical Concerns (Must Be Planned Before Build)

1. **Status model mismatch risk**
   - Risk: `DOCX_GENERATION_FAILED` is referenced in risk planning but not consistently included in status flow sections.
   - Critical change: Add explicit failure status and transitions in Prompt 3 and Prompt 8.

2. **Non-atomic cost reservations across workers**
   - Risk: In-memory locking fails if multiple workers/processes run concurrently.
   - Critical change: Cost reservation must be persisted in shared storage and updated atomically.

3. **Stale reservation leakage**
   - Risk: Provider timeout can strand reserved budget and block processing.
   - Critical change: Add reservation expiry, cleanup cadence, and recovery behavior.

4. **Budget boundary ambiguity**
   - Risk: Day/month reset and rounding differences cause inconsistent hard-stop behavior.
   - Critical change: Define timezone, reset boundaries, decimal precision, and compare rules.

5. **Weak DOCX acceptance criteria**
   - Risk: "File opens" is insufficient; structurally valid but empty/truncated files can pass.
   - Critical change: Validate minimum content/sections before setting `DOCX_READY`.

6. **Temp/debug artifact growth and data exposure**
   - Risk: Retained temp files accumulate sensitive data and storage overhead.
   - Critical change: Add retention policy, cleanup job, and redaction/sanitization rule.

7. **Retry idempotency gaps**
   - Risk: Retries can produce duplicate provider calls or duplicate DOCX writes.
   - Critical change: Add idempotency key per job and deduplicate writes/results.

8. **Unmeasurable concurrency test criteria**
   - Risk: Tests pass without proving budget safety under contention.
   - Critical change: Add deterministic invariants (spend never exceeds cap + epsilon).

---

## Prompt 0: Global Guardrails For The Coding Agent

```text
You are implementing changes in an existing Python project: job_automation.

Mandatory rules:
1. Preserve existing behavior unless explicitly changed.
2. Do not remove current adapters or tracker behavior.
3. Keep code modular and production-safe (logging, retries, defensive checks).
4. Do not hallucinate missing site selectors; keep placeholders where unknown.
5. Use small incremental commits in structure (but do not run git commit).
6. After each code change, run available tests or lint checks and report errors.

Execution style:
- Implement only the requested scope for each prompt.
- Show exact file-level changes.
- Stop and wait for next prompt.
```

---

## Prompt 1: Add Config Schema For New Pipeline

```text
Task: Update config.yaml schema to support validation, batching, provider routing, and DOCX output.

Files to modify:
1. job_automation/config.yaml

Requirements:
1. Keep existing keys intact where possible.
2. Add new top-level sections:
   - validation
   - batch
   - ai
   - output
3. Under validation, include:
   - role_keyword_sets for analyst and engineer
   - deny_patterns for insurance/sales bait
   - min_keyword_hits
4. Under batch, include:
   - enabled
   - interval_minutes
   - batch_size
   - target_sla_hours (default 24)
   - max_retries
5. Under ai, include:
   - provider (openrouter or anthropic)
   - fallback_order
   - model_map (analyst/engineer model names)
   - budget with daily_cap_usd, monthly_cap_usd, hard_stop
   - budget_timezone (default UTC)
   - budget_precision_decimals (default 4)
   - cost_lock_timeout_seconds
   - reservation_cleanup_interval_seconds
6. Under output, include:
   - docx_output_dir
   - docx_template_path (optional)
   - docx_temp_retention_hours
   - docx_validation_required_sections

Deliverable:
- Updated config.yaml with sane defaults and comments.
```

---

## Prompt 2: Implement JD Validator Gate

```text
Task: Build a deterministic JD technical relevance validator to filter fake non-technical postings.

Files to add:
1. job_automation/ai/jd_validator.py

Files to modify:
1. job_automation/data/models.py (if needed for new result model)
2. job_automation/core/orchestrator.py (wire validation step only, no batch yet)

Requirements:
1. Create ValidationResult dataclass/model with:
   - is_pass: bool
   - score: int
   - matched_keywords: list[str]
   - matched_deny_patterns: list[str]
   - reason: str
2. Validator should:
   - normalize text
   - count technical keyword hits from selected role profile
   - detect deny patterns
   - fail when deny pattern is present OR keyword hits below threshold
3. Add clear logging for pass/fail.
4. Add unit tests for validator edge cases:
   - clearly technical JD
   - clearly insurance-sales JD
   - mixed JD with borderline keyword count

Deliverable:
- Working validator module and tests.
```

---

## Prompt 3: Expand Excel Tracker For New States And Metadata

```text
Task: Upgrade Excel tracker schema and status flow for validation, batch, provider, and DOCX metadata.

Files to modify:
1. job_automation/data/tracker.py
2. job_automation/data/models.py

Requirements:
1. Extend statuses to include:
   - VALIDATION_PENDING
   - VALIDATION_FAILED_NON_TECH
   - VALIDATION_PASSED
   - BATCH_QUEUED
   - AI_IN_PROGRESS
   - TAILORED_TEXT_READY
   - DOCX_GENERATION_FAILED
   - DOCX_READY
2. Add columns if missing:
   - validation_score
   - validation_reason
   - pipeline_track
   - ai_provider_used
   - cost_reserved_usd
   - cost_actual_usd
   - cost_usd
   - reservation_id
   - reservation_expires_at
   - docx_path
   - docx_validation_error
   - idempotency_key
   - processed_at
3. Ensure backward compatibility:
   - existing Database.xlsx should be migrated in place by adding missing columns.
4. Add helper APIs:
   - list_rows_by_status(status)
   - mark_validation_result(...)
   - mark_batch_queued(...)
   - mark_ai_result(...)
   - mark_docx_ready(...)

Deliverable:
- Tracker can read old files and write new fields safely.
```

---

## Prompt 4: Introduce AI Provider Abstraction (OpenRouter + Claude)

```text
Task: Replace direct Gemini coupling with provider abstraction and routing.

Files to add:
1. job_automation/ai/providers/base.py
2. job_automation/ai/providers/openrouter_client.py
3. job_automation/ai/providers/anthropic_client.py
4. job_automation/ai/provider_router.py

Files to modify:
1. job_automation/ai/tailor.py
2. job_automation/core/orchestrator.py
3. job_automation/requirements.txt

Requirements:
1. Define a common provider interface:
   - generate(prompt, system_prompt, model, max_tokens, temperature) -> ProviderResult
2. ProviderResult must include:
   - text
   - model
   - provider
   - estimated_cost_usd
   - raw_usage_tokens (if available)
3. Add budget guard:
   - load daily/monthly caps from config
   - hard stop when exceeded
   - return explicit error type BudgetExceededError
   - persist reservation in shared state before provider call
   - enforce atomic reservation updates across concurrent workers
   - expire stale reservations based on cost_lock_timeout_seconds
   - define budget boundary semantics (timezone/reset/precision/rounding)
4. Update tailor path to use ProviderRouter.
5. Keep retries with backoff for transient network/API failures.
6. Add idempotency key support to prevent duplicate provider charges on retries.

Deliverable:
- Gemini no longer required in active execution path.
```

---

## Prompt 5: Add Two-Prompt Pipeline (Analyst + Engineer)

```text
Task: Split prompt strategy into two role-specific pipelines and route jobs to the right prompt set.

Files to modify:
1. job_automation/ai/prompts.py

Files to add:
1. job_automation/ai/pipeline.py

Files to modify (wiring):
1. job_automation/ai/tailor.py
2. job_automation/core/orchestrator.py

Requirements:
1. In prompts.py define:
   - ANALYST_SYSTEM_PROMPT
   - ANALYST_USER_TEMPLATE
   - ENGINEER_SYSTEM_PROMPT
   - ENGINEER_USER_TEMPLATE
2. Build pipeline selector with modes:
   - role_hint
   - classifier
3. Default to role_hint using job title + configured role mappings.
4. Persist selected track to tracker field pipeline_track.
5. Add tests for route selection and prompt formatting.

Deliverable:
- Each processed job is tagged and generated via analyst or engineer prompt track.
```

---

## Prompt 6: Implement 24-Hour Batch Processor

```text
Task: Add slow-cost batch processing so tailoring is completed within 24 hours, not immediately.

Files to add:
1. job_automation/core/batch_processor.py

Files to modify:
1. job_automation/core/orchestrator.py

Requirements:
1. BatchProcessor should:
   - fetch VALIDATION_PASSED rows
   - queue rows as BATCH_QUEUED
   - process in chunks using batch_size and interval_minutes
2. Throughput control:
   - compute jobs-per-run based on queue depth and target_sla_hours
3. Retries:
   - exponential backoff
   - capped attempts using config batch.max_retries
   - preserve idempotency key across retry attempts
4. On success:
   - save tailored text
   - set TAILORED_TEXT_READY
5. On permanent failure:
   - set FAILED with reason
6. Add SLA drift checks and log/flag when projected completion exceeds target_sla_hours.

Deliverable:
- Batch worker integrated into orchestrator loop with clear logs.
```

---

## Prompt 7: Add DOCX Downstream Output

```text
Task: Render tailored resume outputs to DOCX files and track output paths.

Files to add:
1. job_automation/output/docx_renderer.py
2. job_automation/output/__init__.py

Files to modify:
1. job_automation/core/orchestrator.py
2. job_automation/data/tracker.py
3. job_automation/requirements.txt

Requirements:
1. Use python-docx.
2. Render output for each successful tailored result:
   - file path pattern: output/docs/{job_id}.docx
3. Optionally load a .docx template if configured.
4. Save generated doc path into tracker docx_path.
5. Write to temp file first, then validate before final move.
6. Validate DOCX acceptance criteria before marking success:
   - file opens without exception
   - non-empty body/content
   - required sections present (config-driven)
7. On DOCX validation failure:
   - set status DOCX_GENERATION_FAILED
   - set docx_validation_error
   - retain temporary artifact only within configured retention window
8. Set status DOCX_READY only after final move + validation.
9. Add integration tests for success path and validation-failure path.

Deliverable:
- End-to-end tailored text to DOCX generation working.
```

---

## Prompt 8: Full Integration Pass

```text
Task: Perform an end-to-end integration pass for the new pipeline.

Files to modify as needed:
- job_automation/core/orchestrator.py
- job_automation/main.py
- job_automation/data/tracker.py
- job_automation/ai/tailor.py

Requirements:
1. Ensure final flow is:
   SCRAPED -> VALIDATION_PENDING -> VALIDATION_PASSED/FAILED -> BATCH_QUEUED -> AI_IN_PROGRESS -> TAILORED_TEXT_READY -> DOCX_READY/DOCX_GENERATION_FAILED
2. Ensure non-technical postings never call AI provider.
3. Ensure budget hard stop prevents additional AI calls.
4. Ensure errors are logged with actionable messages.
5. Provide concise run instructions.
6. Ensure idempotency across provider retries and DOCX writes.

Deliverable:
- Final integrated implementation with no dead code paths.
```

---

## Prompt 9: Test Suite Expansion

```text
Task: Add targeted tests for the new architecture.

Files to add:
1. job_automation/tests/test_jd_validator.py
2. job_automation/tests/test_provider_router.py
3. job_automation/tests/test_pipeline_selector.py
4. job_automation/tests/test_batch_processor.py
5. job_automation/tests/test_docx_renderer.py

Requirements:
1. Use pytest style.
2. Mock external provider calls.
3. Cover budget exceeded path.
4. Cover retry exhaustion path.
5. Keep tests deterministic and fast.
6. Add concurrency tests for reservation safety:
   - invariant: committed spend never exceeds configured cap (+ defined epsilon)
7. Add stale reservation cleanup test.
8. Add DOCX corrupted/empty output validation-failure test.
9. Add idempotency test for duplicated retry execution.

Deliverable:
- Tests pass locally and validate critical behavior.
```

---

## Prompt 10: Prompt Content Quality Tuning (Optional)

```text
Task: Improve prompt quality and consistency for both analyst and engineer tracks.

Files to modify:
1. job_automation/ai/prompts.py

Requirements:
1. Keep strict anti-hallucination rules.
2. Make analyst prompt prioritize:
   - SQL, BI, dashboarding, stakeholder reporting, experimentation, metrics.
3. Make engineer prompt prioritize:
   - data pipelines, ETL/ELT, orchestration, cloud data stack, reliability.
4. Keep output plain text suitable for DOCX rendering.
5. Add short inline examples in comments for maintenance.

Deliverable:
- Stronger role-specific prompt behavior with clean formatting.
```

---

## Prompt 11: Atomic Budget Reservation Ledger (Critical)

```text
Task: Implement atomic, cross-worker budget reservation so cost caps cannot be exceeded under concurrency.

Files to add:
1. job_automation/core/budget_ledger.py

Files to modify:
1. job_automation/ai/provider_router.py
2. job_automation/data/tracker.py
3. job_automation/data/models.py
4. job_automation/config.yaml

Requirements:
1. Implement reservation lifecycle:
   - reserve(job_id, estimated_cost, idempotency_key)
   - commit(reservation_id, actual_cost)
   - release(reservation_id, reason)
2. Reservations must be persisted in shared state and updated atomically.
3. Define and enforce budget boundaries:
   - timezone for daily reset (config-driven)
   - monthly reset boundary
   - fixed decimal precision and rounding mode
4. Add stale reservation cleanup:
   - expire after cost_lock_timeout_seconds
   - cleanup cadence via reservation_cleanup_interval_seconds
5. If reservation cannot be acquired, raise BudgetExceededError before provider call.
6. Persist reservation metadata in tracker:
   - reservation_id
   - reservation_expires_at
   - cost_reserved_usd
   - cost_actual_usd

Deliverable:
- Provider calls are blocked unless reservation succeeds, with deterministic cap enforcement across concurrent workers.
```

---

## Prompt 12: DOCX Atomic Write + Validation Gate (Critical)

```text
Task: Make DOCX output path fail-safe and content-validated before final success state.

Files to modify:
1. job_automation/output/docx_renderer.py
2. job_automation/core/orchestrator.py
3. job_automation/data/tracker.py
4. job_automation/config.yaml

Requirements:
1. Implement safe write workflow:
   - write DOCX to temp path
   - reopen and validate content
   - atomically move to final path only after validation passes
2. Validation criteria must include:
   - file opens successfully
   - non-empty body
   - required sections from config output.docx_validation_required_sections
3. On failure:
   - set status DOCX_GENERATION_FAILED
   - save docx_validation_error
   - keep temporary artifact only within configured retention window
4. Add retention cleanup behavior for temp artifacts.
5. Do not set DOCX_READY unless final move and validation are complete.

Deliverable:
- Corrupted, partial, or empty DOCX outputs never reach DOCX_READY.
```

---

## Prompt 13: End-to-End Idempotency and Retry Safety (Critical)

```text
Task: Ensure retries and duplicate executions do not create duplicate provider charges or duplicate outputs.

Files to modify:
1. job_automation/core/batch_processor.py
2. job_automation/ai/provider_router.py
3. job_automation/core/orchestrator.py
4. job_automation/data/tracker.py
5. job_automation/data/models.py

Requirements:
1. Generate and persist idempotency_key per job processing attempt group.
2. Reuse same idempotency_key across retries for the same job.
3. Provider requests must be deduplicated by idempotency_key.
4. DOCX generation must be idempotent:
   - avoid duplicate writes
   - avoid duplicate status transitions
5. On replay/duplicate execution, return existing committed result instead of re-charging or rewriting.
6. Add clear logs for dedupe hits and replay behavior.

Deliverable:
- Same logical job can be safely retried/replayed without financial or output duplication.
```

---

## Prompt 14: Hardening Test Pack for Edge Cases (Critical)

```text
Task: Add deterministic tests that prove concurrency safety, recovery behavior, and doc integrity guarantees.

Files to modify:
1. job_automation/tests/test_provider_router.py
2. job_automation/tests/test_batch_processor.py
3. job_automation/tests/test_docx_renderer.py

Files to add (if needed):
1. job_automation/tests/test_budget_ledger.py

Requirements:
1. Concurrency budget safety test:
   - simulate parallel reservations
   - assert invariant: committed spend never exceeds cap (+ defined epsilon)
2. Stale reservation cleanup test:
   - create expired reservations
   - run cleanup
   - verify budget becomes available again
3. Idempotency replay test:
   - replay same job/idempotency_key
   - verify no extra provider charge and no duplicate DOCX write
4. DOCX integrity test:
   - corrupted/empty/partial output must fail validation
   - status must be DOCX_GENERATION_FAILED with error recorded
5. Keep tests fast, deterministic, and isolated from live provider APIs.

Deliverable:
- Test suite proves critical failure modes are guarded in code.
```

---

## Recommended Execution Sequence

Run prompts in this order:

1. Prompt 0
2. Prompt 1
3. Prompt 2
4. Prompt 3
5. Prompt 4
6. Prompt 5
7. Prompt 6
8. Prompt 7
9. Prompt 8
10. Prompt 9
11. Prompt 11 (critical)
12. Prompt 12 (critical)
13. Prompt 13 (critical)
14. Prompt 14 (critical)
15. Prompt 10 (optional)