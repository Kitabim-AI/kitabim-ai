# API Developer Skill — Kitabim AI Backend

You are implementing backend features for the kitabim-ai FastAPI service. This skill covers the day-to-day developer workflow: running the stack, writing services and repositories, implementing worker jobs, writing tests, and running migrations.

---

## Local Dev Environment

**Rebuild and restart a service:**
```bash
./deploy/local/rebuild-and-restart.sh backend   # API server only
./deploy/local/rebuild-and-restart.sh worker    # Worker only
./deploy/local/rebuild-and-restart.sh frontend  # Frontend only
./deploy/local/rebuild-and-restart.sh all       # Full stack (regenerates App ID)
```

**Ports:**
- Frontend: http://localhost:30080
- Backend API: http://localhost:30800
- Backend container internal port: 8000

**Tail logs:**
```bash
docker compose logs -f backend
docker compose logs -f worker
```

**All backend code changes require a rebuild** — there is no hot-reload in Docker mode.

---

## Package Layout (what goes where)

| Code type | Location |
|-----------|----------|
| Route handlers | `services/backend/api/endpoints/<domain>.py` |
| Auth dependencies | `services/backend/auth/dependencies.py` |
| Worker jobs | `services/worker/jobs/<name>_job.py` |
| Business logic / services | `packages/backend-core/app/services/<name>_service.py` |
| DB repositories (CRUD) | `packages/backend-core/app/db/repositories/<name>.py` |
| ORM models | `packages/backend-core/app/db/models.py` |
| Pydantic schemas | `packages/backend-core/app/models/schemas.py` |
| Config settings | `packages/backend-core/app/core/config.py` |
| Cache key constants | `packages/backend-core/app/core/cache_config.py` |
| i18n translations | `services/backend/locales/<lang>.json` |
| SQL migrations | `packages/backend-core/migrations/NNN_description.sql` |

The rule: **endpoints call services, services call repositories, repositories call the DB**. Never put raw SQL or `session.execute()` in an endpoint or service file.

---

## Repository Pattern

All DB access goes through a repository. Repositories live in `packages/backend-core/app/db/repositories/`.

**Base repository** (`repositories/base.py`) provides generic async CRUD — extend it or use it directly:

```python
from app.db.repositories.base import BaseRepository
from app.db.models import MyModel

class MyRepository(BaseRepository[MyModel]):
    # Inherits: get, get_all, create, update_one, delete_one, count, exists

    async def find_by_name(self, session: AsyncSession, name: str) -> MyModel | None:
        result = await session.execute(
            select(MyModel).where(MyModel.name == name)
        )
        return result.scalar_one_or_none()

    async def find_many(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        q: str | None = None,
    ) -> tuple[list[MyModel], int]:
        stmt = select(MyModel)
        if q:
            stmt = stmt.where(MyModel.name.ilike(f"%{q}%"))
        count_result = await session.execute(select(func.count()).select_from(stmt.subquery()))
        total = count_result.scalar_one()
        stmt = stmt.order_by(MyModel.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(stmt)
        return result.scalars().all(), total
```

**Bulk upsert pattern** (used in `chunks.py`):
```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def bulk_upsert(self, session: AsyncSession, records: list[dict]) -> None:
    if not records:
        return
    stmt = pg_insert(MyModel).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={"value": stmt.excluded.value, "last_updated": func.now()},
    )
    await session.execute(stmt)
    await session.commit()
```

**Vector similarity search** (used in `chunks.py` via pgvector):
```python
from pgvector.sqlalchemy import Vector

# In repository:
async def similarity_search(
    self, session: AsyncSession, embedding: list[float], book_id: str, top_k: int = 16
) -> list[Chunk]:
    result = await session.execute(
        select(Chunk)
        .where(Chunk.book_id == book_id)
        .order_by(Chunk.embedding.cosine_distance(embedding))
        .limit(top_k)
    )
    return result.scalars().all()
```

---

## Service Layer

Services contain business logic that doesn't belong in a route or repository. They live in `packages/backend-core/app/services/`.

**Service conventions:**
- Async functions — no class required unless stateful (see `CacheService`)
- Accept `AsyncSession` as a parameter — never create their own sessions
- No FastAPI imports — services are framework-agnostic
- Raise plain `Exception` or domain-specific exceptions — let the endpoint translate to `HTTPException`

**Cache service** (`services/cache_service.py`):

```python
from app.services.cache_service import cache_service
from app.core import cache_config

# Get (returns None on miss or Redis failure)
raw = await cache_service.get(cache_config.KEY_MY_ITEM.format(id=item_id))
if raw:
    return MySchema.model_validate(raw)

# Set (always serialize with mode='json' — handles datetime, Enum, UUID)
await cache_service.set(
    cache_config.KEY_MY_ITEM.format(id=item_id),
    item.model_dump(mode='json'),
    ttl=settings.cache_ttl_my_item,   # add to config.py
)

# Delete single key
await cache_service.delete(cache_config.KEY_MY_ITEM.format(id=item_id))

# Delete by pattern (invalidate list caches)
await cache_service.delete_pattern(f"{cache_config.KEY_MY_LIST}*")
```

The cache service has a built-in circuit breaker — Redis failures are swallowed and logged, never raised to callers.

**Storage service** (`services/storage_service.py`):

```python
from app.services.storage_service import storage_service

# Upload (works for both local filesystem and GCS)
await storage_service.upload_file(
    local_path=Path("/tmp/file.pdf"),
    destination="books/my-book-id/file.pdf",
    bucket="data",   # "data" or "media"
)

# Download to local path
await storage_service.download_file(
    source="books/my-book-id/file.pdf",
    local_path=Path("/tmp/file.pdf"),
    bucket="data",
)

# Public URL
url = storage_service.get_public_url("covers/my-book-id.jpg", bucket="media")

# Signed URL (for private content)
url = await storage_service.get_signed_url("books/my-book-id/file.pdf", bucket="data")
```

**User service** (`services/user_service.py`) — key functions:
```python
from app.services.user_service import (
    get_user_by_id,
    get_user_by_email,
    get_user_by_provider,
    create_user,
    update_user_role,
    list_users,
)
```

---

## Database Session Rules

**In endpoints** — use `get_session` dependency (auto-commits on success, auto-rolls back on error):
```python
async def my_endpoint(session: AsyncSession = Depends(get_session)):
    ...
    await session.commit()   # explicit commit after writes
    await session.refresh(obj)
```

**In worker jobs** — create an isolated session per page/item (do NOT share one session across all pages):
```python
from app.db.session import async_session_factory

async def process_page(page_id: str) -> None:
    async with async_session_factory() as session:
        try:
            page = await session.get(Page, page_id)
            # ... do work ...
            page.status = "done"
            await session.commit()
        except Exception as e:
            await session.rollback()
            # record error, don't re-raise — let other pages continue
```

**Never** share an `AsyncSession` across concurrent tasks — one session per coroutine.

---

## Worker Jobs (arq)

Worker jobs live in `services/worker/jobs/`. Each job is an async function registered in `services/worker/worker.py`.

**Job anatomy:**
```python
# services/worker/jobs/my_job.py

import logging
from app.db.session import async_session_factory
from app.db.models import MyModel
from app.utils.observability import log_json

logger = logging.getLogger(__name__)

async def my_job(ctx: dict, item_id: str) -> None:
    """Process a single item. Called by arq worker."""
    log_json(logger, logging.INFO, "Job started", item_id=item_id)

    async with async_session_factory() as session:
        item = await session.get(MyModel, item_id)
        if not item:
            log_json(logger, logging.WARNING, "Item not found", item_id=item_id)
            return

        try:
            # Mark as in-progress
            item.status = "processing"
            await session.commit()

            # Do the work
            result = await do_heavy_work(item)

            # Mark as done
            item.status = "done"
            item.result = result
            await session.commit()

        except Exception as e:
            await session.rollback()
            item.status = "error"
            item.last_error = str(e)
            item.retry_count = (item.retry_count or 0) + 1
            await session.commit()
            log_json(logger, logging.ERROR, "Job failed", item_id=item_id, error=str(e))
```

**Register the job in `worker.py`:**
```python
# services/worker/worker.py
from jobs.my_job import my_job

class WorkerSettings:
    functions = [
        ...,
        my_job,
    ]
```

**Enqueue from an endpoint:**
```python
from arq.connections import RedisSettings, create_pool

async def enqueue_my_job(item_id: str) -> None:
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await redis.enqueue_job("my_job", item_id)
    await redis.close()
```

**Concurrency control with semaphore** (pattern from `ocr_job.py`):
```python
import asyncio

MAX_CONCURRENT = 4
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

async def process_all_pages(page_ids: list[str]) -> None:
    async def bounded(page_id: str):
        async with semaphore:
            await process_page(page_id)

    await asyncio.gather(*[bounded(pid) for pid in page_ids])
```

---

## Pipeline State Machine

Books and pages progress through a pipeline. Constants are in `app/core/pipeline.py`:

```python
from app.core.pipeline import PIPELINE_STEP

PIPELINE_STEP.OCR           # "ocr"
PIPELINE_STEP.CHUNKING      # "chunking"
PIPELINE_STEP.EMBEDDING     # "embedding"
PIPELINE_STEP.SPELL_CHECK   # "spell_check"
PIPELINE_STEP.READY         # "ready"
PIPELINE_STEP.ERROR         # "error"
```

**Book milestone pattern** — each processing step updates the book's milestone field to track aggregate progress. After updating pages, call `book_milestone_service` to recompute:

```python
from app.services.book_milestone_service import update_book_milestone

await update_book_milestone(session, book_id, PIPELINE_STEP.OCR)
```

**Error recording** (`utils/errors.py`):
```python
from app.utils.errors import record_book_error

await record_book_error(session, book_id, "OCR failed on page 3: timeout")
```

---

## Database Migrations

Migrations are plain SQL files in `packages/backend-core/migrations/`. No Alembic — use the naming convention:

```
NNN_short_description.sql
```
e.g. `035_add_retry_count_to_pages.sql`

**Rules:**
- Number sequentially from the highest existing file
- One logical change per file
- Include a rollback comment at the top if the change is reversible
- Test locally before pushing

**Apply a migration locally:**
```bash
# Connect to the running Postgres container and run the file
docker exec -i $(docker compose ps -q postgres) \
  psql -U postgres kitabim < packages/backend-core/migrations/035_my_change.sql
```

**After adding a column to the DB**, update:
1. The SQLAlchemy model in `models.py`
2. Any affected Pydantic schemas in `schemas.py`
3. Any repository queries that need the new field

---

## Testing

Tests live in `services/backend/tests/`. Run with:
```bash
cd services/backend && python -m pytest
```

**Test file conventions:**
- `tests/api/endpoints/test_<domain>.py` — endpoint tests
- `tests/auth/test_<module>.py` — auth tests

**Async test pattern** (use `pytest-asyncio`):
```python
import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.mark.asyncio
async def test_my_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/my-feature/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
```

**Auth in tests** — override the dependency:
```python
from auth.dependencies import get_current_user
from app.models.user import User, UserRole

def override_user(role: UserRole = UserRole.ADMIN):
    async def _user():
        return User(id="test-user", role=role, email="test@example.com", is_active=True)
    return _user

@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    app.dependency_overrides[get_current_user] = override_user(UserRole.ADMIN)
    yield
    app.dependency_overrides.clear()
```

**DB in tests** — use an in-memory SQLite or a test Postgres; mock the `get_session` dependency for unit tests:
```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_service_logic():
    mock_session = AsyncMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = MyModel(id="1")
    result = await my_service_function(mock_session, item_id="1")
    assert result is not None
```

**Mocking external services** (Gemini, GCS, Redis):
```python
from unittest.mock import patch, AsyncMock

@patch("app.services.cache_service.cache_service.get", new_callable=AsyncMock, return_value=None)
@patch("app.services.cache_service.cache_service.set", new_callable=AsyncMock)
async def test_with_cache_miss(mock_set, mock_get):
    ...
```

---

## Logging & Observability

Always use `log_json` — never `print()` or bare `logger.info("string")`:

```python
import logging
from app.utils.observability import log_json

logger = logging.getLogger(__name__)

# Info
log_json(logger, logging.INFO, "Book processing started",
         book_id=book.id, total_pages=book.total_pages)

# Warning
log_json(logger, logging.WARNING, "Cache miss on user profile",
         user_id=user_id, key=cache_key)

# Error (include the exception string)
log_json(logger, logging.ERROR, "Embedding failed",
         page_id=page_id, error=str(e), retry_count=page.retry_count)
```

`request_id_var` is automatically injected into every log line from the request context — no manual effort needed in endpoints.

---

## Config & Settings

Settings are a frozen `@dataclass` singleton. Access via:

```python
from app.core.config import settings

settings.database_url
settings.gemini_api_key
settings.cache_ttl_books
settings.rag_top_k
```

To add a new setting:
1. Add the field to the `Settings` dataclass in `core/config.py`
2. Add the corresponding env var to `.env` (and `deploy/local/.env.example` if it exists)
3. Access via `settings.my_new_setting` — never `os.environ.get()` directly in application code

---

## i18n in Error Messages

All user-facing error messages must be translated:

```python
from app.core.i18n import t

raise HTTPException(404, detail=t("errors.book_not_found"))
raise HTTPException(400, detail=t("errors.invalid_file_type"))
```

Add new keys to `services/backend/locales/ug.json` and `services/backend/locales/en.json`.

The request language is set per-request by the `add_language_header` middleware — `t()` reads it automatically from a `ContextVar`.

---

## Common Mistakes to Avoid

| Mistake | Correct approach |
|---------|-----------------|
| `session.execute()` in an endpoint file | Extract to a repository method |
| Business logic inside a route handler | Extract to a service function |
| One `AsyncSession` shared across all pages in a job | New `async with async_session_factory()` per page |
| `os.environ.get("MY_KEY")` in application code | `settings.my_key` from `core/config.py` |
| `logger.info("message")` bare string | `log_json(logger, logging.INFO, "message", key=value)` |
| Hardcoded error strings | `t("errors.key")` from `app.core.i18n` |
| Raw `fetch` / `httpx` for internal calls | Services call each other in-process, not over HTTP |
| Forgetting cache invalidation after a write | Always `await cache_service.delete(key)` after commit |
| `model_dump()` for cache storage | Use `model_dump(mode='json')` to serialise `datetime` / `Enum` |
| Adding a DB column without a migration file | Always add a `.sql` file in `migrations/` first |

---

## Workflow

1. **Migration first** — if the feature needs a new table or column, write the `.sql` file and apply it before writing any Python code.
2. **Update ORM model** — add the `Mapped` field to `models.py`.
3. **Write/extend repository** — add query methods to the relevant repository class; never write raw queries outside `repositories/`.
4. **Write service** — add business logic to `services/`; accept `AsyncSession`, call the repository.
5. **Write endpoint** — call the service, use dependency injection for session and auth, return a Pydantic response model.
6. **Add cache keys** — register new key templates in `cache_config.py` and TTLs in `config.py`.
7. **Worker job (if async)** — add a job file, register it in `worker.py`, enqueue from the endpoint.
8. **Write tests** — at minimum, test the happy path and the 404 case for each endpoint.
9. **Rebuild** — `./deploy/local/rebuild-and-restart.sh backend` (and `worker` if you added a job).
