# SQLAlchemy Migration Status

**Last Updated:** 2026-02-14
**Branch:** kitabim-db-migration
**Overall Progress:** 40% Complete (Phases 1-2 Done)

---

## Quick Summary

✅ **Foundation Complete:** SQLAlchemy models, repositories, and session management are implemented and committed.

🎯 **Next Steps:** Migrate API endpoints to use new repository layer (starting with books endpoints).

---

## Phase Completion Status

| Phase | Status | Duration | Completion Date |
|-------|--------|----------|----------------|
| **Phase 1: Preparation** | ✅ Complete | 3 hours | 2026-02-14 |
| **Phase 2: Core Implementation** | ✅ Complete | 4 hours | 2026-02-14 |
| **Phase 3: Endpoint Migration** | ⏳ Pending | Est. 8 hours | - |
| **Phase 4: Service Layer** | ⏳ Pending | Est. 6 hours | - |
| **Phase 5: Cleanup** | ⏳ Pending | Est. 2 hours | - |

---

## Detailed Progress

### ✅ Phase 1: Preparation (COMPLETE)

#### Dependencies Added
```txt
sqlalchemy[asyncio]==2.0.36
alembic==1.14.0
greenlet==3.1.1
asyncpg==0.31.0  # Kept as SQLAlchemy driver
pgvector==0.4.2  # Kept for vector operations
```

**Commit:** `d7e0458` - "Add SQLAlchemy foundation: models, repositories, and session"

#### SQLAlchemy Models Created
- ✅ `packages/backend-core/app/db/models.py` (298 lines)
  - Book model with ARRAY types, JSONB, UUID
  - Page model with Vector(768) for embeddings
  - Chunk model with Vector(768) and unique constraint
  - User model with OAuth fields
  - RefreshToken model with foreign key
  - Job model with JSONB metadata

**Key Features:**
- Full type hints using `Mapped[]` syntax (SQLAlchemy 2.0)
- pgvector integration via `Vector(768)`
- Preserved all existing columns and constraints
- DateTime with timezone support

#### Session Management
- ✅ `packages/backend-core/app/db/session.py` (111 lines)
  - Async engine with connection pooling (pool_size=10)
  - Session factory with error handling
  - `get_session()` dependency for FastAPI
  - `init_db()` and `close_db()` lifecycle functions

#### Alembic Setup
- ⏳ **NOT YET DONE** - Deferred to Phase 5 (not blocking)

---

### ✅ Phase 2: Core Implementation (COMPLETE)

#### Repository Layer
All repositories implement base CRUD + domain-specific operations:

- ✅ `packages/backend-core/app/db/repositories/base.py` (89 lines)
  - Generic BaseRepository[T] with type safety
  - Methods: get, get_all, create, update_one, delete_one, count, exists

- ✅ `packages/backend-core/app/db/repositories/books.py` (139 lines)
  - `find_by_hash()` - duplicate detection
  - `find_many()` - filtering by status, visibility, categories, search
  - `get_with_page_stats()` - aggregated page statistics
  - `count_by_status()` / `count_by_visibility()`

- ✅ `packages/backend-core/app/db/repositories/pages.py` (146 lines)
  - `find_by_book()` - all pages for a book
  - `find_one()` - specific page by book + page number
  - **`upsert()`** - PostgreSQL INSERT...ON CONFLICT (critical for OCR)
  - `update_status()` / `update_many_status()`
  - `delete_by_book()` / `count_by_book()`

- ✅ `packages/backend-core/app/db/repositories/chunks.py` (159 lines)
  - **`similarity_search()`** - pgvector cosine distance (CRITICAL for RAG)
  - `upsert_many()` - batch chunk insertion with conflict resolution
  - `delete_by_book()` / `delete_by_page()`
  - `find_by_book()`

- ✅ `packages/backend-core/app/db/repositories/users.py` (109 lines)
  - `find_by_email()` - user lookup
  - `find_by_provider()` - OAuth integration
  - `update_last_login()`
  - RefreshTokensRepository for JWT management

**Commit:** `d7e0458` (included in foundation commit)

#### Pydantic Schema Updates
- ✅ `packages/backend-core/app/models/schemas.py` (modified)
  - Added `to_camel()` helper function
  - Updated all models with `ConfigDict`:
    ```python
    model_config = ConfigDict(
        alias_generator=to_camel,      # Auto: content_hash → contentHash
        populate_by_name=True,          # Accept both formats
        from_attributes=True            # Enable from SQLAlchemy models
    )
    ```
  - **This eliminates ~200 lines of manual conversion code!**

**Commit:** `f80a0ea` - "Update Pydantic schemas and main.py for SQLAlchemy"

#### FastAPI Integration
- ✅ `packages/backend-core/app/main.py` (modified)
  - Updated lifespan to initialize SQLAlchemy:
    ```python
    await init_db()  # SQLAlchemy
    await db_manager.connect_to_storage()  # Keep temporarily
    ```
  - Both systems running in parallel during migration

**Commit:** `f80a0ea` (same as Pydantic updates)

#### Testing
- ✅ `packages/backend-core/tests/test_sqlalchemy_setup.py` (114 lines)
  - Database connection test
  - PostgreSQL version check
  - pgvector extension verification
  - Repository instantiation tests
  - Model existence tests

**Commit:** `f80a0ea` (same as Pydantic updates)

---

## ⏳ Phase 3: Endpoint Migration (PENDING)

**Status:** Not started
**Estimated Duration:** 8 hours
**Next Task:** Migrate books endpoints

### Planned Migration Order

1. **Books Endpoints** (`app/api/endpoints/books.py`) - 12 endpoints
   - [ ] GET `/api/books` - List books
   - [ ] GET `/api/books/{id}` - Get single book
   - [ ] POST `/api/books/upload` - Upload PDF
   - [ ] PATCH `/api/books/{id}` - Update book
   - [ ] DELETE `/api/books/{id}` - Delete book
   - [ ] POST `/api/books/{id}/ocr/start` - Start OCR
   - [ ] GET `/api/books/{id}/pages` - Get pages
   - [ ] PATCH `/api/books/{id}/pages/{page_num}` - Update page
   - [ ] All other book endpoints

2. **Users Endpoints** (`app/api/endpoints/users.py`) - 4 endpoints
   - [ ] GET `/api/users` - List users
   - [ ] GET `/api/users/{id}` - Get user
   - [ ] PATCH `/api/users/{id}` - Update user
   - [ ] DELETE `/api/users/{id}` - Delete user

3. **Auth Endpoints** (`app/api/endpoints/auth.py`) - 3 endpoints
   - [ ] POST `/api/auth/google` - OAuth login
   - [ ] POST `/api/auth/refresh` - Refresh token
   - [ ] GET `/api/auth/me` - Current user

4. **Chat Endpoint** (`app/api/endpoints/chat.py`) - 1 endpoint
   - [ ] POST `/api/chat` - RAG chat

### Migration Pattern

**Before:**
```python
db = pg_db
book = await db.books.find_one({"id": book_id})
```

**After:**
```python
from app.db.session import get_session
from app.db.repositories.books import BooksRepository

async def get_book(
    book_id: str,
    session: AsyncSession = Depends(get_session)
):
    repo = BooksRepository(session)
    book = await repo.get(UUID(book_id))
    await session.commit()
    return BookResponse.model_validate(book)  # Auto camelCase
```

---

## ⏳ Phase 4: Service Layer Migration (PENDING)

**Status:** Not started
**Estimated Duration:** 6 hours

### Services to Update

1. **PDF Service** (`app/services/pdf_service.py`)
   - [ ] Replace all `pg_db` calls with repository methods
   - [ ] Update OCR task functions
   - [ ] Test end-to-end PDF processing

2. **RAG Service** (`app/services/rag_service.py`)
   - [ ] Update chunk retrieval to use ChunksRepository
   - [ ] Verify vector similarity search works
   - [ ] Test with real embeddings

3. **User Service** (`app/services/user_service.py`)
   - [ ] Update user CRUD operations
   - [ ] Update OAuth provider lookups

4. **Token Service** (`app/services/token_service.py`)
   - [ ] Update refresh token operations

---

## ⏳ Phase 5: Cleanup (PENDING)

**Status:** Not started
**Estimated Duration:** 2 hours

### Files to Delete
- [ ] `packages/backend-core/app/db/postgres_helpers.py` (464 lines)
- [ ] `packages/backend-core/app/db/postgres_adapter.py` (272 lines)
- [ ] `packages/backend-core/app/db/mongodb.py` (80 lines)

**Expected Net Code Reduction:** ~500-600 lines

### Alembic Setup (Deferred from Phase 1)
- [ ] Initialize Alembic: `alembic init alembic`
- [ ] Configure `alembic/env.py` for async
- [ ] Generate baseline migration
- [ ] Test migration up/down

### Documentation Updates
- [ ] Update `README.md`
- [ ] Update `AGENTS.md`
- [ ] Update `SYSTEM_DESIGN.md`
- [ ] Add migration notes for future reference

---

## Code Statistics

### Current State (After Phase 2)

**New Code Added:**
- `app/db/models.py` - 298 lines
- `app/db/session.py` - 111 lines
- `app/db/repositories/base.py` - 89 lines
- `app/db/repositories/books.py` - 139 lines
- `app/db/repositories/pages.py` - 146 lines
- `app/db/repositories/chunks.py` - 159 lines
- `app/db/repositories/users.py` - 109 lines
- `tests/test_sqlalchemy_setup.py` - 114 lines
- **Total New:** ~1,165 lines

**Modified:**
- `app/models/schemas.py` - Added ConfigDict to all models
- `app/main.py` - Added SQLAlchemy initialization

**To Be Deleted (Phase 5):**
- `app/db/postgres_helpers.py` - 464 lines
- `app/db/postgres_adapter.py` - 272 lines
- `app/db/mongodb.py` - 80 lines
- **Total Removed:** ~816 lines

**Net Impact:** ~350 lines added (but with ORM benefits and no manual case conversion)

---

## Testing Status

### Completed Tests
- ✅ Database connection
- ✅ PostgreSQL version check
- ✅ pgvector extension verification
- ✅ Repository instantiation
- ✅ Model definitions

### Pending Tests
- [ ] End-to-end OCR pipeline
- [ ] RAG chat functionality
- [ ] User authentication flow
- [ ] Vector similarity search with real data
- [ ] Performance benchmarks (before/after)

---

## Git History

### Commits on `kitabim-db-migration` branch

1. **d7e0458** - "Add SQLAlchemy foundation: models, repositories, and session"
   - Added all SQLAlchemy models
   - Created complete repository layer
   - Set up session management
   - Updated dependencies

2. **f80a0ea** - "Update Pydantic schemas and main.py for SQLAlchemy"
   - Added automatic camelCase conversion via alias_generator
   - Initialized SQLAlchemy in app lifespan
   - Created connection tests

---

## Risks & Mitigation

| Risk | Status | Mitigation |
|------|--------|------------|
| Breaking API contracts | ✅ Mitigated | Pydantic alias_generator preserves camelCase responses |
| pgvector compatibility | ✅ Verified | Vector(768) type working in models, raw SQL in similarity_search() |
| Performance issues | ⚠️ Untested | Need to benchmark after endpoint migration |
| Transaction handling | ⚠️ Partial | Session management in place, need to verify in endpoints |

---

## Next Actions (Priority Order)

1. **Start Phase 3:** Migrate books endpoints to SQLAlchemy repositories
2. **Test OCR pipeline:** Verify page upsert and chunk insertion works
3. **Test RAG chat:** Verify vector similarity search returns correct results
4. **Continue migration:** Users, auth, chat endpoints
5. **Service layer:** Update pdf_service, rag_service, user_service
6. **Cleanup:** Delete old files, set up Alembic

---

## Questions & Notes

### Design Decisions Made

1. **Dual Database Mode:** Running both asyncpg (old) and SQLAlchemy (new) in parallel during migration
   - Allows gradual, safe migration
   - Can test endpoints one-by-one
   - Easy rollback if issues found

2. **Raw SQL for pgvector:** Using `text()` queries in `similarity_search()`
   - SQLAlchemy 2.0 doesn't have native pgvector operators yet
   - Raw SQL gives optimal performance
   - Encapsulated in repository, not exposed to endpoints

3. **Repository Pattern:** Strict separation of concerns
   - Endpoints use repositories, never raw SQL
   - Repositories encapsulate all database logic
   - Easy to test and mock

4. **Pydantic Integration:** `alias_generator` instead of manual conversion
   - Eliminates ~200 lines of conversion code
   - Automatic in both directions (request/response)
   - Type-safe and validated

### Open Questions

- [ ] Should we add database connection pooling metrics?
- [ ] Do we need separate read/write connections?
- [ ] Should repositories return Pydantic models or SQLAlchemy models?
  - **Current approach:** Return SQLAlchemy models, convert in endpoints

---

**Migration continues...**
