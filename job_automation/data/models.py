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
    # New fields
    validation_score: Optional[int] = None
    validation_reason: Optional[str] = None
    pipeline_track: Optional[str] = None       # "analyst" or "engineer"
    ai_provider_used: Optional[str] = None
    cost_usd: Optional[float] = None
    docx_path: Optional[str] = None
    processed_at: Optional[datetime] = None

    # Column order for Excel — must stay in sync with ExcelTracker.COLUMNS
    EXCEL_COLUMNS: list[str] = [
        "id", "portal_name", "role", "company", "url",
        "raw_description", "tailored_resume", "status", "page_num", "timestamp",
        "validation_score", "validation_reason", "pipeline_track",
        "ai_provider_used", "cost_usd", "docx_path", "processed_at",
    ]
