from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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
    content: Optional[str] = None
    results: List[ExtractionResult]
    status: str
    uploadDate: datetime
    lastUpdated: Optional[datetime] = None
    coverUrl: Optional[str] = None
    processingStep: Optional[str] = "ocr" # "ocr" or "rag"
    categories: List[str] = []

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
