from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field


def to_camel(string: str) -> str:
    """
    Convert snake_case to camelCase.

    Used by Pydantic's alias_generator to automatically convert
    SQLAlchemy model fields (snake_case) to API response fields (camelCase).

    This eliminates the need for manual conversion in postgres_helpers.py.
    """
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


class ErrorEvent(BaseModel):
    ts: datetime
    kind: str
    message: str
    context: Optional[dict] = None


class ExtractionResult(BaseModel):
    """Page extraction result with automatic camelCase conversion"""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    page_number: int  # DB: page_number, API: pageNumber
    text: Optional[str] = None
    status: str
    error: Optional[str] = None
    last_updated: Optional[datetime] = None  # DB: last_updated, API: lastUpdated
    pipeline_step: Optional[str] = None  # DB: pipeline_step, API: pipelineStep
    milestone: Optional[str] = None  # DB: milestone, API: milestone


class Book(BaseModel):
    """
    Book schema with automatic camelCase conversion from SQLAlchemy models.

    The alias_generator converts snake_case DB fields to camelCase API fields automatically.
    Example: content_hash (DB) → contentHash (API)
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # Accept both snake_case and camelCase
        from_attributes=True    # Enable .model_validate() from SQLAlchemy models
    )

    id: str
    content_hash: str  # DB: content_hash, API: contentHash (auto-converted)
    title: str
    author: str
    volume: Optional[int] = None
    total_pages: int  # DB: total_pages, API: totalPages (auto-converted)
    pages: List[ExtractionResult] = Field(default_factory=list)
    status: str
    upload_date: datetime  # DB: upload_date, API: uploadDate (auto-converted)
    last_updated: Optional[datetime] = None  # DB: last_updated, API: lastUpdated
    cover_url: Optional[str] = None  # DB: cover_url, API: coverUrl
    visibility: str = "private"
    categories: List[str] = Field(default_factory=list)
    last_error: Optional[ErrorEvent] = None  # DB: last_error, API: lastError
    read_count: int = 0  # DB: read_count, API: readCount
    file_name: Optional[str] = None  # Original uploaded filename
    file_type: Optional[str] = None  # File extension (e.g., 'pdf', 'docx')
    pipeline_step: Optional[str] = None  # DB: pipeline_step, API: pipelineStep
    pipeline_stats: Optional[Dict[str, int]] = Field(default_factory=dict) # DB: pipeline_stats, API: pipelineStats
    has_summary: bool = False  # API: hasSummary
    # Book-level milestones (denormalized from pages for performance)
    ocr_milestone: str = "idle"  # DB: ocr_milestone, API: ocrMilestone
    chunking_milestone: str = "idle"  # DB: chunking_milestone, API: chunkingMilestone
    embedding_milestone: str = "idle"  # DB: embedding_milestone, API: embeddingMilestone
    spell_check_milestone: str = "idle"  # DB: spell_check_milestone, API: spellCheckMilestone


class PaginatedBooks(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )
    books: List[Book]
    total: int
    total_ready: int
    page: int
    page_size: int


class ChatRequest(BaseModel):
    """Chat request with automatic camelCase conversion"""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    book_id: str  # API: bookId
    question: str
    history: List[dict] = []
    current_page: Optional[int] = None  # API: currentPage


class ChatResponse(BaseModel):
    answer: str
    usage: Optional[ChatUsageStatus] = None


class ChatUsageStatus(BaseModel):
    usage: int
    limit: Optional[int]
    has_reached_limit: bool


class ContactSubmissionCreate(BaseModel):
    """Schema for creating a new contact submission"""
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255)
    interest: Literal["editor", "developer", "other"]
    message: str = Field(..., min_length=10, max_length=5000)


class ContactSubmissionPublic(BaseModel):
    """Public response schema for contact submission"""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    id: int
    status: str
    created_at: datetime  # DB: created_at, API: createdAt


class ContactSubmissionAdmin(BaseModel):
    """Admin view schema for contact submissions with all fields"""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    id: int
    name: str
    email: str
    interest: str
    message: str
    status: str
    admin_notes: Optional[str] = None  # DB: admin_notes, API: adminNotes
    reviewed_by: Optional[str] = None  # DB: reviewed_by, API: reviewedBy
    reviewed_at: Optional[datetime] = None  # DB: reviewed_at, API: reviewedAt
    created_at: datetime  # DB: created_at, API: createdAt
