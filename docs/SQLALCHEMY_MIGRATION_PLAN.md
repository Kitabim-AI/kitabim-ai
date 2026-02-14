# SQLAlchemy Migration Plan

> **Created:** 2026-02-14
> **Status:** Planning
> **Effort:** Medium-Large (~2-3 days)
> **Risk:** Medium (requires careful testing)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Goals](#goals)
3. [Current State Analysis](#current-state-analysis)
4. [Proposed Architecture](#proposed-architecture)
5. [Migration Strategy](#migration-strategy)
6. [Implementation Plan](#implementation-plan)
7. [Testing Strategy](#testing-strategy)
8. [Rollback Plan](#rollback-plan)
9. [Risk Assessment](#risk-assessment)

---

## Executive Summary

Migrate from **raw asyncpg + manual helpers** to **SQLAlchemy 2.0 (async)** to:
- Eliminate ~200 lines of camelCase/snake_case conversion code
- Gain type-safe queries and ORM benefits
- Enable automatic schema migrations with Alembic
- Improve developer experience with better IDE support

**Key Decision:** Use SQLAlchemy 2.0 with async support (not legacy 1.4)

---

## Goals

### Primary Goals
1. **Eliminate manual case conversion** - Remove all camelCase ↔ snake_case helper code
2. **Type safety** - Add compile-time type checking for database queries
3. **Maintainability** - Reduce code complexity and improve readability
4. **Migration support** - Enable Alembic for schema version control

### Non-Goals
1. ❌ Change database schema (keep existing PostgreSQL schema)
2. ❌ Modify API contracts (keep existing Pydantic models)
3. ❌ Rewrite business logic (only change data access layer)

---

## Current State Analysis

### Files to Replace/Modify

```
packages/backend-core/app/db/
├── postgres.py                 # 250 lines → SQLAlchemy Base + Session
├── postgres_adapter.py         # 200 lines → Repository pattern with SQLAlchemy
├── postgres_helpers.py         # 350 lines → REMOVE (replaced by SQLAlchemy)
└── mongodb.py                  # 80 lines → REMOVE (legacy, unused)
```

### Code Statistics

| Component | Current Lines | After Migration | Reduction |
|-----------|--------------|-----------------|-----------|
| Connection management | ~100 | ~30 | -70% |
| Case conversion | ~200 | 0 | -100% |
| Query builders | ~250 | ~50 | -80% |
| Repository pattern | ~200 | ~150 | -25% |
| **Total** | **~750** | **~230** | **-69%** |

### Dependencies to Add

```txt
# requirements.txt additions
sqlalchemy[asyncio]==2.0.28
alembic==1.13.1
greenlet==3.0.3  # Required for async SQLAlchemy
```

### Dependencies to Keep

```txt
asyncpg==0.31.0      # SQLAlchemy will use this as driver
pgvector==0.4.2      # For vector operations
```

---

## Proposed Architecture

### SQLAlchemy 2.0 Models

```python
# packages/backend-core/app/db/models.py (NEW)
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from datetime import datetime
from uuid import uuid4

class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass

class Book(Base):
    __tablename__ = 'books'

    # Primary key
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))

    # Core fields
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    processing_step: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Timestamps
    upload_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Audit
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)

    # Metadata
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default='private')
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    # Error tracking
    errors: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class Page(Base):
    __tablename__ = 'pages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    ocr_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)

class Chunk(Base):
    __tablename__ = 'chunks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class User(Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default='reader')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'

    jti: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Job(Base):
    __tablename__ = 'jobs'

    job_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
```

### Database Session Management

```python
# packages/backend-core/app/db/session.py (NEW)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# Create async engine
engine = create_async_engine(
    settings.database_url.replace('postgresql://', 'postgresql+asyncpg://'),
    echo=False,  # Set to True for SQL logging
    pool_size=10,
    max_overflow=20,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    """FastAPI dependency for database sessions"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### Updated Repository Pattern

```python
# packages/backend-core/app/db/repositories.py (NEW)
from typing import Optional, List
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Book, Page, Chunk, User

class BookRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, book_id: str) -> Optional[Book]:
        result = await self.session.execute(
            select(Book).where(Book.id == book_id)
        )
        return result.scalar_one_or_none()

    async def find_by_hash(self, content_hash: str) -> Optional[Book]:
        result = await self.session.execute(
            select(Book).where(Book.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def find_many(
        self,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Book]:
        query = select(Book)

        if status:
            query = query.where(Book.status == status)
        if visibility:
            query = query.where(Book.visibility == visibility)

        query = query.limit(limit).offset(offset).order_by(Book.upload_date.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **data) -> Book:
        book = Book(**data)
        self.session.add(book)
        await self.session.flush()
        return book

    async def update_one(self, book_id: str, **updates) -> Optional[Book]:
        stmt = (
            update(Book)
            .where(Book.id == book_id)
            .values(**updates)
            .returning(Book)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one_or_none()

    async def delete_one(self, book_id: str) -> bool:
        stmt = delete(Book).where(Book.id == book_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0
```

### Pydantic Integration (No Changes Needed!)

```python
# Existing Pydantic models work with SQLAlchemy via from_attributes
class BookResponse(BaseModel):
    id: str
    contentHash: str = Field(alias='content_hash')
    title: str
    # ... etc

    class Config:
        from_attributes = True  # This makes it work with SQLAlchemy models!

# Usage in endpoint:
book = await book_repo.find_by_id(book_id)
return BookResponse.from_orm(book)  # Auto-converts SQLAlchemy → Pydantic
```

---

## Migration Strategy

### Phase 1: Preparation (Day 1 - Morning)

1. **Add dependencies**
   ```bash
   pip install sqlalchemy[asyncio]==2.0.28 alembic==1.13.1 greenlet==3.0.3
   ```

2. **Create SQLAlchemy models**
   - Create `app/db/models.py` with all table models
   - Verify model definitions match existing schema

3. **Initialize Alembic**
   ```bash
   cd packages/backend-core
   alembic init alembic
   ```
   - Configure `alembic.ini`
   - Update `alembic/env.py` to use async

4. **Generate initial migration**
   ```bash
   alembic revision --autogenerate -m "Initial SQLAlchemy migration"
   ```
   - Review generated migration (should be empty/minimal)
   - Mark as baseline

### Phase 2: Core Implementation (Day 1 - Afternoon)

1. **Create new database layer**
   - Create `app/db/session.py` - async engine and session factory
   - Create `app/db/repositories.py` - repository classes
   - Keep old files temporarily for reference

2. **Update dependency injection**
   - Modify `app/main.py` to use SQLAlchemy session
   - Update FastAPI dependencies to inject `AsyncSession`

3. **Create adapter layer** (temporary)
   - Create shim functions that convert old API calls to new
   - Allows gradual migration

### Phase 3: Endpoint Migration (Day 2)

Migrate endpoints one-by-one in this order:

1. **Books endpoints** (`app/api/endpoints/books.py`)
   - `/api/books` (list)
   - `/api/books/{id}` (get)
   - `/api/books/upload` (create)
   - `/api/books/{id}` (update/delete)

2. **Users endpoints** (`app/api/endpoints/users.py`)
   - `/api/users` (list)
   - `/api/users/{id}` (get/update)

3. **Auth endpoints** (`app/api/endpoints/auth.py`)
   - `/api/auth/google`
   - Token refresh logic

4. **Chat endpoint** (`app/api/endpoints/chat.py`)
   - Update RAG service to use SQLAlchemy for chunk retrieval

### Phase 4: Service Layer (Day 2-3)

1. **PDF Service** (`app/services/pdf_service.py`)
   - Update all database calls to use repositories
   - Test OCR pipeline end-to-end

2. **RAG Service** (`app/services/rag_service.py`)
   - Update vector similarity queries
   - Verify pgvector integration with SQLAlchemy

3. **User Service** (`app/services/user_service.py`)
   - Migrate user CRUD operations

### Phase 5: Cleanup (Day 3)

1. **Remove old code**
   - Delete `postgres_helpers.py` (350 lines)
   - Delete `mongodb.py` (80 lines)
   - Clean up `postgres_adapter.py` (if fully replaced)
   - Remove manual case conversion code

2. **Update tests**
   - Modify existing tests to use SQLAlchemy fixtures
   - Add new tests for repository layer

3. **Documentation**
   - Update README files
   - Update AGENTS.md
   - Document new patterns

---

## Implementation Plan

### Step-by-Step Checklist

#### Setup
- [ ] Install SQLAlchemy dependencies
- [ ] Create `app/db/models.py` with all models
- [ ] Create `app/db/session.py` with engine/sessionmaker
- [ ] Initialize Alembic
- [ ] Generate baseline migration

#### Core Database Layer
- [ ] Create `app/db/repositories.py`
  - [ ] BookRepository
  - [ ] PageRepository
  - [ ] ChunkRepository
  - [ ] UserRepository
  - [ ] JobRepository
- [ ] Update `app/main.py` lifespan for SQLAlchemy
- [ ] Create `get_db()` dependency

#### Endpoints Migration
- [ ] Migrate `app/api/endpoints/books.py`
  - [ ] GET /api/books (list)
  - [ ] GET /api/books/{id} (get one)
  - [ ] POST /api/books/upload (create)
  - [ ] PATCH /api/books/{id} (update)
  - [ ] DELETE /api/books/{id} (delete)
  - [ ] POST /api/books/{id}/ocr/start
  - [ ] All other book endpoints

- [ ] Migrate `app/api/endpoints/users.py`
  - [ ] GET /api/users (list)
  - [ ] GET /api/users/{id} (get)
  - [ ] PATCH /api/users/{id} (update)

- [ ] Migrate `app/api/endpoints/auth.py`
  - [ ] POST /api/auth/google
  - [ ] POST /api/auth/refresh
  - [ ] User lookup and creation

- [ ] Migrate `app/api/endpoints/chat.py`
  - [ ] POST /api/chat

#### Services Migration
- [ ] Update `app/services/pdf_service.py`
  - [ ] process_pdf_task
  - [ ] All DB operations

- [ ] Update `app/services/rag_service.py`
  - [ ] Vector similarity search
  - [ ] Chunk retrieval

- [ ] Update `app/services/user_service.py`
  - [ ] All user operations

#### Worker
- [ ] Update `app/queue.py` for SQLAlchemy sessions
- [ ] Update `app/jobs.py` database calls
- [ ] Test background job processing

#### Cleanup
- [ ] Remove `app/db/postgres_helpers.py`
- [ ] Remove `app/db/mongodb.py`
- [ ] Remove unused imports
- [ ] Update requirements.txt (remove unused deps)

#### Testing & Validation
- [ ] Run all existing tests
- [ ] Test OCR pipeline end-to-end
- [ ] Test RAG chat (global and per-book)
- [ ] Test user authentication
- [ ] Test book CRUD operations
- [ ] Performance testing (compare query speeds)

#### Documentation
- [ ] Update `README.md`
- [ ] Update `AGENTS.md`
- [ ] Update `SYSTEM_DESIGN.md`
- [ ] Add migration guide for future reference

---

## Testing Strategy

### Unit Tests
```python
# Example test with SQLAlchemy
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.db.models import Base, Book
from app.db.repositories import BookRepository

@pytest.fixture
async def db_session():
    engine = create_async_engine("postgresql+asyncpg://localhost/test_db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.mark.asyncio
async def test_create_book(db_session):
    repo = BookRepository(db_session)
    book = await repo.create(
        content_hash="abc123",
        title="Test Book",
        total_pages=100,
    )
    assert book.id is not None
    assert book.title == "Test Book"
```

### Integration Tests
- Test full OCR pipeline
- Test RAG chat end-to-end
- Test user authentication flow
- Test file upload and processing

### Performance Tests
- Measure query performance before/after
- Verify vector similarity search speed
- Check memory usage

---

## Rollback Plan

### If Migration Fails Mid-Way

1. **Keep old code in git branch**
   ```bash
   git checkout kitabim-db-migration  # Current branch with old code
   ```

2. **Revert specific files**
   - All old database files are in git history
   - Can cherry-pick old implementations

3. **Database schema unchanged**
   - No schema changes = safe rollback
   - Just switch code back

### Rollback Steps
```bash
# If on sqlalchemy-migration branch and it's not working:
git stash  # Save any changes
git checkout kitabim-db-migration  # Go back to working version
kubectl rollout restart deployment/backend deployment/worker  # Redeploy
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Breaking API contracts** | Low | High | Keep Pydantic models unchanged; thorough testing |
| **Performance degradation** | Low | Medium | Benchmark before/after; SQLAlchemy 2.0 is fast |
| **Vector search issues** | Medium | High | Test pgvector integration early; fallback available |
| **Migration bugs** | Medium | Medium | Gradual migration; extensive testing |
| **Deployment issues** | Low | Medium | Test in local K8s first; rollback plan ready |

---

## Success Criteria

- [ ] All tests passing
- [ ] API responses unchanged (same structure)
- [ ] Performance within 10% of current
- [ ] Code reduction: -500+ lines
- [ ] No manual case conversion code
- [ ] Alembic migrations working
- [ ] Documentation updated

---

## Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 1: Preparation** | 4 hours | Models, Alembic setup |
| **Phase 2: Core Implementation** | 4 hours | Repositories, session management |
| **Phase 3: Endpoint Migration** | 8 hours | All endpoints migrated |
| **Phase 4: Service Layer** | 6 hours | Services updated |
| **Phase 5: Cleanup** | 2 hours | Old code removed, docs updated |
| **Total** | **24 hours** | **~3 working days** |

---

## Next Steps

1. ✅ Review this plan
2. ⏳ Get approval to proceed
3. ⏳ Create feature branch `sqlalchemy-migration`
4. ⏳ Execute Phase 1
5. ⏳ ...

---

*Last Updated: 2026-02-14*
