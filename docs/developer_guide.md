# Developer Guide

This guide provides information for developers who want to contribute to the project.

## Project Structure

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

## Running Tests

To run the test suite, navigate to the `job_automation` directory and run pytest:

```bash
pytest tests/ -v
```

The test suite covers the following:
-   `test_jd_validator.py`: Keyword scoring and deny-pattern logic.
-   `test_pipeline_selector.py`: Analyst/engineer track selection.
-   `test_provider_router.py`: Fallback and budget guard behaviour.
-   `test_batch_processor.py`: SLA batch sizing and retry logic.
-   `test_skills_signal_extractor.py`: Regex skill pattern extraction.
-   `test_trawl_login_visibility.py`: Playwright browser launch check.
-   `test_docx_renderer.py`: DOCX output formatting.
-   `test_prompt_pipeline.py` / `test_skills_filter_pipeline.py`: End-to-end script tests.
