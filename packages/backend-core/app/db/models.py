"""SQLAlchemy 2.0 models for PostgreSQL database"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, func, text, Date
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass


class Book(Base):
    """Book model with full metadata and processing status"""
    __tablename__ = "books"

    # Primary key - using String to match existing MD5-based IDs
    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        nullable=False
    )

    # Required fields
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        index=True,
        nullable=False
    )

    # Optional fields
    author: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(20),
        default="private",
        server_default="private",
        nullable=False
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

    # Arrays (PostgreSQL)
    categories: Mapped[List[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        server_default=text("'{}'")
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
        nullable=False
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False
    )
    file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_type: Mapped[str] = mapped_column(String(10), default="pdf", server_default="pdf", nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 'upload', 'gcs'
    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    pages: Mapped[List["Page"]] = relationship(
        "Page",
        back_populates="book",
        cascade="all, delete-orphan"
    )
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk",
        back_populates="book",
        cascade="all, delete-orphan"
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
            name="books_status_check"
        ),
        CheckConstraint(
            "visibility IN ('public', 'private')",
            name="books_visibility_check"
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
        nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        index=True,
        nullable=False
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_toc: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    pipeline_step: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    milestone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    
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
        nullable=False
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="pages")

    __table_args__ = (
        UniqueConstraint("book_id", "page_number", name="pages_book_id_page_number_key"),
        CheckConstraint(
            "status IN ('pending', 'ocr_processing', 'ocr_done', 'chunked', 'indexing', 'indexed', 'error')",
            name="pages_status_check"
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
        nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(3072),  # pgvector type
        nullable=True
    )
    embedding_v1: Mapped[Optional[List[float]]] = mapped_column(
        Vector(768),  # Old 768-dim column (to be removed in migration 038)
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint(
            "book_id", "page_number", "chunk_index",
            name="chunks_book_id_page_number_chunk_index_key"
        ),
    )


class User(Base):
    """User model with OAuth provider information"""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        server_default=text("uuid_generate_v4()")
    )

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provider_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    role: Mapped[str] = mapped_column(
        String(20),
        default="reader",
        server_default="reader",
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    last_login_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Relationships
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="users_provider_provider_id_key"),
        CheckConstraint(
            "role IN ('admin', 'editor', 'reader')",
            name="users_role_check"
        ),
    )


class RefreshToken(Base):
    """Refresh token model for JWT authentication"""
    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    device_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False
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
        nullable=False
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
        ARRAY(Text),
        default=list,
        server_default=text("'{}'")
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True
    )

    # Performance metrics
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answer_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamp
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
        index=True
    )



class Dictionary(Base):
    """Dictionary model for Uyghur language spell checking"""
    __tablename__ = "dictionary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)




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
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
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
        nullable=False
    )


class UserChatUsage(Base):
    """Daily chat usage counter per user"""
    __tablename__ = "user_chat_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    usage_date: Mapped[datetime.date] = mapped_column(
        Date,
        default=func.current_date(),
        server_default=func.current_date(),
        index=True,
        nullable=False
    )
    count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="user_chat_usage_user_id_date_key"),
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
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_v1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[List[float]] = mapped_column(Vector(3072), nullable=False)
    embedding_draft: Mapped[Optional[List[float]]] = mapped_column(Vector(3072), nullable=True)
    embedding_v1: Mapped[Optional[List[float]]] = mapped_column(
        Vector(768),  # Old 768-dim column (to be removed in migration 038)
        nullable=True
    )
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
    interest: Mapped[str] = mapped_column(String(50), nullable=False)  # editor, developer, other
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Status and admin fields
    status: Mapped[str] = mapped_column(
        String(20),
        default="new",
        server_default="new",
        index=True,
        nullable=False
    )  # new, reviewed, contacted, archived
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    __table_args__ = (
        CheckConstraint(
            "interest IN ('editor', 'developer', 'other')",
            name="contact_submissions_interest_check"
        ),
        CheckConstraint(
            "status IN ('new', 'reviewed', 'contacted', 'archived')",
            name="contact_submissions_status_check"
        ),
    )


class PipelineEvent(Base):
    """Transactional outbox for pipeline state transitions"""
    __tablename__ = "pipeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob
    processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

