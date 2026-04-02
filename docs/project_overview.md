# Project Overview

This project is a job application automation pipeline that scrapes job portals, filters listings, and uses AI to tailor a resume for each role.

## How it works

The system operates in three phases:

1.  **Scrape**: Playwright is used to scrape job listings from various portals.
2.  **Validate**: The scraped job descriptions are validated against a set of keywords and deny patterns.
3.  **AI Batch**: Validated listings are processed in batches by an AI (Claude) to tailor a resume for each job.

The tailored resumes are then rendered as DOCX files, which can be reviewed and approved through a Streamlit UI.
