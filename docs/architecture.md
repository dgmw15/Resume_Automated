# Architecture

The application is designed with a modular architecture, separating concerns into different components.

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

## Key Design Decisions

| Decision | Reason |
|---|---|
| Excel as the database | Zero infrastructure — readable and editable by hand at any time |
| Deterministic validation before AI | Eliminates irrelevant listings with no API cost |
| Two prompt tracks (analyst / engineer) | Different JDs call for different emphasis; keyword match is instant and accurate enough |
| Budget guard in-process | Hard stops before daily/monthly caps are hit; restarts the process cleanly |
| Playwright browser contexts per portal | Allows cookie/session reuse across scrape calls without re-logging in |
| Crash-restart loop in main.py | If something breaks mid-run the process restarts and picks up from the Excel state |

## AI Pipeline

The AI pipeline is responsible for tailoring the resume. It uses different "tracks" based on the type of role to ensure the generated resume highlights the most relevant skills. For example, it can distinguish between roles that are more analytical and those that are more technical.

For example:
*   **Analysis-focused roles**: These are roles that involve data analysis, business intelligence, and reporting. Examples include Data Analyst, Business Intelligence Analyst, and roles requiring skills in SQL, Tableau, Power BI, or Looker.
*   **Engineering-focused roles**: These are roles that involve building and maintaining data systems. Examples include Data Engineer, Analytics Engineer, and roles requiring skills in ETL/ELT, Airflow, dbt, Spark, and cloud data warehouses like BigQuery, Redshift, or Snowflake.

Each track has a dedicated system prompt with focus areas and strict anti-hallucination rules.

### AI Providers

The system uses a primary AI provider (Anthropic) and a fallback provider (OpenRouter). A `BudgetGuard` is in place to prevent budget overruns.
