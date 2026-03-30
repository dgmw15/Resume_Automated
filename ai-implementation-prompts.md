# AI Implementation Prompt Pack (Updated)

Use these prompts in order. Each block is designed for copy-paste into your AI coding assistant.

Goal of this pack:

1. Add JD technical pass/fail validation.
2. Add 24-hour batch processing.
3. Replace Gemini path with OpenRouter and/or Claude with hard budget stop.
4. Add dual prompt tracks (Data Analyst + Data Engineer).
5. Generate DOCX outputs for downstream review and submission.

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
6. Under output, include:
   - docx_output_dir
   - docx_template_path (optional)

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
   - DOCX_READY
2. Add columns if missing:
   - validation_score
   - validation_reason
   - pipeline_track
   - ai_provider_used
   - cost_usd
   - docx_path
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
4. Update tailor path to use ProviderRouter.
5. Keep retries with backoff for transient network/API failures.

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
4. On success:
   - save tailored text
   - set TAILORED_TEXT_READY
5. On permanent failure:
   - set FAILED with reason

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
5. Set status DOCX_READY after successful write.
6. Add one integration test that verifies generated file exists and is readable.

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
   SCRAPED -> VALIDATION_PENDING -> VALIDATION_PASSED/FAILED -> BATCH_QUEUED -> AI_IN_PROGRESS -> TAILORED_TEXT_READY -> DOCX_READY
2. Ensure non-technical postings never call AI provider.
3. Ensure budget hard stop prevents additional AI calls.
4. Ensure errors are logged with actionable messages.
5. Provide concise run instructions.

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
11. Prompt 10 (optional)