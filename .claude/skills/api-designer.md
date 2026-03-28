# API Designer Skill — Kitabim AI Backend

You are designing and implementing backend API features for the kitabim-ai FastAPI service. Your job is to add endpoints, schemas, services, and DB models that are correct, secure, and consistent with the existing codebase.

---

## Stack

| Layer | Tech |
|-------|------|
| Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 async (`asyncpg` driver) |
| Validation | Pydantic v2 |
| Auth | JWT Bearer + OAuth (Google / Facebook / Twitter) |
| Cache | Redis via `cache_service` |
| Queue | Redis-backed background jobs (worker service) |
| DB | PostgreSQL |
| Config | Frozen `@dataclass` singleton in `core/config.py` |
| i18n | Per-request `ContextVar` via `app.core.i18n` |
| Observability | Structured JSON logs with `X-Request-ID` correlation |

---

## Directory Layout

```
services/backend/
  main.py                        # App factory, lifespan, middleware, router registration
  api/endpoints/                 # Route handlers (one file per domain)
  auth/
    dependencies.py              # get_current_user, require_role, require_admin, require_editor, require_reader
    jwt_handler.py
    oauth_providers.py
    providers/                   # Google, Facebook, Twitter

packages/backend-core/app/
  core/
    config.py                    # Settings dataclass — import `settings`
    cache_config.py              # Cache key constants
    pipeline.py                  # PIPELINE_STEP constants
    i18n.py                      # t(), set_current_lang()
  db/
    models.py                    # SQLAlchemy ORM models
    session.py                   # get_session() dependency, init_db()
    repositories/                # Thin CRUD wrappers (optional)
  models/
    user.py                      # User, UserPublic, UserRole
    schemas.py                   # Pydantic request/response schemas (camelCase)
  services/                      # Business logic (no FastAPI deps)
  langchain/models.py            # LLM / embeddings
  utils/observability.py         # log_json(), request_id_var
```

---

## Endpoint Anatomy

Every endpoint file lives in `services/backend/api/endpoints/`. Register the router in `main.py`.

```python
# services/backend/api/endpoints/my_feature.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_session
from app.db.models import MyModel
from app.models.schemas import MyResponse, MyCreate, MyUpdate
from app.models.user import User
from app.services.cache_service import cache_service
from app.core import cache_config
from app.core.i18n import t
from auth.dependencies import require_admin, require_editor, get_current_user_optional

router = APIRouter()
```

### GET list (paginated)
```python
@router.get("/", response_model=list[MyResponse])
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None),
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(MyModel).order_by(MyModel.created_at.desc())
    if q:
        stmt = stmt.where(MyModel.name.ilike(f"%{q}%"))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(stmt)
    items = result.scalars().all()
    return [MyResponse.model_validate(item) for item in items]
```

### GET single
```python
@router.get("/{item_id}", response_model=MyResponse)
async def get_item(
    item_id: str,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(MyModel).where(MyModel.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, detail=t("errors.not_found"))
    return MyResponse.model_validate(item)
```

### POST create
```python
@router.post("/", response_model=MyResponse, status_code=201)
async def create_item(
    body: MyCreate,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    item = MyModel(**body.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    await cache_service.delete(cache_config.KEY_MY_LIST)
    return MyResponse.model_validate(item)
```

### PATCH / PUT update
```python
@router.patch("/{item_id}", response_model=MyResponse)
async def update_item(
    item_id: str,
    body: MyUpdate,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(MyModel).where(MyModel.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, detail=t("errors.not_found"))
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    await session.commit()
    await session.refresh(item)
    await cache_service.delete(cache_config.KEY_MY_ITEM.format(item_id=item_id))
    return MyResponse.model_validate(item)
```

### DELETE
```python
@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(MyModel).where(MyModel.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, detail=t("errors.not_found"))
    await session.delete(item)
    await session.commit()
    await cache_service.delete(cache_config.KEY_MY_ITEM.format(item_id=item_id))
```

---

## Authentication & Authorization

Import from `auth.dependencies` (in `services/backend/auth/`):

```python
from auth.dependencies import (
    get_current_user,           # Required auth — raises 401 if missing
    get_current_user_optional,  # Optional auth — returns None for guests
    require_admin,              # role == ADMIN
    require_editor,             # role in (ADMIN, EDITOR)
    require_reader,             # any authenticated role
)
```

Role hierarchy: `ADMIN > EDITOR > READER`

For custom role checks:
```python
from auth.dependencies import require_role
from app.models.user import UserRole

require_my_role = require_role(UserRole.ADMIN, UserRole.EDITOR)
```

**Never skip auth** on endpoints that touch user data, write state, or trigger processing.

---

## Pydantic Schemas

All schemas live in `packages/backend-core/app/models/schemas.py`.

**Always use the camelCase config** — the frontend receives camelCase, sends camelCase:

```python
from pydantic import BaseModel, ConfigDict

def to_camel(string: str) -> str:
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

class MyResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,   # content_hash → contentHash
        populate_by_name=True,      # accept both forms
        from_attributes=True,       # works with SQLAlchemy models
    )

    id: str
    content_hash: str              # serialised as "contentHash"
    total_pages: int               # serialised as "totalPages"
    created_at: datetime           # serialised as "createdAt"

class MyCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    content_hash: str
    total_pages: int

class MyUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    total_pages: Optional[int] = None   # all fields Optional for partial update
```

Use `model_dump(exclude_unset=True)` on update bodies — never overwrite with `None`.

---

## SQLAlchemy Models

All models in `packages/backend-core/app/db/models.py`. Use SQLAlchemy 2.0 `Mapped` annotations:

```python
from sqlalchemy import String, Integer, DateTime, func, CheckConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.models import Base  # declarative base

class MyModel(Base):
    __tablename__ = "my_table"
    __table_args__ = (
        CheckConstraint("status IN ('active','inactive')", name="ck_my_table_status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Nullable foreign key
    book_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("books.id", ondelete="CASCADE"), nullable=True
    )
    book: Mapped[Optional["Book"]] = relationship(back_populates="my_items")
```

Always add `CheckConstraint` for enum-like string columns.

---

## Caching

```python
from app.services.cache_service import cache_service
from app.core import cache_config

# Read-through
cache_key = cache_config.KEY_MY_ITEM.format(item_id=item_id)
cached = await cache_service.get(cache_key)
if cached:
    return MyResponse.model_validate(cached)

item = await fetch_from_db(...)
await cache_service.set(cache_key, item.model_dump(mode='json'), ttl=settings.cache_ttl_my_item)

# Invalidate on write
await cache_service.delete(cache_key)
```

Add new cache key templates to `app/core/cache_config.py` and TTL settings to `core/config.py`.

**Rules:**
- Always invalidate on create / update / delete.
- Never cache admin-only queries unless intentional.
- Use `model_dump(mode='json')` to serialise (handles `datetime`, `Enum`, etc.).

---

## Error Handling

```python
from app.core.i18n import t

# 400 Bad Request
raise HTTPException(400, detail=t("errors.invalid_input"))

# 401 Unauthorized (auth deps raise this automatically)
raise HTTPException(401, detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"})

# 403 Forbidden
raise HTTPException(403, detail=t("errors.insufficient_permissions"))

# 404 Not Found
raise HTTPException(404, detail=t("errors.not_found"))

# 409 Conflict
raise HTTPException(409, detail=t("errors.already_exists"))

# 429 Rate Limited
raise HTTPException(429, detail=t("errors.limit_reached"))
```

Always use `t()` for user-facing messages. Use English string literals only for internal/log messages.

---

## Logging & Observability

```python
import logging
from app.utils.observability import log_json

logger = logging.getLogger(__name__)

# Structured log — request_id is injected automatically
log_json(logger, logging.INFO, "Book created",
         book_id=book.id, user_id=current_user.id)

log_json(logger, logging.WARNING, "Cache miss", key=cache_key)

log_json(logger, logging.ERROR, "DB write failed", error=str(e))
```

Never use `print()`. Never log secrets, tokens, or full request bodies.

---

## Streaming (SSE)

For long-running operations (e.g. chat, processing status):

```python
from fastapi.responses import StreamingResponse
import json

@router.post("/stream")
async def my_stream(req: MyRequest, current_user: User = Depends(require_reader)):
    async def event_generator():
        try:
            async for chunk in my_service.stream(req):
                yield f'data: {json.dumps({"chunk": chunk})}\n\n'
            yield f'data: {json.dumps({"done": True})}\n\n'
        except Exception as exc:
            yield f'data: {json.dumps({"error": str(exc)})}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## Background Jobs

Enqueue via the Redis worker queue (do not run heavy processing in the request cycle):

```python
from fastapi import BackgroundTasks

@router.post("/", response_model=BookResponse)
async def create_book(
    ...,
    background_tasks: BackgroundTasks,
):
    book = await create_book_in_db(...)
    background_tasks.add_task(enqueue_processing_job, book.id)
    return BookResponse.model_validate(book)
```

---

## Registering a New Router

In `services/backend/main.py`:

```python
from api.endpoints import my_feature

app.include_router(
    my_feature.router,
    prefix="/api/my-feature",
    tags=["my-feature"],
)
```

---

## Workflow

1. **Schema first** — define request/response Pydantic models in `schemas.py` before writing the endpoint.
2. **DB model second** — add the SQLAlchemy model with constraints; create a migration if needed.
3. **Service layer for business logic** — if the logic is more than a single DB query, extract it to `app/services/`.
4. **Endpoint last** — wire dependency injection, call the service, return the response model.
5. **Cache keys in `cache_config.py`** — never hardcode cache key strings in endpoint files.
6. **Always invalidate** — any write operation must delete relevant cache keys.
7. **i18n all error messages** — add keys to `services/backend/locales/`.
8. **Protect every write route** — minimum `require_editor`; destructive ops require `require_admin`.
9. **Read existing endpoints** before adding a new one — check for patterns already in use in that domain (e.g. `books.py` before adding a book sub-resource).
