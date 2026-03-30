# Job Application Automation

An end-to-end pipeline that scrapes Singapore job portals, filters listings with deterministic rules, and uses Claude to tailor a resume per role — outputting a ready-to-send DOCX for each approved job.

---

## Table of contents

1. [How it works](#how-it-works)
2. [Architecture](#architecture)
3. [Job status lifecycle](#job-status-lifecycle)
4. [Project structure](#project-structure)
5. [Setup](#setup)
6. [What you must update before running](#what-you-must-update-before-running)
7. [User flow — step by step](#user-flow--step-by-step)
8. [Configuration reference](#configuration-reference)
9. [Running the scripts](#running-the-scripts)
10. [Tests](#tests)

---

## How it works

The system runs in three phases, continuously:

```
[1] Scrape  →  [2] Validate  →  [3] AI Batch
   Playwright       Keyword/          Claude tailors
   scrapes JDs      deny filter       resume → DOCX
```

1. **Scrape** — Playwright opens CareersFuture, Indeed (and optionally JobStreet), searches your target roles, and saves each listing's raw JD text to `Database.xlsx`.
2. **Validate** — Every scraped JD is checked against a technical keyword list and a deny-pattern list (e.g. "insurance agent"). Non-matching listings are filtered out with no AI spend.
3. **AI Batch** — Validated listings are queued and processed in controlled batches. Claude reads the raw JD and your base resume, then rewrites the resume to highlight matching skills — without hallucinating anything. The tailored text is saved to Excel and rendered as a DOCX file.

A Streamlit review UI lets you read each tailored resume and mark it APPROVED or REJECTED before sending.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  main.py  (restart loop)                                             │
│  └── Orchestrator (core/orchestrator.py)                             │
│       ├── Phase 1: Scrape                                            │
│       │    ├── adapters/careersfuture.py  ─┐                         │
│       │    ├── adapters/indeed.py          ├─ Playwright (async)     │
│       │    └── adapters/jobstreet.py      ─┘                         │
│       │         ↓ JobListing objects                                  │
│       │    core/session_manager.py   (browser contexts, re-auth)     │
│       │    core/rate_limiter.py      (per-portal delay/hourly cap)   │
│       │                                                              │
│       ├── Phase 2: Validate                                           │
│       │    └── ai/jd_validator.py   (deterministic, zero AI cost)    │
│       │                                                              │
│       └── Phase 3: Batch                                             │
│            └── core/batch_processor.py                              │
│                 ├── ai/pipeline.py        (track selector)           │
│                 ├── ai/tailor.py          (prompt builder)           │
│                 ├── ai/provider_router.py (Anthropic / OpenRouter)   │
│                 │    └── BudgetGuard      (daily + monthly caps)     │
│                 └── output/docx_renderer.py  (→ .docx file)         │
│                                                                      │
│  data/tracker.py  (ExcelTracker — Database.xlsx — shared state)     │
└──────────────────────────────────────────────────────────────────────┘

  Standalone scripts (run independently of main.py):
  ├── trawl.py               — scrape only, outputs trawl_results.xlsx
  ├── skills_filter_pipeline.py  — populate skills + continue columns
  └── prompt_pipeline.py     — build AI prompts from trawl results

  Review:
  └── web_ui/app.py          — Streamlit UI (APPROVED / REJECTED)
```

### Key design decisions

| Decision | Reason |
|---|---|
| Excel as the database | Zero infrastructure — readable and editable by hand at any time |
| Deterministic validation before AI | Eliminates irrelevant listings with no API cost |
| Two prompt tracks (analyst / engineer) | Different JDs call for different emphasis; keyword match is instant and accurate enough |
| Budget guard in-process | Hard stops before daily/monthly caps are hit; restarts the process cleanly |
| Playwright browser contexts per portal | Allows cookie/session reuse across scrape calls without re-logging in |
| Crash-restart loop in main.py | If something breaks mid-run the process restarts and picks up from the Excel state |

### AI pipeline tracks

The system detects whether a role is **analyst** or **engineer** from the job title (no AI call needed):

- **Analyst** — SQL, BI tools (Tableau/Power BI/Looker), dashboards, A/B testing, KPIs, stakeholder communication
- **Engineer** — ETL/ELT, Airflow/dbt/Spark, cloud data warehouses (BigQuery/Redshift/Snowflake), streaming (Kafka), IaC

Each track has a dedicated system prompt (`ai/prompts.py`) with focus areas and strict anti-hallucination rules. Claude is instructed never to invent experience — it only reorders and re-emphasises what is already in your base resume.

### AI providers

`ai/provider_router.py` tries providers in the configured `fallback_order`:

- **Anthropic** (primary) — reads `ANTHROPIC_API_KEY` from `.env`
- **OpenRouter** (fallback) — reads `OPENROUTER_API_KEY` from `.env`

The `BudgetGuard` tracks in-process spend and raises `BudgetExceededError` when a cap is hit, stopping the batch cycle cleanly.

---

## Job status lifecycle

Every row in `Database.xlsx` moves through these statuses:

```
NEW
 └─→ SCRAPED           (JD text fetched)
      └─→ MISSING           (JD fetch failed — skipped)
      └─→ VALIDATION_PENDING
           ├─→ VALIDATION_FAILED_NON_TECH   (filtered out, no AI spend)
           └─→ VALIDATION_PASSED
                └─→ BATCH_QUEUED
                     └─→ AI_IN_PROGRESS
                          ├─→ TAILORED_TEXT_READY
                          │    └─→ DOCX_READY      (← DOCX file written)
                          │         └─→ APPROVED    (set via Streamlit UI)
                          │              └─→ SUBMITTED
                          └─→ FAILED               (max retries exceeded)
```

You interact with the `DOCX_READY` rows in the Streamlit UI, setting them to `APPROVED` or `REJECTED`.

---

## Project structure

```
job_automation/
├── main.py                      # Crash-restart entry point
├── trawl.py                     # Standalone scraper (→ trawl_results.xlsx)
├── prompt_pipeline.py           # Batch AI enrichment from trawl results
├── skills_filter_pipeline.py    # Populate skills/continue columns
├── config.yaml                  # All runtime settings (edit this)
├── requirements.txt
├── run.bat                      # Windows: activate venv + run main.py
├── trawl.bat                    # Windows: activate venv + run trawl.py
│
├── adapters/                    # One file per job portal
│   ├── base_adapter.py          # ABC: login(), scrape_page(), get_job_description()
│   ├── careersfuture.py
│   ├── indeed.py
│   └── jobstreet.py
│
├── ai/
│   ├── pipeline.py              # select_track() — "analyst" or "engineer"
│   ├── prompts.py               # System prompts + user templates (edit focus areas here)
│   ├── jd_validator.py          # Deterministic keyword/deny-pattern filter
│   ├── jd_signal_extractor.py   # Extracts structured signals from a JD
│   ├── skills_signal_extractor.py
│   ├── provider_router.py       # BudgetGuard + provider fallback
│   ├── tailor.py                # Builds the final prompt, calls router.generate()
│   └── providers/
│       ├── base.py              # BaseProvider, ProviderResult, BudgetExceededError
│       ├── anthropic_client.py  # Anthropic SDK integration
│       └── openrouter_client.py # OpenRouter REST integration
│
├── core/
│   ├── orchestrator.py          # Three-phase run loop
│   ├── batch_processor.py       # SLA-aware batch worker
│   ├── session_manager.py       # Playwright browser context lifecycle
│   ├── rate_limiter.py          # Per-portal delay + hourly action cap
│   └── login_utils.py           # Shared browser helpers
│
├── data/
│   ├── models.py                # JobListing (Pydantic) + JobStatus (Enum)
│   └── tracker.py               # ExcelTracker — read/write Database.xlsx
│
├── web_ui/
│   └── app.py                   # Streamlit review UI
│
├── input/
│   └── skills_input.xlsx        # Skill patterns (auto-created, then editable)
│
├── output/
│   └── docs/                    # Generated DOCX files (gitignored)
│
└── tests/                       # pytest suite
```

---

## Setup

**Requirements:** Python 3.11+, Windows (`.bat` scripts) or any OS with bash.

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd Resume

# 2. Create a virtual environment inside job_automation/
cd job_automation
python -m venv .venv

# 3. Activate it
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac / Linux

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install the Playwright browser (one-time)
.venv\Scripts\playwright.exe install chromium
# playwright install chromium   # Mac / Linux

# 6. Create your .env file (in the repo root)
# See "What you must update" below.
```

---

## What you must update before running

These are the things that are personal to you and not included in the repo.

### 1. `.env` — API keys

Create this file at the repo root (`Resume/.env`):

```
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...   # optional, only needed as fallback
```

### 2. `job_automation/base_resume.txt` — your resume

Create this file inside `job_automation/`. Paste your full resume as **plain text**. This is the file Claude reads and rewrites for each job. It is gitignored.

```
Jane Doe
jane@example.com | linkedin.com/in/janedoe

EXPERIENCE
...
```

### 3. `job_automation/job_roles.xlsx` — your target roles

Open this file and edit the **Roles** sheet, **Job Role** column. Add every role title you want to search for, one per row. Examples:

| Job Role |
|---|
| Data Analyst |
| Business Intelligence Analyst |
| Data Engineer |
| Analytics Engineer |

### 4. `job_automation/config.yaml` — tune the settings

Key settings to review:

| Setting | What to change |
|---|---|
| `portals.careersfuture.enabled` | Set `false` to skip a portal |
| `portals.*.max_actions_per_hour` | Lower if you're getting blocked |
| `ai.budget.daily_cap_usd` | Your spend ceiling per day |
| `ai.budget.monthly_cap_usd` | Your spend ceiling per month |
| `validation.min_keyword_hits` | Raise to be stricter; lower to pass more JDs |
| `validation.deny_patterns` | Add phrases that identify irrelevant postings |
| `batch.batch_size` | How many JDs to process per 30-minute cycle |

### 5. `job_automation/input/skills_input.xlsx` (optional)

Run `python skills_filter_pipeline.py` once to auto-generate this file, then edit the **Skills** sheet to enable/disable skill patterns used by the standalone filter pipeline.

---

## User flow — step by step

### Option A — fully automated (recommended after first run)

```
1.  Edit job_roles.xlsx with your target roles.
2.  Edit base_resume.txt with your current resume.
3.  Set ANTHROPIC_API_KEY in .env.
4.  cd job_automation
5.  python main.py          (or double-click run.bat on Windows)
6.  Leave it running. Every 5 minutes it scrapes → validates → batches.
7.  Open the Streamlit UI to review DOCX_READY rows.
8.  Approve what looks good, download the DOCX, apply manually.
```

### Option B — manual / staged (good for first-time use or debugging)

```
Step 1 — Scrape only
    python trawl.py
    → produces trawl_results.xlsx

Step 2 — Skills filter (optional, no AI cost)
    python skills_filter_pipeline.py
    → adds "skills" and "continue" columns
    → open trawl_results.xlsx, set "continue" = 0 for rows you want to skip

Step 3 — AI enrichment
    python prompt_pipeline.py
    → reads trawl_results.xlsx rows where continue = 1
    → calls Claude, writes prompts/responses to output/

Step 4 — Review
    streamlit run web_ui/app.py
    → approve the ones you like
```

### Streamlit review UI

```bash
cd job_automation
streamlit run web_ui/app.py
```

The UI shows each `DOCX_READY` row with the tailored resume text and the original JD. Use it to:
- Read the tailored resume
- Download the DOCX
- Set status to `APPROVED` or `REJECTED`

---

## Configuration reference

### `portals`

```yaml
portals:
  careersfuture:
    enabled: true
    max_actions_per_hour: 30   # browser clicks + page loads counted together
    min_delay_seconds: 5       # minimum wait between actions
    max_delay_seconds: 15      # maximum wait (randomised within range)
```

### `validation`

```yaml
validation:
  min_keyword_hits: 3          # JD must contain at least this many tech keywords
  role_keyword_sets:
    analyst: [sql, python, tableau, ...]   # add/remove freely
    engineer: [etl, dbt, airflow, ...]
  deny_patterns:
    - "insurance agent"        # any JD containing these strings is rejected
    - "commission only"
```

### `ai`

```yaml
ai:
  provider: "anthropic"        # primary provider
  fallback_order:
    - "anthropic"
    - "openrouter"
  model_map:
    analyst: "claude-sonnet-4-6"
    engineer: "claude-sonnet-4-6"
  budget:
    daily_cap_usd: 5.00
    monthly_cap_usd: 50.00
    hard_stop: true            # raises BudgetExceededError when cap hit
```

### `batch`

```yaml
batch:
  enabled: true
  interval_minutes: 30         # how often the batch worker runs
  batch_size: 5                # max JDs processed per cycle
  target_sla_hours: 24         # target turnaround time for queued jobs
  max_retries: 3               # AI call retries before marking FAILED
```

---

## Running the scripts

All commands assume you are inside `job_automation/` with the venv active.

| Script | Command | Purpose |
|---|---|---|
| Full system | `python main.py` | Runs all three phases in a loop, auto-restarts on crash |
| Scrape only | `python trawl.py` | Saves listings to `trawl_results.xlsx` |
| Skills filter | `python skills_filter_pipeline.py` | Adds skills/continue columns to trawl results |
| AI pipeline | `python prompt_pipeline.py` | Runs Claude on rows where `continue = 1` |
| Review UI | `streamlit run web_ui/app.py` | Opens the Streamlit review interface |
| Tests | `pytest tests/` | Runs the full test suite |

**Windows shortcuts:**

```
run.bat      →  activates venv + runs main.py
trawl.bat    →  activates venv + runs trawl.py
```

---

## Tests

```bash
cd job_automation
pytest tests/ -v
```

Test coverage includes:
- `test_jd_validator.py` — keyword scoring and deny-pattern logic
- `test_pipeline_selector.py` — analyst/engineer track selection
- `test_provider_router.py` — fallback and budget guard behaviour
- `test_batch_processor.py` — SLA batch sizing and retry logic
- `test_skills_signal_extractor.py` — regex skill pattern extraction
- `test_trawl_login_visibility.py` — Playwright browser launch check
- `test_docx_renderer.py` — DOCX output formatting
- `test_prompt_pipeline.py` / `test_skills_filter_pipeline.py` — end-to-end script tests
