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


# --- OCR Correction System Models ---

class RawVariant(BaseModel):
    token: str
    count: int = 0


class OcrVocabulary(BaseModel):
    token: str
    rawVariants: List[RawVariant] = Field(default_factory=list)
    frequency: int
    bookSpan: int
    pageSpan: int
    lastSeenAt: datetime
    status: str  # "verified" | "suspect" | "ignored" | "corrected"
    correctedTo: Optional[str] = None
    manualOverride: bool = False
    flags: List[str] = Field(default_factory=list)


class OcrCorrectionJob(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    status: str  # "pending" | "running" | "completed" | "failed" | "paused"
    sourceToken: str
    targetToken: str
    totalPages: int
    processedPages: int = 0
    lastProcessedPageId: Optional[str] = None
    affectedBookIds: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    startedAt: Optional[datetime] = None


class OcrCorrectionHistory(BaseModel):
    jobId: str
    pageId: str
    bookId: str
    sourceToken: str
    targetToken: str
    lineIndex: int
    contextBefore: str
    contextAfter: str
    originalText: str
    appliedAt: datetime = Field(default_factory=datetime.utcnow)
