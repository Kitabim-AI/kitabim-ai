from __future__ import annotations

from datetime import datetime
from typing import List, Optional
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
    is_verified: bool = False  # DB: is_verified, API: isVerified
    error: Optional[str] = None
    last_updated: Optional[datetime] = None  # DB: last_updated, API: lastUpdated
    updated_by: Optional[str] = None  # DB: updated_by, API: updatedBy


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
    updated_by: Optional[str] = None  # DB: updated_by, API: updatedBy
    created_by: Optional[str] = None  # DB: created_by, API: createdBy
    cover_url: Optional[str] = None  # DB: cover_url, API: coverUrl
    visibility: str = "private"
    processing_step: Optional[str] = "ocr"  # DB: processing_step, API: processingStep
    categories: List[str] = Field(default_factory=list)
    last_error: Optional[ErrorEvent] = None  # DB: last_error, API: lastError
    completed_count: int = 0  # DB: completed_count, API: completedCount
    error_count: int = 0  # DB: error_count, API: errorCount
    file_name: Optional[str] = None  # Original uploaded filename


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


class ChatUsageStatus(BaseModel):
    usage: int
    limit: Optional[int]
    has_reached_limit: bool
