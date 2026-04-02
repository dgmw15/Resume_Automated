# User Guide

This guide will walk you through setting up and running the job application automation project.

## Setup

**Requirements:** Python 3.11+, Windows (`.bat` scripts) or any OS with bash.

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd Resume
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    cd job_automation
    python -m venv .venv
    # On Windows
    .venv\Scripts\activate
    # On macOS/Linux
    # source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Playwright browser:**
    ```bash
    # On Windows
    .venv\Scripts\playwright.exe install chromium
    # On macOS/Linux
    # playwright install chromium
    ```

5.  **Create `.env` file:**
    Create a `.env` file in the root of the repository (`Resume/.env`) with your API keys:
    ```
    ANTHROPIC_API_KEY=sk-ant-...
    OPENROUTER_API_KEY=sk-or-...   # optional, only needed as fallback
    ```

6.  **Create `base_resume.txt`:**
    Create a file named `base_resume.txt` inside the `job_automation` directory. Paste your full resume as plain text.

7.  **Configure `job_roles.xlsx`:**
    Open `job_automation/job_roles.xlsx` and add the job titles you want to search for in the "Roles" sheet.

8.  **Configure `config.yaml`:**
    Review and edit `job_automation/config.yaml` to tune the settings for your needs.

## Running the Application

### Fully Automated Mode

This is the recommended way to run the application after the initial setup.

1.  Navigate to the `job_automation` directory.
2.  Run the main script:
    ```bash
    python main.py
    ```
    On Windows, you can also double-click `run.bat`.

The application will run continuously, scraping, validating, and tailoring resumes.

### Manual/Staged Mode

This mode is useful for first-time use or debugging.

1.  **Scrape only:**
    ```bash
    python trawl.py
    ```
    This will create `trawl_results.xlsx`.

2.  **AI enrichment:**
    ```bash
    python prompt_pipeline.py
    ```
    This will process the scraped jobs and generate tailored resumes.

### Reviewing Results

Use the Streamlit UI to review the generated resumes.

1.  Navigate to the `job_automation` directory.
2.  Run the Streamlit app:
    ```bash
    streamlit run web_ui/app.py
    ```

The UI will display the tailored resume and the original job description. You can approve or reject the tailored resume and download the DOCX file.
