"""SQLAlchemy 2.0 models for PostgreSQL database"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint, func, text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass


class Book(Base):
    """Book model with full metadata and processing status"""
    __tablename__ = "books"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("uuid_generate_v4()")
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
    processing_step: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Arrays (PostgreSQL)
    categories: Mapped[List[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        server_default=text("'{}'")
    )
    tags: Mapped[List[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        server_default=text("'{}'")
    )

    # JSONB fields
    errors: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb")
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Counts
    completed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

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
    updated_by: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

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

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'error')",
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
    book_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
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
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(768),  # pgvector type for 768-dimensional embeddings
        nullable=True
    )

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False
    )
    updated_by: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="pages")

    __table_args__ = (
        UniqueConstraint("book_id", "page_number", name="pages_book_id_page_number_key"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'error')",
            name="pages_status_check"
        ),
    )


class Chunk(Base):
    """Chunk model for RAG with semantic embeddings"""
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(768),  # pgvector type
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

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
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

    jti: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("uuid_generate_v4()")
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


class Job(Base):
    """Job model for ARQ background job tracking"""
    __tablename__ = "jobs"

    job_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

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
