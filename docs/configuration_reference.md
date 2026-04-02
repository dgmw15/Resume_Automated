# Configuration Reference

This document provides a reference for the settings in the `config.yaml` file.

## `portals`

```yaml
portals:
  careersfuture:
    enabled: true
    max_actions_per_hour: 30   # browser clicks + page loads counted together
    min_delay_seconds: 5       # minimum wait between actions
    max_delay_seconds: 15      # maximum wait (randomised within range)
```

-   `enabled`: Set to `true` to enable scraping for the portal, `false` to disable.
-   `max_actions_per_hour`: The maximum number of actions (clicks, page loads) to perform per hour to avoid being blocked.
-   `min_delay_seconds`: The minimum delay in seconds between actions.
-   `max_delay_seconds`: The maximum delay in seconds between actions. The actual delay is a random value between `min_delay_seconds` and `max_delay_seconds`.

## `validation`

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

-   `min_keyword_hits`: The minimum number of technical keywords a job description must contain to be considered valid.
-   `role_keyword_sets`: Sets of keywords for different roles.
-   `deny_patterns`: A list of strings. If a job description contains any of these strings, it will be rejected.

## `ai`

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

-   `provider`: The primary AI provider to use.
-   `fallback_order`: The order of AI providers to use as fallbacks.
-   `model_map`: The AI model to use for each role track.
-   `budget`:
    -   `daily_cap_usd`: The maximum amount of money to spend per day.
    -   `monthly_cap_usd`: The maximum amount of money to spend per month.
    -   `hard_stop`: If set to `true`, the application will stop when the budget is exceeded.

## `batch`

```yaml
batch:
  enabled: true
  interval_minutes: 30         # how often the batch worker runs
  batch_size: 5                # max JDs processed per cycle
  target_sla_hours: 24         # target turnaround time for queued jobs
  max_retries: 3               # AI call retries before marking FAILED
```

-   `enabled`: Set to `true` to enable batch processing.
-   `interval_minutes`: The interval in minutes at which the batch worker runs.
-   `batch_size`: The maximum number of job descriptions to process in each batch.
-   `target_sla_hours`: The target service level agreement in hours for processing queued jobs.
-   `max_retries`: The maximum number of times to retry an AI call before marking it as failed.
