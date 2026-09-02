# Plan: Tailored, ATS-Ready Resumes — Built and Applied to Every Job

**For:** Daryl Goh
**Scope:** A from-scratch plan for turning `job_automation/` into a system that (1) tailors a genuinely keyword-rich, ATS-passable resume per job, (2) builds it as a clean DOCX, and (3) gets it in front of an employer — reusing what already works in the repo and replacing what doesn't.

---

## TL;DR diagnosis

I read through the repo (`README.md`, `architecture-design.md`, the scraper adapters, the AI tailoring code, the DOCX renderer, and your live data). Two things are true at once:

1. **The pipeline scaffolding is genuinely solid.** Scraping, a deterministic pre-AI JD filter, a budget-capped AI provider router, an ATS-safe DOCX renderer, and a Streamlit approval step all exist and are reasonably well-built.
2. **The one file that actually matters for your problem doesn't exist yet.** `job_automation/base_resume.txt` — the master resume text Claude reads before tailoring anything — has never been created. `core/batch_processor.py` checks for it and silently skips the batch cycle if it's missing (line 77-79). So even if you turned the whole system on today, no resume would get tailored.

That's the real root cause of "not enough keywords." It's not a prompt problem or a rendering problem — Claude is explicitly forbidden from inventing skills (correctly — that's what keeps you from getting flagged for lying), so it can only surface what's *in* the base resume. Your current DOCX (`Resume_DarylGoh (1).docx`) is thin on tool-specific keywords, and there's no richer source document behind it for the AI to draw from. Fix the source document, and the rest of the pipeline has a real chance of working.

I'm treating this as a fresh design (per your steer) rather than a strict continuation of `architecture-design.md` — but a lot of what's there is worth keeping. I'll flag reuse vs. rebuild explicitly in each phase.

---

## What I found when I audited your data

- **160 jobs already scraped**, all from CareersFuture only (Indeed is enabled in `config.yaml` but has never actually been run; JobStreet is disabled).
- Target roles (`job_roles.xlsx`): **Data Engineer** and **Data Analyst** only.
- Breakdown of what's been scraped: 22× Data Engineer, 11× Data Analyst, 7× Senior Data Engineer, plus postings explicitly requiring **Azure**, **Databricks** — neither of which appears anywhere in your current resume or skills list.
- The deterministic keyword gate (`ai/jd_validator.py`) requires **3+ technical keyword hits** from lists that include `airflow`, `dbt`, `spark`, `kafka`, `databricks`, `snowflake`, `bigquery`, `redshift`, `aws`, `gcp`, `azure`, `docker`, `kubernetes` — i.e. exactly the keywords your resume is missing. A meaningful slice of your own scraped listings would fail this gate today purely on vocabulary, independent of whether you actually have the underlying skill.
- `skills_filter_pipeline.py` has never been run (the `skills` / `continue` columns in `trawl_results.xlsx` are empty) — so even the lightweight standalone filter path hasn't been exercised yet.
- Your resume shows real technical breadth that just isn't spelled out: Python-based ETL pipeline, AI-integrated QC (97% accuracy), IBM SPSS Modeler, Power BI, Excel VBA/Macros, database design for 1,000 users, a SvelteKit web app, an AI-assisted data ingestion tool. None of these currently carry the specific sub-tool/library keywords an ATS or a hiring filter scans for.
- Two things worth double-checking before any of this becomes your master resume: your **'Sup (Lead Software Engineer)** role (Nov 2024 – Apr 2025) and **SpareParts 3D** role (Jan 2025 – Present) overlap by ~3 months, and your **NTU Bachelor of Technology in Computing** is dated Aug 2025 – Aug 2029 (i.e. in progress, finishing in 3 years, concurrent with full-time work). Neither is disqualifying, but a recruiter or an ATS date-parser may flag the overlap, so it's worth having a one-line explanation ready (e.g. transition/notice period, or part-time NTU) — I'll bake that into the master resume as a note to resolve with you rather than guess.

---

## Guiding principles for the whole plan

- **No fabrication, ever.** Every keyword that ends up in a tailored resume must trace back to something you actually did. This is a hard constraint on your career, not just a nice-to-have — ATS keyword stuffing without substance gets caught in the interview, not before it.
- **The fix is information, not prompting.** The AI can't surface a keyword you never told it about. So the highest-leverage work here is building a complete, honest inventory of your real technical experience — not tweaking prompts.
- **ATS-safe formatting is a solved problem in this repo — keep it.** `output/docx_renderer.py` already avoids the things that break ATS parsers: no tables, no text boxes, no headers/footers, no multi-column layout, no icons/graphics, real text (not images) throughout, and standard section names (WORK EXPERIENCE, EDUCATION, SKILLS). Don't touch this unless you're extending it.
- **Human-in-the-loop before anything gets sent.** Scraping and tailoring can be fully automated. Actual submission to an employer should not be — more on why in Phase 5.
- **Cost control is already handled — and there's a second option.** `ai/provider_router.py` has a hard daily ($5) and monthly ($50) budget cap against the pay-per-token Anthropic API. If you'd rather run this against your existing Claude subscription instead of a metered API key, that's a real, documented alternative — see **Phase 2B** below.

---

## Phase 0 — Build your real skills & experience inventory (the actual blocker)

This is the phase that unblocks everything else, and it's the one no automation can do for you — it has to come from you, because the whole point is not to invent anything.

For each role (SpareParts 3D, 'Sup, Singapore Maritime Crisis Centre, Advario Asia Pacific) and each project (Maritime Route Analysis, Capstone, MakanOS, Data Analyst Tool), I need honest answers to:

1. **Languages & libraries** — not just "Python," but which libraries (pandas, NumPy, requests, FastAPI, etc.)? Which parts of SQL (window functions, CTEs, query optimization)?
2. **Cloud & infra** — have you touched AWS/GCP/Azure at all, even lightly (e.g. S3 for storage, a VM, a managed DB)? Docker? Git/GitHub (you clearly use GitHub — is that reflected anywhere in your skills list? It isn't currently).
3. **Data tooling** — anything adjacent to Airflow/dbt/Spark/Kafka, even informally (e.g. did the "automated Python-based ETL pipeline" use any scheduler, any orchestration, any specific ingestion pattern)? If genuinely no, that's fine — we just won't claim it, and instead we lean harder into what you do have (SPSS Modeler, Power BI, VBA automation, AI-integrated pipelines) for roles that value that profile.
4. **The AI/agent-building work** — MakanOS and the Data Analyst Tool both mention "AI-assisted development" and "external AI APIs." Which APIs (OpenAI, Anthropic, others)? This is increasingly a hot keyword category (LLM integration, prompt engineering, agentic workflows) and is currently underselling itself as a one-line mention.
5. **Scale/impact numbers** — you have some great ones already (97% accuracy, 30x turnaround, 50% productivity gain, 1,000-user scalability). Any more of these hiding in the other roles?
6. **Certifications, courses, or self-study** — anything not on the resume at all (e.g. an online cloud cert, a SQL course)?

**Deliverable of this phase:** a raw, unpolished, complete text dump of everything real — doesn't need to be well-written, just complete. I'll turn it into structured content in Phase 1.

---

## Phase 1 — Construct the master resume (`base_resume.txt`)

This is a **superset document**, not what gets sent to any employer. It's the keyword-complete source of truth the AI tailors *down* from for each job. Practically:

- Every bullet from your current resume, rewritten to include the specific tool/method underneath the generic verb (e.g. "automated Python-based ETL pipeline" → name the libraries, the trigger mechanism, the data volume, if you have those details).
- A comprehensive **Skills** section organized by category (Languages, Data/BI Tools, Cloud & Infra, AI/LLM, Soft Skills) that only lists things confirmed in Phase 0.
- All the project work, expanded with the same keyword depth.
- Kept in the exact structural format `ai/prompts.py` already specifies for the renderer (name → contact → SUMMARY → WORK EXPERIENCE with `Company | Title | Mon YYYY – Mon YYYY` role lines → bullets → EDUCATION → SKILLS → PROJECTS) — this format is the contract `output/docx_renderer.py` parses against, so keeping it is what makes the existing renderer "just work."

**Reuse:** the format contract in `ai/prompts.py` and the renderer's line-classification rules — don't change these, they're solid.
**Build:** the actual content, from Phase 0's raw material, written by us together once you've answered the inventory questions.

---

## Phase 2 — Make the keyword matching real, not just AI vibes

Right now the tailoring step is: hand Claude the JD + base resume + a system prompt that says "match relevant things." That's reasonable but soft — there's no explicit accounting of *which* JD keywords made it into the output.

Two focused additions close that loop:

1. **JD keyword extraction before the AI call.** The repo already has an unused module (`ai/skills_signal_extractor.py`) that regex-extracts technical terms from a JD. It's currently dead code — never called from the live pipeline (`core/batch_processor.py` doesn't import it). Wire it in: extract the JD's required keywords, cross-reference against your master resume's actual skill inventory, and pass the AI an explicit list of "these are the ones you're allowed to emphasize" — turning an implicit ask into an explicit, auditable one.
2. **Post-generation coverage check.** After Claude returns the tailored text, run the same keyword extractor against the *output* and log a coverage score (e.g. "7 of 9 matched keywords present") before marking the row `DOCX_READY`. This becomes a visible signal in the Streamlit review step — you can see at a glance whether a tailored resume is actually keyword-strong before you spend time reading it.

**Reuse:** `ai/jd_validator.py` (deterministic pre-AI filter, saves budget), `ai/provider_router.py` + `BudgetGuard`, `ai/skills_signal_extractor.py` (currently unused — this is where it earns its keep).
**Rebuild/extend:** wire the extractor into `batch_processor.py`, add a `keyword_coverage` column to the tracker, surface it in the Streamlit UI.

---

## Phase 2B — Alternative: run tailoring on your Claude subscription instead of the API

You asked for an alternative to metered API billing, since you're already paying for a Claude subscription. This is genuinely doable — I checked the current docs rather than assuming — but it comes with real trade-offs worth weighing against the API-key path in Phase 2, not a strictly-better swap.

### How it actually works

Claude Code (the CLI) supports two separate authentication modes:

- **API key** — `ANTHROPIC_API_KEY` in the environment, billed per token. This is what `job_automation/.env` currently uses via `ai/providers/anthropic_client.py`.
- **Subscription login** — run `claude /login` once and authenticate with your claude.ai account (Pro/Max/whatever you're on). From then on, Claude Code calls draw from your **plan's included usage** instead of metered billing — the same pool this Cowork conversation is running on.

Critically: **if `ANTHROPIC_API_KEY` is set in the environment, Claude Code uses it and bills per-token regardless of whether you're logged in.** So the two modes are mutually exclusive per-process — you'd need `job_automation`'s environment to have no API key set, with the machine logged into your subscription via `claude /login`.

Claude Code also has an official, documented **headless/non-interactive mode** built exactly for scripts and CI: `claude -p "your prompt" --allowedTools "..."`. That's not a hack — it's the same mechanism GitHub Actions and CI pipelines use. `--output-format json` returns the response text plus a cost estimate per call, which is exactly the shape `ProviderResult` in this codebase already expects.

### What changes in the repo

This slots into the existing provider abstraction cleanly — you don't need to touch `ai/tailor.py`, `ai/prompts.py`, `core/batch_processor.py`, or the DOCX renderer at all:

- Add a new provider, e.g. `ai/providers/claude_code_client.py`, implementing the same interface as `ai/providers/anthropic_client.py` — but instead of an SDK call, it shells out to `claude -p "<prompt>" --output-format json --allowedTools ""` (no tools needed; this is a single-shot text-generation call, not an agentic session) and parses the JSON response into a `ProviderResult`.
- Set `ai.provider: "claude_code"` in `config.yaml` (or make it the sole entry in `fallback_order`).
- The dollar-based `BudgetGuard` (`daily_cap_usd` / `monthly_cap_usd`) stops being the meaningful constraint, since you're not paying per call — swap it for a **volume cap** instead (e.g. reuse `batch.batch_size` / `batch.interval_minutes`, which already exist) so the batch job doesn't quietly burn through your plan's shared usage window in one run.

### The trade-offs, honestly

| | **Phase 2 (API key)** | **Phase 2B (subscription)** |
|---|---|---|
| Cost model | Pay per token, on top of any subscription | Included in the subscription you already pay for |
| Spend cap needed | Yes — dollar-based (`BudgetGuard`, already built) | Not dollar-based — needs a volume cap instead |
| Usage ceiling | Your API rate limits / budget caps only | **Shared** with your interactive Claude Code and Cowork usage — a rolling 5-hour session window plus a weekly cap on Pro/Max. A large batch run competes with the rest of your Claude usage that day. |
| Call overhead | Direct API call, minimal startup | Each `claude -p` call spins up a full Claude Code session (loads hooks, CLAUDE.md, MCP servers, skills) unless you use `--bare` — but **`--bare` mode only works with an API key, not subscription login**, so the lighter/faster path isn't available on the subscription route |
| Setup | Add `ANTHROPIC_API_KEY` to `.env` | Run `claude /login` once on the machine running `job_automation`, and make sure that environment has no `ANTHROPIC_API_KEY` set |
| Best for | Predictable, isolated, always-on automation | Personal-scale volume where you're comfortable trading some of your own Claude Code/Cowork headroom for the day |

**My honest read:** for the volume this system is actually operating at (single-digit to low-double-digit tailored resumes per batch, capped by `batch_size: 5` and a 24-hour SLA), Phase 2B is a completely reasonable choice and saves you real money on top of a subscription you're already paying for. The thing to watch is that it draws from the *same* usage pool as this conversation and any other Claude Code work you do — so if you're mid-way through a heavy coding session elsewhere and the job-automation batch fires in the background, you could see both compete for the same window. Worth monitoring with the `/usage` command for the first week to see how much headroom a full day of scraping + tailoring actually consumes before deciding whether to keep the API-key path as a fallback (`fallback_order: [claude_code, anthropic]` — the router already supports fallback chains) for when the subscription window is tight.

**Reuse:** the entire `ProviderRouter` abstraction, `ai/tailor.py`, `ai/prompts.py`, `core/batch_processor.py` — none of this needs to change, because the provider interface already isolates "how do we call the model" from everything else.
**Build:** one new provider client (`ai/providers/claude_code_client.py`) and a volume-based cap in place of the dollar-based one.

---

## Phase 3 — DOCX generation (mostly done — verify, don't rebuild)

`output/docx_renderer.py` already does the right things for ATS parsing: single-column, no tables/text boxes/images, real text, standard fonts and section headers, atomic write-validate-move so a broken render never gets marked ready. Leave it alone structurally. The only addition: log the keyword coverage score into the filename or a metadata column so it's visible without opening the file.

---

## Phase 4 — Review workflow (keep Streamlit, make it faster to scan)

Keep `web_ui/app.py` as the approval gate — reading every tailored resume before it goes anywhere is a good instinct and costs you almost nothing in time once Phase 2's coverage score is showing. Add the coverage score as a sortable column so you can triage: high-coverage rows get a quick skim, low-coverage rows get closer scrutiny (they're either a bad keyword match or a case where you genuinely lack the skill — worth knowing either way).

---

## Phase 5 — "Applied to every single job": what's realistic to automate

Scraping and tailoring can be close to 100% automated. **Submission should not be**, and I want to be direct about why rather than overpromise:

- Every employer/portal uses a different application system underneath (Workday, Greenhouse, Taleo, a native CareersFuture/Indeed form, sometimes a redirect to the company's own site). There's no single "apply" action to automate — each one is a different form with different required fields, file upload mechanics, and often a CAPTCHA.
- A fully blind auto-submit risks: applying with a resume that has a low keyword-coverage score, applying twice to the same listing, applying to something that quietly changed (JD edited, role closed), or tripping a portal's bot-detection and getting your account flagged.
- Realistic automation ceiling: **auto-tailor and auto-build a ready DOCX for every qualifying job** (fully automated, already ~90% built), then a **fast one-click review-and-apply step** — for portals with a stable, scriptable apply form, browser automation (e.g. Claude in Chrome) can pre-fill the application with your tailored resume and details, but you click the final Submit. That gets you "apply to every job" in practice — minutes of review per application instead of hours of manual re-tailoring — without the risk of a fully unattended submitter.

---

## Phase 6 — Scale and operating cadence

- Turn on the **Indeed** adapter (`adapters/indeed.py` exists, config-enabled, but has never actually been run — verify it still works against the live site before trusting it).
- Leave **JobStreet** off unless CareersFuture + Indeed aren't producing enough volume.
- Run the existing three-phase loop (`main.py`, every 5 minutes: scrape → validate → batch) once `base_resume.txt` exists — the orchestrator, rate limiter, and session manager are already built for this.
- Budget caps stay as configured ($5/day, $50/month) — plenty of headroom for daily volume at Sonnet pricing.
- Dedup is already handled by the Excel tracker's status lifecycle (a job only gets one `job_id` row) — no new work needed here.

---

## Phase 7 — Feedback loop (after the first real batch)

Once you've sent a few dozen tailored applications, track response/interview rate against the keyword-coverage score from Phase 2. If high-coverage resumes aren't converting better than low-coverage ones, that's a signal the keyword-matching isn't the bottleneck and something else (role fit, application volume in the market, etc.) is — worth knowing before over-investing further in the matching engine.

---

## Reuse vs. rebuild, at a glance

| Component | Verdict | Why |
|---|---|---|
| Scraper adapters (`adapters/`) | Reuse | CareersFuture proven (160 jobs scraped); Indeed untested but present |
| Excel tracker / state machine (`data/`) | Reuse | Solid lifecycle, zero-infra, already working |
| JD validator (`ai/jd_validator.py`) | Reuse | Good pre-AI cost filter; keyword sets need Phase 0 input to stay accurate |
| Provider router + budget guard (`ai/provider_router.py`) | Reuse | Budget caps + fallback already correct; works unchanged with either Phase 2 (API key) or Phase 2B (subscription) |
| AI billing model | **Your choice — Phase 2 or 2B** | API key = predictable, isolated, metered. Subscription (via `claude -p`) = no extra cost, but shares your Claude Code/Cowork usage window |
| Tailoring prompts (`ai/prompts.py`) | Reuse, lightly extend | Anti-hallucination rules are good; add explicit keyword checklist (Phase 2) |
| `ai/skills_signal_extractor.py`, `ai/jd_signal_extractor.py` | **Currently dead code — wire in** | Built but never called from the live pipeline |
| DOCX renderer (`output/docx_renderer.py`) | Reuse as-is | Already ATS-safe by design |
| Streamlit review UI (`web_ui/app.py`) | Reuse, add a column | Good human checkpoint; needs the coverage score surfaced |
| `base_resume.txt` | **Doesn't exist — build in Phase 0/1** | Root cause of the keyword problem |
| Auto-submit to employers | **Don't build as fully automated** | Too many portal-specific forms + real risk; semi-auto (Phase 5) is the right ceiling |

---

## Immediate next step

Everything downstream depends on Phase 0. The single highest-leverage thing you can do right now is answer the inventory questions above for your four roles and four projects — as messy and unpolished as you want. Send that over (or we can do it live, role by role) and I'll turn it directly into `base_resume.txt`, wire in the keyword-coverage check, and get the pipeline to the point where `python main.py` produces real, honest, keyword-strong tailored resumes.
