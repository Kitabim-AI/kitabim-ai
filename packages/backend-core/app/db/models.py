"""SQLAlchemy 2.0 models for PostgreSQL database"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    Date,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models"""

    pass


class Book(Base):
    """Book model with full metadata and processing status"""

    __tablename__ = "books"

    # Primary key - using String to match existing MD5-based IDs
    id: Mapped[str] = mapped_column(String(64), primary_key=True, nullable=False)

    # Required fields
    content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        index=True,
        nullable=False,
    )

    # Optional fields
    author: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(20), default="private", server_default="private", nullable=False
    )
    pipeline_step: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Book-level milestones (denormalized from pages for performance)
    ocr_milestone: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )
    chunking_milestone: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )
    embedding_milestone: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )
    spell_check_milestone: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )
    graph_milestone: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )

    # Arrays (PostgreSQL)
    categories: Mapped[List[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )

    # JSONB fields
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Counts
    read_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Timestamps & audit
    upload_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_type: Mapped[str] = mapped_column(
        String(10), default="pdf", server_default="pdf", nullable=False
    )
    source: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # 'upload', 'gcs'
    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content_page_offset: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Relationships
    pages: Mapped[List["Page"]] = relationship(
        "Page", back_populates="book", cascade="all, delete-orphan"
    )
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk", back_populates="book", cascade="all, delete-orphan"
    )
    summary: Mapped[Optional["BookSummary"]] = relationship(
        "BookSummary",
        back_populates="book",
        cascade="all, delete-orphan",
        uselist=False,
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'ocr_processing', 'ocr_done', 'indexing', 'ready', 'error')",
            name="books_status_check",
        ),
        CheckConstraint(
            "visibility IN ('public', 'private')", name="books_visibility_check"
        ),
    )


class Page(Base):
    """Page model with OCR text and embeddings"""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("books.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_page_number: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )

    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        index=True,
        nullable=False,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_indexed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_toc: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    pipeline_step: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    milestone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # New decoupled milestones
    ocr_milestone: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )
    chunking_milestone: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )
    embedding_milestone: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )
    spell_check_milestone: Mapped[Optional[str]] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=True
    )

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="pages")

    @property
    def display_page_number(self) -> str:
        """Returns printed content page number string if explicitly set,
        otherwise calculates based on book.content_page_offset if available,
        or falls back to physical page_number as a string.
        """
        if self.content_page_number is not None:
            return self.content_page_number
        offset = (
            getattr(self.book, "content_page_offset", 0)
            if hasattr(self, "book") and self.book
            else 0
        )
        if offset > 0 and self.page_number > offset:
            return str(self.page_number - offset)
        return str(self.page_number)

    __table_args__ = (
        UniqueConstraint(
            "book_id", "page_number", name="pages_book_id_page_number_key"
        ),
        CheckConstraint(
            "status IN ('pending', 'ocr_processing', 'ocr_done', 'chunked', 'indexing', 'indexed', 'error')",
            name="pages_status_check",
        ),
    )


class BatchOCRJob(Base):
    """Batch OCR Job model tracking Gemini Batch API requests"""

    __tablename__ = "batch_ocr_jobs"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    gemini_batch_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    book_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("books.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_ids: Mapped[List[int]] = mapped_column(ARRAY(Integer), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="submitting",
        server_default="submitting",
        index=True,
        nullable=False,
    )

    gcs_input_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gcs_output_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    total_pages: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    processed_pages: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book")

    __table_args__ = (
        CheckConstraint(
            "status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')",
            name="check_batch_ocr_jobs_status",
        ),
    )


class BatchEmbeddingJob(Base):
    """Batch Embedding Job model tracking Gemini Batch API embedding requests"""

    __tablename__ = "batch_embedding_jobs"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    gemini_batch_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    book_ids: Mapped[List[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    page_ids: Mapped[List[int]] = mapped_column(ARRAY(Integer), nullable=False)
    chunk_ids: Mapped[List[int]] = mapped_column(ARRAY(Integer), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="submitting",
        server_default="submitting",
        index=True,
        nullable=False,
    )

    gcs_input_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gcs_output_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    total_chunks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    processed_chunks: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')",
            name="check_batch_embedding_jobs_status",
        ),
    )


class BatchHistoryExtractionJob(Base):
    """Batch History Extraction Job model tracking Gemini Batch API history extraction requests"""

    __tablename__ = "batch_history_extraction_jobs"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    gemini_batch_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    book_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("books.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="submitting",
        server_default="submitting",
        index=True,
        nullable=False,
    )

    gcs_input_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gcs_output_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    total_batches: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    min_significance: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5"
    )
    model_name: Mapped[str] = mapped_column(
        String(100), default="gemini-2.5-flash", server_default="gemini-2.5-flash"
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book")

    __table_args__ = (
        CheckConstraint(
            "status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')",
            name="check_batch_history_jobs_status",
        ),
    )


class Chunk(Base):
    """Chunk model for RAG with semantic embeddings"""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("books.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(3072),  # pgvector type
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint(
            "book_id",
            "page_number",
            "chunk_index",
            name="chunks_book_id_page_number_chunk_index_key",
        ),
    )


class User(Base):
    """User model with OAuth provider information"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        server_default=text("uuid_generate_v4()"),
    )

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provider_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    role: Mapped[str] = mapped_column(
        String(20), default="reader", server_default="reader", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    # Relationships
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_id", name="users_provider_provider_id_key"
        ),
        CheckConstraint(
            "role IN ('admin', 'editor', 'reader')", name="users_role_check"
        ),
    )


class RefreshToken(Base):
    """Refresh token model for JWT authentication"""

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        server_default=text("uuid_generate_v4()"),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    device_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


class Proverb(Base):
    """Proverb model for Uyghur proverbs about knowledge and books"""

    __tablename__ = "proverbs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )


class Quran(Base):
    """Quran model for Uyghur, English and Arabic verses (ayahs)"""

    __tablename__ = "quran"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    surah: Mapped[int] = mapped_column(Integer, nullable=False)
    surah_name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    surah_name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    surah_name_ug: Mapped[str] = mapped_column(String(255), nullable=False)
    ayah: Mapped[int] = mapped_column(Integer, nullable=False)
    text_ar: Mapped[str] = mapped_column(Text, nullable=False)
    text_en: Mapped[str] = mapped_column(Text, nullable=False)
    text_ug: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(3072),  # pgvector type
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )


class RAGEvaluation(Base):
    """RAG evaluation model for tracking RAG query performance metrics"""

    __tablename__ = "rag_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Query context
    book_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    current_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Retrieval metrics
    retrieved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    context_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scores: Mapped[Optional[List[float]]] = mapped_column(ARRAY(Float), nullable=True)
    category_filter: Mapped[List[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Performance metrics
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answer_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Agent-execution RAG metrics, set by ChatOrchestrator's retrieval agent run
    agent_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tools_called: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    retry_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    final_chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Ragas semantic evaluation metrics
    faithfulness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    answer_relevance_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    context_precision_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    context_recall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eval_status: Mapped[str] = mapped_column(
        String(20), default="skipped", server_default="skipped", nullable=False
    )
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieved_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # User feedback ('positive' = 👍, 'negative' = 👎, None = no feedback yet)
    user_feedback: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Multi-turn session tracking
    conversation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # True when this question opened a new conversation (history was empty)
    is_first_turn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Admin-curated flag: show this question in the home-page rotator
    show_on_homepage: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Timestamp
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


class Word(Base):
    """Word model for Uyghur language spell checking"""

    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )


class Dictionary(Base):
    """Dictionary model containing definitions and audio"""

    __tablename__ = "dictionary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class PageSpellIssue(Base):
    """A single unknown-word occurrence detected by dictionary-based spell check"""

    __tablename__ = "page_spell_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word: Mapped[str] = mapped_column(Text, nullable=False)
    char_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ocr_corrections: Mapped[List[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default="open", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    auto_corrected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'corrected', 'ignored', 'processing')",
            name="page_spell_issues_status_check",
        ),
    )


class AutoCorrectRule(Base):
    """Auto-correction rules for spell check issues"""

    __tablename__ = "auto_correct_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    misspelled_word: Mapped[str] = mapped_column(Text, unique=True, index=True)
    corrected_word: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "misspelled_word != corrected_word",
            name="auto_correct_rules_different_words",
        ),
    )


class SystemConfig(Base):
    """General system configuration entries"""

    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )


class UserChatUsage(Base):
    """Daily chat usage counter per user"""

    __tablename__ = "user_chat_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    usage_date: Mapped[datetime.date] = mapped_column(
        Date,
        default=func.current_date(),
        server_default=func.current_date(),
        index=True,
        nullable=False,
    )
    count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "usage_date", name="user_chat_usage_user_id_date_key"
        ),
    )


class BookSummary(Base):
    """LLM-generated semantic summary + embedding for each ready book, used for hierarchical RAG retrieval."""

    __tablename__ = "book_summaries"

    book_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("books.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[List[float]] = mapped_column(Vector(3072), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    book: Mapped["Book"] = relationship("Book", back_populates="summary")


class ContactSubmission(Base):
    """Contact form submissions from Join Us page"""

    __tablename__ = "contact_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Form fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    interest: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # editor, developer, other
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Status and admin fields
    status: Mapped[str] = mapped_column(
        String(20), default="new", server_default="new", index=True, nullable=False
    )  # new, reviewed, contacted, archived
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "interest IN ('editor', 'developer', 'other')",
            name="contact_submissions_interest_check",
        ),
        CheckConstraint(
            "status IN ('new', 'reviewed', 'contacted', 'archived')",
            name="contact_submissions_status_check",
        ),
    )


class Synonym(Base):
    """Uyghur synonym dictionary — one row per headword"""

    __tablename__ = "synonyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    letter_group: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    synonyms: Mapped[List[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )


class HistoryDictionary(Base):
    """Uyghur historical dictionary — entries parsed from the uyghur-language history corpus"""

    __tablename__ = "history_dictionary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True, index=True
    )
    transliteration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    letter_group: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        String(30),
        default="general",
        server_default="general",
        nullable=False,
        index=True,
    )
    significance_score: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5", nullable=False, index=True
    )
    is_ai_generated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )
    facts: Mapped[list] = mapped_column(
        JSON, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    aliases: Mapped[list] = mapped_column(
        JSON, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )


class HistoryDictionaryStaging(Base):
    """Staging queue for extracted history dictionary candidates awaiting admin review"""

    __tablename__ = "history_dictionary_staging"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    existing_dictionary_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("history_dictionary.id", ondelete="SET NULL"), nullable=True
    )
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    term: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    transliteration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(30), default="general", nullable=False)
    significance_score: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False, index=True
    )
    significance_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    entry_type: Mapped[str] = mapped_column(
        String(20), default="new", nullable=False, index=True
    )
    letter_group: Mapped[str] = mapped_column(String(10), nullable=False)
    facts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    aliases: Mapped[list] = mapped_column(
        JSON, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class NamesDictionary(Base):
    """Uyghur person names dictionary"""

    __tablename__ = "names_dictionary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True, index=True
    )
    letter_group: Mapped[str] = mapped_column(String(20), nullable=False, index=True)


class EnglishUyghurDictionary(Base):
    """English-Uyghur bilingual dictionary"""

    __tablename__ = "english_uyghur_dictionary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    english: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True, index=True
    )
    uyghur: Mapped[str] = mapped_column(Text, nullable=False)
    letter_group: Mapped[str] = mapped_column(String(5), nullable=False, index=True)


class PipelineEvent(Base):
    """Transactional outbox for pipeline state transitions"""

    __tablename__ = "pipeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob
    processed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )


class Conversation(Base):
    """Conversation session for multi-turn chat persistence"""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("books.id", ondelete="SET NULL"),
        nullable=True,
    )
    book: Mapped[Optional["Book"]] = relationship("Book", lazy="selectin")
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ConversationMessage(Base):
    """Message turns inside a conversation"""

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # 'user' | 'model'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_steps: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    used_book_ids: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    current_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eval_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("rag_evaluations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )


class GraphResolutionQueue(Base):
    """Coordinates claiming of Neo4j Entity nodes for the global resolution pass.

    Postgres owns queue state (FOR UPDATE SKIP LOCKED); Neo4j owns the entity data
    itself. See knowledge-graph-entity-resolution-design-v2.md §2/§4.
    """

    __tablename__ = "graph_resolution_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    book_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("books.id", ondelete="CASCADE"), nullable=True
    )
    sort_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", index=True, nullable=False
    )
    pass_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "scope IN ('fiction', 'nonfiction')",
            name="graph_resolution_queue_scope_check",
        ),
        CheckConstraint(
            "status IN ('idle', 'in_progress', 'succeeded', 'failed', 'needs_review')",
            name="graph_resolution_queue_status_check",
        ),
    )


class GraphResolutionReview(Base):
    """Admin review queue for gray-zone / ambiguous entity-resolution outcomes."""

    __tablename__ = "graph_resolution_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_a_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    entity_b_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    suggested_action: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        index=True,
        nullable=False,
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "scope IN ('fiction', 'nonfiction')",
            name="graph_resolution_reviews_scope_check",
        ),
        CheckConstraint(
            "suggested_action IN ('merge', 'split', 'unsure')",
            name="graph_resolution_reviews_suggested_action_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="graph_resolution_reviews_status_check",
        ),
    )


class GraphMergeLog(Base):
    """Pre-merge snapshot of the removed Entity node + its edges, enabling unmerge."""

    __tablename__ = "graph_merge_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kept_entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    removed_entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    removed_entity_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    removed_edges_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    performed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    reverted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
