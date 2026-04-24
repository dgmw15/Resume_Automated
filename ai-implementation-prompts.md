# AI Implementation Prompt Pack (Updated)

Use these prompts in order. Each block is designed for copy-paste into your AI coding assistant.

Goal of this pack:

1. Add JD technical pass/fail validation.
2. Add 24-hour batch processing.
3. Replace Gemini path with OpenRouter and/or Claude with hard budget stop.
4. Add dual prompt tracks (Data Analyst + Data Engineer).
5. Generate DOCX outputs for downstream review and submission.
6. Add salary extraction with explicit CareersFuture selector parsing.
7. Add toggleable filtering for internships and contract roles.
8. Add a data completeness checker that audits and optionally backfills missing recoverable fields.

---

## New Prompt Series: Salary + Employment Filter Implementation

Use this series first for the newest scope. These prompts are additive and align with the latest automation plan and architecture diagrams.

### Prompt S0: Scope Lock and Non-Regression Guardrails

```text
You are implementing only the latest scope in job_automation:
1) salary extraction from CareersFuture,
2) toggleable employment-type filtering for internship/contract roles.

Rules:
- Do not refactor unrelated modules.
- Keep existing scraping flow and columns backward compatible.
- Add missing columns without breaking existing Excel files.
- Use deterministic parsing/filtering only (no LLM calls for these steps).
- Add tests for every new parser/filter behavior.

Deliverable:
- A short implementation summary + exact files changed.
```

### Prompt S1: Add Salary Config + Selector Mapping

```text
Task: Extend config for salary extraction and selector mapping.

Files to modify:
1. job_automation/config.yaml

Requirements:
1. Ensure salary section exists with:
   - capture_on_listing (bool)
   - capture_on_detail_fallback (bool)
   - default_currency (SGD)
   - parse_locale (en-SG)
   - enable_period_inference (bool)
2. Add explicit CareersFuture selector mapping:
   - salary.selectors.careersfuture.range = span[data-testid="salary-range"]
   - salary.selectors.careersfuture.min_amount = span[data-testid="salary-range"] span.dib:nth-of-type(1)
   - salary.selectors.careersfuture.max_amount = span[data-testid="salary-range"] span.dib:nth-of-type(2)
3. Keep comments concise and practical.

Deliverable:
- Updated config.yaml with defaults and no schema regressions.
```

### Prompt S2: Implement Salary Parser + Tracker Columns

```text
Task: Implement salary parsing and persistence in trawl output.

Files to modify:
1. job_automation/trawl.py

Requirements:
1. Add salary columns to output schema (if missing):
   - salary_raw
   - salary_min
   - salary_max
   - salary_currency
   - salary_period
   - salary_status
2. Implement parser helpers:
   - parse_currency_and_amount(text) -> numeric + cleaned token
   - parse_salary_range(raw_text, min_text, max_text)
3. Use confirmed CareersFuture DOM behavior:
   - wrapper: span[data-testid="salary-range"]
   - first span.dib = min
   - second span.dib = max (contains nested "to")
4. Status behavior:
   - OK when parsed
   - MISSING when no salary wrapper/content
   - AMBIGUOUS for non-numeric salary phrases
   - ERROR only on unexpected parse exceptions
5. If only min exists, set salary_min = salary_max.

Deliverable:
- Salary values written per row with deterministic status.
```

### Prompt S3: Wire CareersFuture Salary Extraction

```text
Task: Extract salary tokens from CareersFuture listing cards/detail pages and pass to salary parser.

Files to modify:
1. job_automation/trawl.py
2. job_automation/adapters/careersfuture.py (if shared selector constants are needed)

Requirements:
1. On listing scrape, attempt to read salary wrapper and first/second amount spans.
2. Save full wrapper text to salary_raw.
3. Strip nested "to" label from second token before parse.
4. If listing-level salary missing and detail fallback is enabled, attempt detail-page salary extraction.
5. Do not fail the listing when salary cannot be parsed.

Deliverable:
- CareersFuture rows include salary fields whenever salary is present in DOM.
```

### Prompt S4: Add Toggleable Internship/Contract Filter

```text
Task: Add deterministic employment-type filtering with independent toggles.

Files to modify:
1. job_automation/config.yaml
2. job_automation/ai/jd_validator.py
3. job_automation/data/tracker.py
4. job_automation/data/models.py (if needed)

Requirements:
1. Add config block employment_filter:
   - enabled
   - exclude_internship
   - exclude_contract
   - filter_stage (pre_validation)
   - unknown_policy (allow)
2. Add detection heuristics from title + description + tags:
   - internship patterns: intern, internship, trainee, student
   - contract patterns: contract, 6-month, 12-month, fixed-term
3. Add tracker fields:
   - employment_type_raw
   - employment_type_normalized
   - employment_filter_status (PASSED/FILTERED/SKIPPED)
   - employment_filter_reason
4. Behavior:
   - Filter internship only when exclude_internship=true
   - Filter contract only when exclude_contract=true
   - When enabled=false set employment_filter_status=SKIPPED
   - Unknown defaults to pass-through unless unknown_policy says otherwise

Deliverable:
- Rows are auditable with explicit filter decisions and reasons.
```

### Prompt S5: Integrate Filter Stage Into Runtime Flow

```text
Task: Place employment filtering in runtime before technical JD validation.

Files to modify:
1. job_automation/core/orchestrator.py
2. job_automation/core/batch_processor.py (if stage assumptions require adjustment)

Requirements:
1. Flow order must be:
   SCRAPED -> employment filter -> JD validation -> batch queue
2. Filtered rows must never enter AI queue.
3. Preserve existing logging style and add clear reason logs.
4. Keep backward-compatible behavior when employment filtering is disabled.

Deliverable:
- Runtime honors toggle settings and prevents unwanted job types from AI processing.
```

### Prompt S6: Focused Test Pack For New Scope

```text
Task: Add tests for salary extraction and employment toggles.

Files to add:
1. job_automation/tests/test_salary_parser.py
2. job_automation/tests/test_employment_filter.py

Files to modify:
1. existing relevant test modules as needed

Requirements:
1. Salary parser tests:
   - "$4,500 to $6,500" range parsing
   - single amount fallback min=max
   - missing wrapper/status=MISSING
   - non-numeric phrase/status=AMBIGUOUS
2. Employment filter tests:
   - internship filtered only when exclude_internship=true
   - contract filtered only when exclude_contract=true
   - both toggles false -> SKIPPED/pass-through
   - unknown type behavior follows unknown_policy
3. Add one integration-style test proving filtered rows never reach AI queue.

Deliverable:
- Deterministic tests that lock in new behavior.
```

### Prompt S7: Final Integration and Runbook Update

```text
Task: Finalize integration and add concise run instructions for the new features.

Files to modify:
1. job_automation/README.md (or docs/developer_guide.md if preferred)
2. job_automation/core/orchestrator.py (only if final wiring is pending)

Requirements:
1. Document how to toggle:
   - salary capture options
   - exclude_internship
   - exclude_contract
2. Include expected tracker columns and statuses.
3. Provide one quick smoke-test command sequence.
4. Verify no unresolved TODOs in modified files.

Deliverable:
- Implementation complete with runnable usage notes.
```

### Recommended Order For New Scope

1. Prompt S0
2. Prompt S1
3. Prompt S2
4. Prompt S3
5. Prompt S4
6. Prompt S5
7. Prompt S6
8. Prompt S7

---

## New Prompt Series: Data Completeness Checker + Backfill

Use this after salary and employment changes are in place so historical rows can be repaired safely.

### Prompt C0: Checker Scope and Safety Rules

```text
Task: Define a deterministic data checker contract before implementing code.

Scope decision:
Phase A/B/C target trawl_results.xlsx ONLY.
Phase D extends to Database.xlsx (tracker) only AFTER tracker salary columns
(salary_raw through salary_status) contain real data from a confirmed migration run.
Do not target Database.xlsx in the initial implementation.

Field data contract for trawl_results.xlsx:
- critical (must be non-empty, unresolvable if missing):
    id, portal, role, url
- recoverable (can be backfilled from existing data or portal refetch):
    company, raw_description, salary_raw
- derived (recompute from other fields, no network needed):
    salary_min, salary_max, salary_currency, salary_period, salary_status

Missing-value categories (checked independently):
1. truly missing — null or empty string
2. semantically missing — salary_status is MISSING, AMBIGUOUS, or ERROR
3. inconsistent — salary_min > salary_max, or currency null while salary_min non-null,
   or salary_status=OK while both salary_min and salary_max are null

Recovery outcome states (exactly one assigned per row):
- COMPLETE          — all fields valid, no action
- RECOVERED_LOCAL   — gap filled by local parse/field copy
- RECOVERED_REFETCH — gap filled by re-fetching source URL
- UNRESOLVED        — gap detected, cannot fill, reason recorded
- SKIPPED_NO_URL    — row has no URL, refetch impossible
- ERROR_FETCH       — refetch attempted but network/selector call failed

Safety rules (non-negotiable):
- dry_run=true by default — no writes unless explicitly set to false
- always create timestamped backup copy before any mutation
- only write rows that changed; unchanged rows are read-only even in recover mode
- idempotent reruns: already-COMPLETE rows are never touched
- UNRESOLVED rows are retried only when policy allows (unresolved_reason_required=true)
- row-level failures do not abort the run; log and continue

Acceptance criteria:
1. Audit mode identifies all three categories of missing data with row-level evidence.
2. Recover mode fills derived salary gaps without network calls.
3. Re-run is idempotent — already-correct rows emit COMPLETE with no writes.
4. Every UNRESOLVED row carries a non-empty reason string.
5. Recovery report is produced on every run regardless of mode.

Deliverable:
- Confirmed contract summary and acceptance criteria — no code yet.
```

### Prompt C1: Add Checker Config Block

```text
Task: Extend config for checker execution and backfill controls.

Files to modify:
1. job_automation/config.yaml

Requirements:
1. Add data_checker section with:
   - enabled
   - run_stage (pre_pipeline)
   - mode (audit_only|recover)
   - targets (workbook file list)
   - write_backup
2. Add backfill controls:
   - allow_portal_refetch
   - max_rows_per_run
   - unresolved_reason_required
3. Add report output path setting.

Deliverable:
- Updated config schema with safe defaults.
```

### Prompt C2: Implement Audit and Deterministic Local Recovery

```text
Task: Build checker logic for missing/inconsistent detection and local salary backfill.

Files to add:
1. job_automation/core/data_checker.py

Files to modify:
1. job_automation/core/salary_parser.py (only if helper reuse requires minor extension)

Requirements:
1. Detect missing and inconsistent salary rows.
2. Attempt local deterministic recovery from salary_raw.
3. Do not use AI calls.
4. Emit structured report with counts by classification state.

Deliverable:
- Runnable checker in audit_only and recover modes.
```

### Prompt C3: Add Optional Refetch Recovery Path

```text
Task: Add controlled source refetch for unresolved rows.

Files to modify:
1. job_automation/core/data_checker.py
2. job_automation/adapters/careersfuture.py (if helper selectors are shared)

Requirements:
1. Refetch only when allow_portal_refetch=true.
2. Respect max_rows_per_run.
3. Tag outcomes as RECOVERED_REFETCH or UNRESOLVED with reason.
4. Continue processing even when individual refetch attempts fail.

Deliverable:
- Controlled backfill workflow with explicit row-level outcomes.
```

### Prompt C4: Tests and Runbook for Checker

```text
Task: Add tests and operational docs for checker behavior.

Files to add:
1. job_automation/tests/test_data_checker.py

Files to modify:
1. job_automation/README.md (or docs/developer_guide.md)

Requirements:
1. Tests for COMPLETE, MISSING, INCONSISTENT, RECOVERED_LOCAL, UNRESOLVED.
2. Idempotency test for repeated checker runs.
3. Refetch path test with capped rows.
4. Document audit_only first-run command and recover command.

Deliverable:
- Test coverage and runbook for safe adoption.
```

### Recommended Order For Checker Scope

1. Prompt C0
2. Prompt C1
3. Prompt C2
4. Prompt C3
5. Prompt C4

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
7. Under data_checker, include:
   - enabled
   - run_stage
   - mode
   - targets
   - write_backup
   - backfill.allow_portal_refetch
   - backfill.max_rows_per_run
   - report_path

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
   - select role profile per row from role/title metadata (do not use one global default)
   - detect deny patterns
   - fail when deny pattern is present OR keyword hits below threshold
3. Add clear logging for pass/fail.
4. Add unit tests for validator edge cases:
   - clearly technical JD
   - clearly insurance-sales JD
   - mixed JD with borderline keyword count
   - analyst/engineer role profile selection differences for same JD text

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
   - ensure lock implementation is Windows-safe and POSIX-safe (no hard dependency on fcntl import on Windows)
4. Update tailor path to use ProviderRouter.
5. Keep retries with backoff for transient network/API failures.
6. Add idempotency key support to prevent duplicate provider charges on retries.
7. Write reservation lifecycle fields back to tracker rows on reserve/commit/release.

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
4. Read active pipeline mode from config (`ai.pipeline_mode`) and log selected mode per job.
5. Persist selected track to tracker field pipeline_track.
6. Add tests for route selection and prompt formatting.

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
6. job_automation/tests/test_data_checker.py

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
10. Add test-suite contract checks ensuring tests reference only existing public symbols.
11. Add Windows runtime test for budget-ledger import/startup path.
12. Add data-checker tests for classification states and recover-mode idempotency.

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
7. Ensure replay behavior returns previously committed logical result payload, not placeholder text.

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
6. Wire cleanup invocation on batch/orchestrator cadence so retention policy is actually enforced.

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
6. Add API-drift tests so `test_provider_router.py` and `test_docx_renderer.py` fail fast when they import missing symbols.
7. Add Windows portability test proving budget-ledger initialization does not raise import errors.

Deliverable:
- Test suite proves critical failure modes are guarded in code.
```

---

## Recommended Execution Sequence

Run prompts in this order:

1. Prompt 0
2. Prompt 1
3. Prompt C0
4. Prompt C1
5. Prompt C2
6. Prompt C3
7. Prompt C4
8. Prompt 2
9. Prompt 3
10. Prompt 4
11. Prompt 5
12. Prompt 6
13. Prompt 7
14. Prompt 8
15. Prompt 9
16. Prompt 11 (critical)
17. Prompt 12 (critical)
18. Prompt 13 (critical)
19. Prompt 14 (critical)
20. Prompt 10 (optional)