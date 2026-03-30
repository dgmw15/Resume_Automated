# Architecture Design: Job Application Automation (Updated)

## 1. Goals of This Update

This architecture revision introduces five capabilities:

1. Automatic pass/fail validation for scraped job descriptions before AI tailoring.
2. Slow, controlled batch processing with a 24-hour service-level target.
3. AI provider abstraction to move away from Gemini and support OpenRouter and Claude with budget controls.
4. Two prompt layers for role-specific curation (Data Analyst and Data Engineer).
5. Downstream output generation in DOCX format.

## 2. High-Level Target Architecture

```mermaid
graph TD
  subgraph Ingestion
    ORCH[Orchestrator]
    ADAPT[Portal Adapters]
    TRACK[(Excel Tracker)]
  end

  subgraph Validation Gate
    JDV[JD Validator]
    RULES[Keyword + Pattern Rules]
    JDV --> RULES
  end

  subgraph Batch Engine
    BQ[Batch Queue]
    SCH[Batch Scheduler\n24h SLA]
    RETRY[Retry + Backoff]
  end

  subgraph AI Layer
    ROUTER[AI Provider Router]
    ORP[OpenRouter Client]
    CLAUDE[Anthropic Client]
    PIPE[Two-Prompt Pipeline\nAnalyst + Engineer]
    ROUTER --> ORP
    ROUTER --> CLAUDE
    PIPE --> ROUTER
  end

  subgraph Output
    DOCX[DOCX Renderer]
    STORE[Artifacts Folder]
    DOCX --> STORE
  end

  ORCH --> ADAPT
  ADAPT --> TRACK
  TRACK --> JDV
  JDV -->|PASS| BQ
  JDV -->|FAIL| TRACK
  SCH --> BQ
  BQ --> PIPE
  PIPE --> TRACK
  PIPE --> DOCX
  RETRY --> BQ
```

## 3. Runtime Pipeline and States

### 3.1 End-to-End Flow

1. Scrape listing and description using existing adapters.
2. Persist raw row to Excel with initial state `SCRAPED`.
3. Run JD Validator gate.
4. If failed, mark row `REJECTED_NON_TECH` and skip AI.
5. If passed, enqueue row into batch queue for role-specific prompt processing.
6. Execute two-prompt pipeline for selected role stream.
7. Save tailored text in tracker and render DOCX artifact.
8. Mark row `TAILORED_DOCX_READY` for review and later submission.

### 3.2 Tracker State Model (Extended)

Recommended status lifecycle:

- `SCRAPED`
- `VALIDATION_PENDING`
- `VALIDATION_FAILED_NON_TECH`
- `VALIDATION_PASSED`
- `BATCH_QUEUED`
- `AI_IN_PROGRESS`
- `TAILORED_TEXT_READY`
- `DOCX_READY`
- `APPROVED`
- `SUBMITTED`
- `FAILED`

## 4. Component Design Changes

### 4.1 JD Validator (New)

Add `job_automation/ai/jd_validator.py`:

- Input: `raw_description`, `role`, optional `portal_name`.
- Output: `ValidationResult(pass_fail, score, matched_keywords, fail_reasons)`.
- Logic:
  - Positive technical keyword packs per stream (Analyst, Engineer).
  - Negative/flag patterns for suspected sales/insurance bait descriptions.
  - Minimum threshold rule (for example: at least N technical hits).

Rule packs should be externalized in `config.yaml` so tuning does not require code deploy.

### 4.2 Batch Engine (New)

Add `job_automation/core/batch_processor.py`:

- Selects jobs in `VALIDATION_PASSED` state.
- Slices into configurable batch sizes.
- Processes gradually based on target throughput window (24h).
- Applies retry policy with capped retries and exponential backoff.

Scheduling policy:

- Keep orchestrator scraping loop separate from AI batch execution.
- Execute batch worker at a fixed interval and compute throughput target as:
  $$\text{jobs per hour} = \frac{\text{queued jobs}}{24}$$

### 4.3 AI Provider Router (Refactor)

Replace direct Gemini dependence with interface-driven provider clients:

- New abstract base: `job_automation/ai/providers/base.py`
- OpenRouter client: `job_automation/ai/providers/openrouter_client.py`
- Anthropic direct client: `job_automation/ai/providers/anthropic_client.py`
- Router/fallback: `job_automation/ai/provider_router.py`

Key requirements:

- Hard budget ceiling from config.
- Request-level cost estimation and cumulative spend tracking.
- Fail closed when daily or monthly cap is reached.
- Optional provider fallback order.

### 4.4 Two-Prompt Pipeline (Refactor)

Expand `job_automation/ai/prompts.py` and add `job_automation/ai/pipeline.py`:

- `ANALYST_SYSTEM_PROMPT`, `ANALYST_USER_TEMPLATE`
- `ENGINEER_SYSTEM_PROMPT`, `ENGINEER_USER_TEMPLATE`

Routing modes:

- `role_hint`: use configured role target from search role list.
- `classifier`: lightweight classification from title/JD.
- `dual_run`: run both prompts and keep better-scored result (optional, more cost).

Quality scoring can start with deterministic rules (keyword coverage, banned fabrication checks) before adding LLM-as-judge.

### 4.5 DOCX Renderer (New)

Add `job_automation/output/docx_renderer.py` using `python-docx`:

- Input: tailored plain text + metadata.
- Output: `.docx` file under `job_automation/output/docs/{job_id}.docx`.
- Optional template path for stable formatting.
- Persist generated path in tracker for apply step.

## 5. Configuration Model Changes

Extend `job_automation/config.yaml` with:

- `ai.provider`: `openrouter` or `anthropic`
- `ai.fallback_order`: ordered list
- `ai.budget`: `daily_cap_usd`, `monthly_cap_usd`, `hard_stop: true`
- `ai.pipeline_mode`: `role_hint | classifier | dual_run`
- `batch`: `enabled`, `interval_minutes`, `batch_size`, `target_sla_hours`
- `validation`: keyword dictionaries, thresholds, deny patterns
- `output`: docx template path and output directory

## 6. Data and Filesystem Impacts

### 6.1 Tracker Columns (Recommended additions)

- `validation_score`
- `validation_reason`
- `ai_provider_used`
- `pipeline_track`
- `docx_path`
- `cost_usd`
- `processed_at`

### 6.2 Artifact Layout

```text
job_automation/
├── output/
│   ├── docs/
│   │   └── <job_id>.docx
│   └── logs/
│       └── ai_costs_YYYYMMDD.csv
```

## 7. Reliability and Guardrails

1. Validator-first design prevents wasting API budget on low-quality listings.
2. Batch queue isolates transient provider failures from scraping.
3. Budget hard stop prevents unbounded spend.
4. DOCX output is deterministic and reviewable before submission.
5. Existing restart loop in `main.py` remains valid and now resumes using richer states.

## 8. Security and Compliance

- Keep API keys in environment variables or secret store only.
- Log only truncated JD excerpts in error traces to reduce sensitive exposure.
- Store cost and audit data locally for budget verification.
- Do not persist provider raw responses beyond required text output and troubleshooting metadata.
