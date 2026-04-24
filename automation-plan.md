# Job Application Automation Plan (Updated)

## 1. Objective

Implement the five approved changes in one coherent rollout:

1. JD pass/fail validator gate for technical relevance.
2. 24-hour batch processing model.
3. Migration from Gemini to OpenRouter and/or Claude with hard budget stop.
4. Two-prompt pipeline for Data Analyst and Data Engineer tracks.
5. DOCX downstream output as final artifact.
6. Salary capture from scraped listings with normalized fields for downstream filtering and ranking.
7. Optional employment-type filtering to exclude internships and/or contract roles.

## 2. Delivery Strategy

Use incremental phases so scraping remains stable while AI and output logic evolve.

### Phase 1: Foundation Refactor

- Create AI provider abstraction layer and router.
- Add config schema for providers, budget caps, batch settings, validator rules, and output paths.
- Keep existing flow working with feature flags disabled by default.

Exit criteria:

- Existing scrape loop still runs.
- New config loads without runtime errors.

### Phase 2: Salary Capture and Normalization

- Add salary extraction during listing scrape and (when needed) during job-detail fetch.
- Persist both raw salary text and normalized numeric fields in tracker output.
- Standardize salary into explicit structure: min, max, currency, and period.
- Add confidence/status tags for missing, ambiguous, and parsed salary states.
- Use explicit CareersFuture selectors for salary range capture to avoid brittle text scraping.

Exit criteria:

- New rows include salary fields when salary is present on listing or detail page.
- Parser marks unknown/ambiguous salary text deterministically without crashing scrape.
- Existing scraping throughput does not regress materially.

### Phase 3: Employment-Type Filtering (Toggleable)

- Add deterministic employment-type detection from title and description text.
- Add independent toggles for internship and contract exclusion.
- Preserve filtered listings in tracker with explicit filter reason.

Exit criteria:

- Internship and contract exclusion can be turned on/off independently.
- Filtered rows are tagged with deterministic status and reason.
- When toggles are disabled, no employment-type filtering is applied.

### Phase 4: JD Validation Pipeline

- Implement `jd_validator.py` and keyword rule packs.
- Add tracker status transitions for validation outcomes.
- Block non-technical jobs from entering AI queue.

Exit criteria:

- Rows receive deterministic pass/fail with reason text.
- Non-technical listings are skipped and logged.

### Phase 5: Batch Processor (24h SLA)

- Add queue selection from `VALIDATION_PASSED` rows.
- Process by interval and batch size controls.
- Add retry and deferred requeue logic.

Exit criteria:

- Queue drains predictably within 24h target window under normal load.
- Failures are retried with capped attempts.

### Phase 6: Provider Migration + Budget Guardrails

- Implement OpenRouter and Anthropic clients.
- Add provider fallback order.
- Add hard budget stop and spend ledger.
- Ensure reservation locking works on both Windows and POSIX runtimes.
- Persist reservation metadata in tracker for auditability.

Exit criteria:

- Runtime blocks requests after cap breach.
- Spend reports are persisted daily.
- Budget ledger imports and runs on Windows and Linux without runtime lock/import failures.

### Phase 7: Two-Prompt Curation

- Add analyst and engineer prompt templates.
- Implement routing mode (`role_hint` first, optional classifier).
- Save selected track metadata in tracker.

Exit criteria:

- Each tailored output has explicit prompt track attribution.
- Prompt route is reproducible from logged metadata.

### Phase 8: DOCX Output and Review Integration

- Add `python-docx` renderer and optional template-based formatting.
- Save document path in tracker.
- Update review flow to use DOCX artifact.
- Add scheduled stale temp cleanup to enforce retention policy.

Exit criteria:

- Every successful tailored row emits a valid `.docx` file.
- Reviewer can open generated document directly from tracked path.
- Temporary failed artifacts are cleaned within configured retention window.

### Phase 9: Test Suite Alignment and Portability Hardening

- Remove or update stale tests that reference deleted APIs.
- Ensure tests target the current provider-router and DOCX renderer interfaces.
- Add platform portability checks for Windows and POSIX environments.

Exit criteria:

- Test modules align with current production APIs.
- Critical-path tests run in the project venv.
- No portability regressions in budget-ledger startup path.

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
- `job_automation/trawl.py`: collect salary from cards and/or detail pages, then write normalized columns.
- `job_automation/adapters/careersfuture.py`: add/verify salary selectors for listing cards and detail view.
- `job_automation/ai/jd_signal_extractor.py`: optionally consume normalized salary fields for ranking signals.
- `job_automation/ai/jd_validator.py`: add employment-type filter stage before AI queue entry.
- `job_automation/tests/test_provider_router.py`: keep tests aligned with ledger-based provider routing APIs.
- `job_automation/tests/test_docx_renderer.py`: keep tests aligned with current DOCX renderer APIs.

## 3.2 Salary Data Contract

Add canonical salary fields to each scraped row:

- `salary_raw`: original salary text from portal.
- `salary_min`: normalized lower bound as numeric amount.
- `salary_max`: normalized upper bound as numeric amount.
- `salary_currency`: ISO-like code (default `SGD` when explicit or strongly inferred).
- `salary_period`: one of `hour`, `day`, `month`, `year`, `unknown`.
- `salary_status`: one of `OK`, `MISSING`, `AMBIGUOUS`, `ERROR`, `SKIPPED`.

Normalization rules:

- Range text (for example, "$4,000 - $6,000") maps to min and max directly.
- Single value text maps min=max.
- Non-numeric text (for example, "competitive") maps to `AMBIGUOUS`.
- Unavailable salary maps to `MISSING`.

CareersFuture selector contract (confirmed):

- Range wrapper: `span[data-testid="salary-range"]`
- First amount element (min): first child `span.dib` under salary range block
- Second amount element (max): second child `span.dib` (contains nested `to` label + amount)

Extraction behavior for the confirmed DOM:

- Read full wrapper text into `salary_raw`.
- Parse first amount token as `salary_min` (for example, `$4,500`).
- Parse second amount token as `salary_max` after removing the `to` label (for example, `$6,500`).
- If second amount is missing, map single detected amount to `salary_min=salary_max`.

## 3.3 Employment-Type Filter Contract

Add canonical employment filter fields to each row:

- `employment_type_raw`: source text used for type detection.
- `employment_type_normalized`: one of `full_time`, `part_time`, `internship`, `contract`, `temporary`, `unknown`.
- `employment_filter_status`: one of `PASSED`, `FILTERED`, `SKIPPED`.
- `employment_filter_reason`: reason text such as `filtered_internship` or `filtered_contract`.

Filtering rules:

- If `exclude_internship` is true and normalized type is `internship`, row is filtered.
- If `exclude_contract` is true and normalized type is `contract`, row is filtered.
- If both toggles are false, employment filtering is marked `SKIPPED`.
- Unknown types pass by default unless policy is changed.
- If internship and contract both match, apply deterministic precedence and log the selected reason.

## 3.4 Config Additions

Add these top-level keys:

- `validation`
- `batch`
- `ai`
- `output`
- `salary`
- `employment_filter`

Suggested starting values:

- `batch.target_sla_hours: 24`
- `batch.interval_minutes: 30`
- `batch.batch_size: 5`
- `ai.budget.hard_stop: true`

Salary-specific suggested keys:

- `salary.capture_on_listing: true`
- `salary.capture_on_detail_fallback: true`
- `salary.default_currency: "SGD"`
- `salary.parse_locale: "en-SG"`
- `salary.enable_period_inference: true`
- `salary.selectors.careersfuture.range: 'span[data-testid="salary-range"]'`
- `salary.selectors.careersfuture.min_amount: 'span[data-testid="salary-range"] span.dib:nth-of-type(1)'`
- `salary.selectors.careersfuture.max_amount: 'span[data-testid="salary-range"] span.dib:nth-of-type(2)'`
- `salary.period_conflict_policy: "ambiguous"`
- `salary.multi_currency_policy: "ambiguous"`

Employment filter suggested keys:

- `employment_filter.enabled: true`
- `employment_filter.exclude_internship: true`
- `employment_filter.exclude_contract: true`
- `employment_filter.filter_stage: "pre_validation"`
- `employment_filter.unknown_policy: "allow"`
- `employment_filter.precedence: ["internship", "contract"]`

Validation and pipeline suggested keys:

- `validation.role_source: "row_role"`
- `ai.pipeline_mode: "role_hint"`

## 3.5 Excel Tracker Evolution

Add columns:

- `validation_score`
- `validation_reason`
- `pipeline_track`
- `ai_provider_used`
- `reservation_id`
- `reservation_expires_at`
- `cost_reserved_usd`
- `cost_actual_usd`
- `cost_usd`
- `docx_path`
- `processed_at`
- `salary_raw`
- `salary_min`
- `salary_max`
- `salary_currency`
- `salary_period`
- `salary_status`
- `employment_type_raw`
- `employment_type_normalized`
- `employment_filter_status`
- `employment_filter_reason`

Backward compatibility plan:

- On startup, detect missing columns and append them automatically.

## 4. Automation Timing Model

Recommended schedule:

1. Scraper loop runs continuously (existing behavior).
2. Batch worker wakes every `interval_minutes`.
3. Worker computes budget and throughput gates before each execution.
4. If budget exceeded, worker sets rows to deferred state and exits gracefully.

Salary handling cadence:

1. Capture listing-level salary first (lower latency).
2. If missing and descriptions are enabled, attempt detail-page fallback extraction.
3. Persist normalized fields immediately with scrape row append.

Employment filtering cadence:

1. Detect employment type after scrape and before technical validation.
2. Apply internship/contract toggles and write filter status/reason.
3. Only rows with employment filter pass proceed to validation and AI stages.

Throughput sizing formula:

$$
\mathrm{batch\ size\ per\ run} = \lceil \mathrm{queue\ depth} / \mathrm{runs\ remaining\ in\ 24h} \rceil
$$

This keeps processing slow and cost-aware while still meeting the 24h objective.

## 5. Quality and Risk Controls

1. Prompt hallucination guard: deterministic checks for additions not present in base resume.
2. Provider outage risk: fallback order and capped retries.
3. Cost overrun risk: hard stop with explicit reason logging.
4. False negatives in validator: maintain reviewed allowlist to recover edge-case technical roles.
5. DOCX formatting drift: template-anchored rendering with smoke tests.
6. Salary parse drift across portal UI updates: selector smoke checks and parser regression tests.
7. Misleading period/currency inference: mark uncertain cases as `AMBIGUOUS` rather than guessing.
8. Over-filtering target roles due to keyword collisions: keep unknown policy default to allow.
9. Portal wording drift (e.g., "contract-to-perm"): keep filter patterns configurable.
10. Cross-platform lock risk: avoid POSIX-only lock assumptions and require Windows-safe lock strategy.
11. Test drift risk: prevent stale tests from referencing deleted APIs.
12. Validator role mismatch risk: choose keyword profile from each row role/title, not one global default.
13. Reservation audit gaps: persist reservation id, expiry, reserved cost, and actual cost in tracker rows.

## 6. Test Plan

Minimum automated tests to add:

1. `jd_validator` unit tests for pass/fail thresholds and deny-pattern matches.
2. `provider_router` tests for primary/fallback/budget-stop behavior.
3. `pipeline` tests for analyst vs engineer route selection.
4. `batch_processor` tests for queue slicing and retry/defer logic.
5. `docx_renderer` tests for file creation and non-empty output.
6. Salary parser unit tests for ranges, single values, missing text, and ambiguous salary phrases.
7. Adapter extraction tests (or fixtures) that confirm selectors still capture salary text.
8. Employment-type detector tests for internship and contract phrase matching.
9. Toggle behavior tests verifying independent intern/contract switches.
10. Salary selector tests verifying min/max extraction from the exact two-element `span.dib` range DOM.
11. Windows startup/import test for budget-ledger module.
12. Test-contract checks for provider-router and DOCX renderer test modules.
13. Validator role-source tests proving per-row role controls keyword-pack selection.
14. Reservation metadata tests proving tracker captures reserve/commit lifecycle fields.

Manual checks:

1. Run end-to-end with at least 10 mixed SG listings.
2. Verify insurance-style listings are blocked before AI call.
3. Verify generated DOCX opens cleanly in Microsoft Word.
4. Verify at least one sample with explicit salary range populates `salary_min` and `salary_max` correctly.
5. Verify listings without salary are persisted as `salary_status=MISSING` without scrape failure.
6. Verify internship listings are excluded only when `exclude_internship=true`.
7. Verify contract listings are excluded only when `exclude_contract=true`.
8. Verify CareersFuture rows with salary range HTML populate min/max correctly from first and second `span.dib` elements.
9. Verify budget-ledger path starts in Windows without lock/import crash.
10. Verify DOCX temp artifacts are cleaned after retention window.

## 7. Acceptance Criteria by Line Item

1. Salary capture: listing rows include normalized salary fields when source salary is present.
2. Employment filter: internship and contract exclusions are independently toggleable and auditable.
3. JD validation: AI is never called when listing fails technical threshold.
4. Batch processing: all queued valid jobs processed within 24 hours in normal operations.
5. Provider switch: Gemini removed from active path; OpenRouter/Claude operational with hard cap.
6. Two-prompt pipeline: every output tagged as analyst or engineer stream.
7. DOCX output: every tailored row has an accessible `.docx` artifact path.
8. Platform portability: budget ledger and batch flow work on Windows and POSIX.
9. Test alignment: critical test suites target current production interfaces.

## 8. Recommended Execution Order (Practical)

1. Implement provider abstraction and config migration.
2. Implement salary capture selectors, parser, and tracker column migration.
3. Implement employment-type detector and toggleable filtering.
4. Implement validator gate and tracker status migration.
5. Implement batch processor.
6. Implement dual-prompt pipeline.
7. Implement DOCX rendering and review handoff.
8. Align and harden tests to current APIs and platform constraints.
9. Run full integration and tune keyword thresholds on real SG samples.
