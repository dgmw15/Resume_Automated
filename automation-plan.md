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
8. Initial data completeness checker with optional deterministic backfill for missing fields.
9. Migration of dataframe operations from pandas to Polars for improved speed and memory usage.
10. ATS-style resume tailoring agent flow that extracts JD keywords, selects 3-4 relevant tasks, and rewrites resume content with those keywords.

## 2. Delivery Strategy

Use incremental phases so scraping remains stable while AI and output logic evolve.

### Phase 1: Foundation Refactor

- Create AI provider abstraction layer and router.
- Add config schema for providers, budget caps, batch settings, validator rules, and output paths.
- Keep existing flow working with feature flags disabled by default.

Exit criteria:

- Existing scrape loop still runs.
- New config loads without runtime errors.

### Phase 1.5: Pandas-to-Polars Preparation

- Inventory all pandas usage points and classify each by operation type and risk.
- Introduce a small dataframe engine abstraction for role-loading and table transformations.
- Add a config flag (`dataframe.engine`) to support controlled A/B rollout (`pandas` then `polars`).
- Keep workbook schema and tracker output unchanged during migration.

Exit criteria:

- Every pandas usage site has a mapped Polars replacement path.
- Engine abstraction supports current behavior with `pandas` mode enabled.
- Rollback path is one-step by config flip.

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

### Phase 8.5: Resume Tailoring Agents (ATS-Style)

- Add a lightweight ATS keyword extractor to pull role-specific terms from JD text.
- Add deterministic task selection that picks 3-4 most relevant tasks based on keyword coverage and role alignment.
- Add a resume rewriter that produces keyword-rich bullets while preserving truthfulness and original task meaning.
- Persist keywords, selected tasks, and rewrite rationale in tracker for auditability.
- Add DOCX output option for tailored resume draft as a separate artifact.

Exit criteria:

- Each tailored resume draft includes traceable keywords and the 3-4 selected tasks.
- Output is deterministic given the same JD + task list input.
- Drafts are stored with a stable path in the tracker.

### Phase 9: Test Suite Alignment and Portability Hardening

- Remove or update stale tests that reference deleted APIs.
- Ensure tests target the current provider-router and DOCX renderer interfaces.
- Add platform portability checks for Windows and POSIX environments.

Exit criteria:

- Test modules align with current production APIs.
- Critical-path tests run in the project venv.
- No portability regressions in budget-ledger startup path.

### Phase 9.5: Polars Cutover and Dependency Cleanup

- Run parity tests on representative role/input workbooks in both engines.
- Capture runtime and memory metrics for role-loading and pre-processing flow.
- Promote `polars` to default only after parity and stability checks pass.
- Remove direct pandas dependency from active runtime path after cutover confidence.

Exit criteria:

- Output parity checks pass for status-critical columns and role lists.
- Memory use improves or remains neutral for baseline workloads.
- Polars is default and pandas is optional or removed per final policy.

### Phase 10: Data Completeness Check + Backfill

- Add a deterministic checker that audits missing/inconsistent fields before downstream processing.
- Support `audit_only` mode (report only) and `recover` mode (write back recoverable data).
- Use local parsing backfill first, then optional portal refetch for unresolved salary gaps.

Exit criteria:

- Checker reports field-level and row-level completeness clearly.
- Recover mode fills deterministic missing data without changing already-valid rows.
- Unresolved rows are tagged with explicit reason codes.

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
- `job_automation/core/data_checker.py`: workbook-level completeness audit and optional backfill orchestration.
- `job_automation/tests/test_data_checker.py`: deterministic completeness and recovery behavior tests.
- `job_automation/core/dataframe_engine.py` (new): unified dataframe read/select helpers for pandas and Polars modes.
- `job_automation/core/orchestrator.py`: migrate role-loading path to dataframe engine abstraction.
- `job_automation/trawl.py`: migrate role-loading path to dataframe engine abstraction.
- `job_automation/tests/test_dataframe_engine.py` (new): parity and fallback tests for pandas vs Polars modes.
- `job_automation/ai/ats_keyword_extractor.py`: extract JD keywords and phrases for ATS matching.
- `job_automation/ai/task_selector.py`: select 3-4 most relevant tasks from a provided task list.
- `job_automation/ai/resume_rewriter.py`: rewrite bullets using selected tasks and keywords.
- `job_automation/output/docx_renderer.py`: add optional resume draft template output (reuse docx renderer).
- `job_automation/tests/test_resume_tailoring.py`: regression tests for keyword extraction, task selection, and rewrite stability.

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
- `resume_tailoring`

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

Data checker suggested keys:

- `data_checker.enabled: true`
- `data_checker.run_stage: "pre_pipeline"`
- `data_checker.mode: "audit_only"`  # `audit_only` or `recover`
- `data_checker.targets: ["trawl_results.xlsx", "trawl_results_enriched.xlsx"]`
- `data_checker.backfill.allow_portal_refetch: true`
- `data_checker.backfill.max_rows_per_run: 100`
- `data_checker.write_backup: true`
- `data_checker.report_path: "output/logs/data_completeness_YYYYMMDD.json"`

Resume tailoring suggested keys:

- `resume_tailoring.enabled: true`
- `resume_tailoring.max_tasks: 4`
- `resume_tailoring.min_tasks: 3`
- `resume_tailoring.keyword_min_count: 8`
- `resume_tailoring.output_dir: "output/docs/resume"`
- `resume_tailoring.template_path: "output/templates/resume_template.docx"`
- `resume_tailoring.rewrite_style: "impact-first"`

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
- `resume_keywords`
- `resume_selected_tasks`
- `resume_draft_path`
- `resume_rewrite_notes`

Backward compatibility plan:

- On startup, detect missing columns and append them automatically.

## 3.6 Data Completeness Checker Contract

Checker target fields for trawl workbooks:

- `salary_raw`
- `salary_min`
- `salary_max`
- `salary_currency`
- `salary_period`
- `salary_status`

Row classification states:

- `COMPLETE`: required fields present and internally consistent.
- `MISSING`: one or more required fields are empty.
- `INCONSISTENT`: fields conflict (for example, `salary_min > salary_max`).
- `RECOVERED_LOCAL`: filled by deterministic parser from existing raw text.
- `RECOVERED_REFETCH`: filled by re-fetching source page selectors.
- `UNRESOLVED`: could not recover; explicit reason attached.

Recovery order:

1. Recompute from local `salary_raw` using parser.
2. If still unresolved and allowed, refetch salary from source URL.
3. Persist result with recovery status and reason.

## 3.7 Pandas-to-Polars Migration Contract

Current in-scope dataframe surface:

- Role Excel loading in `trawl.py`.
- Role Excel loading in `core/orchestrator.py`.

Migration rules:

- Preserve role-list output semantics (values, trimming, order).
- Preserve compatibility with existing Excel role workbook structure.
- Keep failure behavior deterministic (clear fallback logs, no silent schema drift).

Execution sequence:

1. Build dataframe engine wrapper with two implementations: pandas and Polars.
2. Route existing role-loading call sites through wrapper (no logic change first).
3. Add parity tests for role extraction from identical fixtures.
4. Add lightweight performance harness to compare speed and memory per engine.
5. Flip default engine to Polars after parity + baseline checks pass.

Acceptance gates:

- Zero functional diff in role values loaded from fixture workbooks.
- No regression in scrape/orchestrator startup behavior.
- Measured memory reduction for medium and large role files.

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
14. Silent data quality drift risk: enforce pre-pipeline completeness checks and explicit unresolved tagging.
15. Dataframe API mismatch risk: isolate pandas vs Polars differences behind wrapper functions.
16. Excel reader capability risk: validate selected Polars Excel path against current workbook formats.
17. Migration rollback risk: keep config-level fallback to pandas until two consecutive stable runs.

### Current Failure Analysis (2026-04-25)

Observed failure state:

- `pytest -q job_automation/tests/test_docx_renderer.py` fails with spacing/content-preservation assertions.
- Full suite collection for provider/batch tests fails on Windows import path before test execution.

Verified root causes:

1. DOCX sanitizer removes regular spaces:
	- File: `job_automation/output/docx_renderer.py`
	- Current regex in `_sanitise_content()` uses `[ ^\\S\\n\\t ]` pattern branch (without spaces in actual code), which matches regular spaces and strips them.
	- Effect: output text collapses words (`"Jane Doe" -> "JaneDoe"`), causing renderer formatting/content tests to fail.

2. Budget ledger is POSIX-locked at import time:
	- File: `job_automation/core/budget_ledger.py`
	- `import fcntl` occurs at module import-time; Windows has no `fcntl`.
	- Effect: `ModuleNotFoundError` during test collection for provider/batch modules, so critical tests never run on Windows.

3. Idempotency replay payload behavior is incomplete against critical prompt contract:
	- File: `job_automation/ai/provider_router.py`
	- Replay returns placeholder text (`[DEDUPLICATED — see original committed result]`) instead of previously committed logical payload.
	- Effect: does not satisfy the stronger replay requirement in critical prompts 11/13.

Remediation plan (no-code planning)

Phase A: Stabilize failing critical paths first

1. Fix sanitizer contract to preserve normal spaces while still removing control chars.
2. Add/adjust regression tests to explicitly protect whitespace preservation in DOCX output.
3. Re-run `test_docx_renderer.py` and require full pass before moving on.

Phase B: Restore Windows portability for budget/provider path

1. Replace import-time POSIX lock dependency with runtime platform-aware lock strategy.
2. Keep equivalent lock semantics for POSIX and a Windows-safe path.
3. Re-run collection + provider/batch/budget tests on Windows; block release if import-time failures remain.

Phase C: Complete replay/idempotency contract

1. Define persisted replay artifact contract (what exact payload fields must be returned on replay).
2. Update router/ledger interaction model to return prior committed logical result payload, not placeholder text.
3. Add replay integrity tests proving: no re-charge, no duplicate output, and exact replay payload return.

Phase D: Gate-based verification and status update

1. Run targeted suites in order: docx, budget ledger, provider router, batch processor.
2. Run full project suite on Windows after targeted pass.
3. Update prompt completion status only after objective green evidence.

Acceptance gates for closure

- DOCX gate: all tests in `job_automation/tests/test_docx_renderer.py` pass, including spacing/content assertions.
- Portability gate: no `ModuleNotFoundError` for budget/provider modules on Windows import and test collection.
- Idempotency gate: replay returns previously committed payload and does not consume additional budget.
- Integration gate: provider/batch/docx critical suites pass together in one Windows run.

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
15. Data-checker tests for missing, inconsistent, recovered, and unresolved row classifications.
16. Idempotency tests proving repeated checker runs do not mutate already-correct rows.
17. Dataframe parity tests proving pandas and Polars return identical role lists on shared fixtures.
18. Startup fallback tests proving pandas engine is used when Polars read path fails.
19. Performance smoke test capturing relative runtime and memory for role loading.
20. Resume tailoring tests for keyword extraction stability and task selection determinism.
21. Resume rewrite tests verifying keyword inclusion without meaning drift.

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
11. Verify checker audit report is produced before downstream processing.
12. Verify recover mode updates only recoverable rows and leaves complete rows untouched.

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
10. Data quality gate: missing/inconsistent data is detected before pipeline stages and recoverable gaps are backfilled deterministically.
11. Dataframe migration: Polars path is functionally equivalent on baseline inputs and improves resource profile.
12. Resume tailoring: ATS keywords are extracted, 3-4 tasks are selected, and a draft resume artifact is produced deterministically.

## 8. Recommended Execution Order (Practical)

1. Implement provider abstraction and config migration.
2. Implement salary capture selectors, parser, and tracker column migration.
3. Implement employment-type detector and toggleable filtering.
4. Implement validator gate and tracker status migration.
5. Implement batch processor.
6. Implement dual-prompt pipeline.
7. Implement DOCX rendering and review handoff.
8. Align and harden tests to current APIs and platform constraints.
9. Implement and validate data completeness checker (audit mode, then recover mode).
10. Implement dataframe engine abstraction and pandas/Polars parity tests.
11. Run Polars canary with rollback guard (`dataframe.engine`), then promote default.
12. Run full integration and tune keyword thresholds on real SG samples.
