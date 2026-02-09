from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ErrorEvent(BaseModel):
    ts: datetime
    kind: str
    message: str
    context: Optional[dict] = None


class ExtractionResult(BaseModel):
    pageNumber: int
    text: Optional[str] = None
    status: str
    isVerified: bool = False
    error: Optional[str] = None


class Book(BaseModel):
    id: str
    contentHash: str
    title: str
    author: str
    volume: Optional[int] = None
    totalPages: int
    pages: List[ExtractionResult] = Field(default_factory=list)
    status: str
    uploadDate: datetime
    lastUpdated: Optional[datetime] = None
    coverUrl: Optional[str] = None
    visibility: str = "private"
    processingStep: Optional[str] = "ocr"
    categories: List[str] = Field(default_factory=list)
    errors: List[ErrorEvent] = Field(default_factory=list)
    lastError: Optional[ErrorEvent] = None
    completedCount: int = 0
    errorCount: int = 0


class PaginatedBooks(BaseModel):
    books: List[Book]
    total: int
    totalReady: int
    page: int
    pageSize: int


class ChatRequest(BaseModel):
    bookId: str
    question: str
    history: List[dict] = []
    currentPage: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
