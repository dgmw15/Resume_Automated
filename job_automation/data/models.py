from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    NEW = "NEW"
    SCRAPED = "SCRAPED"
    MISSING = "MISSING"
    # Validation states
    VALIDATION_PENDING = "VALIDATION_PENDING"
    VALIDATION_FAILED_NON_TECH = "VALIDATION_FAILED_NON_TECH"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    # Batch / AI states
    BATCH_QUEUED = "BATCH_QUEUED"
    AI_IN_PROGRESS = "AI_IN_PROGRESS"
    TAILORED_TEXT_READY = "TAILORED_TEXT_READY"
    DOCX_GENERATION_FAILED = "DOCX_GENERATION_FAILED"
    DOCX_READY = "DOCX_READY"
    # Legacy / end states
    TAILORED = "TAILORED"          # kept for backward compat
    AI_FAILED = "AI_FAILED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"


class JobListing(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    portal_name: str
    role: str
    company: str
    url: str
    raw_description: Optional[str] = None
    tailored_resume: Optional[str] = None
    status: JobStatus = JobStatus.NEW
    page_num: int = 1
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # Employment type filter fields (S4)
    employment_type_raw: Optional[str] = None
    employment_type_normalized: Optional[str] = None   # "internship", "contract", "permanent", "unknown"
    employment_filter_status: Optional[str] = None     # "PASSED", "FILTERED", "SKIPPED"
    employment_filter_reason: Optional[str] = None
    # Validation fields
    validation_score: Optional[int] = None
    validation_reason: Optional[str] = None
    # AI pipeline fields
    pipeline_track: Optional[str] = None       # "analyst" or "engineer"
    ai_provider_used: Optional[str] = None
    cost_usd: Optional[float] = None           # alias kept for backward compat
    cost_reserved_usd: Optional[float] = None  # tentative spend held by ledger
    cost_actual_usd: Optional[float] = None    # confirmed spend after provider response
    # Budget reservation fields
    reservation_id: Optional[str] = None
    reservation_expires_at: Optional[datetime] = None
    idempotency_key: Optional[str] = None      # stable key reused across retries
    # DOCX output fields
    docx_path: Optional[str] = None
    docx_validation_error: Optional[str] = None
    processed_at: Optional[datetime] = None
    # Salary fields — schema parity with trawl output (data_checker Phase D)
    salary_raw: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None    # "monthly", "annual", "unknown"
    salary_status: Optional[str] = None   # "OK", "MISSING", "AMBIGUOUS", "ERROR"

    # Column order for Excel — must stay in sync with ExcelTracker.COLUMNS
    EXCEL_COLUMNS: list[str] = [
        "id", "portal_name", "role", "company", "url",
        "raw_description", "tailored_resume", "status", "page_num", "timestamp",
        "validation_score", "validation_reason", "pipeline_track",
        "ai_provider_used", "cost_usd", "cost_reserved_usd", "cost_actual_usd",
        "reservation_id", "reservation_expires_at", "idempotency_key",
        "docx_path", "docx_validation_error", "processed_at",
        "employment_type_raw", "employment_type_normalized",
        "employment_filter_status", "employment_filter_reason",
        "salary_raw", "salary_min", "salary_max", "salary_currency",
        "salary_period", "salary_status",
    ]
