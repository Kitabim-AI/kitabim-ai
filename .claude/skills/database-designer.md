# Database Designer Skill — Kitabim AI

You are designing database schemas, migrations, and query patterns for the kitabim-ai PostgreSQL database. All models are SQLAlchemy 2.0 async with `pgvector` for embeddings. Every schema change ships as a plain SQL migration file.

---

## Database Overview

| Extension | Purpose |
|-----------|---------|
| `pgvector` | 768-dim embeddings on `chunks` and `book_summaries` |
| `uuid-ossp` | `uuid_generate_v4()` server-side default for user/token PKs |
| `pg_trgm` | (available) trigram indexes for fuzzy text search |

**Existing tables:**

| Table | PK type | Purpose |
|-------|---------|---------|
| `books` | `String(64)` MD5 hash | Core book records + denormalized pipeline milestones |
| `pages` | `Integer` autoincrement | Per-page OCR text + per-step milestone tracking |
| `chunks` | `Integer` autoincrement | RAG chunks with `Vector(768)` embeddings |
| `book_summaries` | `String(64)` (book FK, 1-to-1) | LLM summary + `Vector(768)` for hierarchical RAG |
| `users` | `String(36)` UUID | OAuth users with role-based access |
| `refresh_tokens` | `String(36)` UUID (jti) | JWT refresh token store |
| `user_chat_usage` | `Integer` autoincrement | Daily chat counter per user |
| `rag_evaluations` | `Integer` autoincrement | RAG query performance metrics |
| `system_configs` | `String(100)` key | Hot-reloadable key/value config |
| `pipeline_events` | `Integer` autoincrement | Transactional outbox for pipeline transitions |
| `dictionary` | `Integer` autoincrement | Uyghur spell-check word list |
| `page_spell_issues` | `Integer` autoincrement | Per-word spell-check findings |
| `auto_correct_rules` | `Integer` autoincrement | Word-level auto-correction rules |
| `proverbs` | `Integer` autoincrement | Uyghur proverbs displayed in UI |
| `contact_submissions` | `Integer` autoincrement | Join Us form submissions |

---

## ORM Model Conventions

All models go in `packages/backend-core/app/db/models.py`.

```python
from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    String, Text, Integer, Boolean, DateTime, ForeignKey,
    CheckConstraint, UniqueConstraint, func, text, ARRAY
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class MyModel(Base):
    __tablename__ = "my_table"

    # ── Primary key ──────────────────────────────────────────────────────────
    # Integer autoincrement for internal/join tables:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # UUID string for user-facing entities:
    # id: Mapped[str] = mapped_column(String(36), primary_key=True,
    #     default=lambda: str(uuid4()), server_default=text("uuid_generate_v4()"))
    # MD5 hash string for content-addressed entities (books):
    # id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # ── Required fields ──────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Optional fields ──────────────────────────────────────────────────────
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Enum-like string columns — always add CheckConstraint ────────────────
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending",
        index=True, nullable=False
    )

    # ── Booleans ─────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    # ── PostgreSQL arrays ─────────────────────────────────────────────────────
    tags: Mapped[List[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False     # ← onupdate for mutable rows
    )

    # ── Foreign key ──────────────────────────────────────────────────────────
    book_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("books.id", ondelete="CASCADE"),
        index=True, nullable=False
    )
    book: Mapped["Book"] = relationship("Book", back_populates="my_items")

    # ── Constraints ──────────────────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'done')",
            name="my_table_status_check",        # always name constraints
        ),
        UniqueConstraint("book_id", "name", name="my_table_book_id_name_key"),
    )
```

---

## Primary Key Rules

| Entity type | PK type | Reason |
|-------------|---------|--------|
| Content-addressed (books) | `String(64)` MD5 | Deduplication: same content → same ID |
| User-facing records (users, tokens) | `String(36)` UUID | Unpredictable, safe to expose in URLs |
| Internal / join tables (pages, chunks, events) | `Integer` autoincrement | Compact, fast joins, never exposed |

---

## Foreign Key `ondelete` Rules

Always specify `ondelete` — never leave it as the default `NO ACTION` when the parent could be deleted:

| Scenario | `ondelete` |
|----------|-----------|
| Child is meaningless without parent (pages → books, chunks → books) | `CASCADE` |
| Child should be retained but unlinked (rag_evaluations → users) | `SET NULL` |
| Child must not be deleted while parent exists | `RESTRICT` |

---

## Indexes

Add an index on every column that appears in a `WHERE` clause of a frequently-run query. Rules:

- **Always index** foreign keys (`book_id`, `user_id`, `page_id`)
- **Always index** status/milestone columns queried by scanners
- **Always index** `processed` boolean on outbox tables (`pipeline_events`)
- **Always index** `last_updated` on tables polled by the stale watchdog
- **Consider composite index** when two columns are always queried together (e.g. `(user_id, usage_date)` on `user_chat_usage`)
- **`pgvector` cosine index** on `Vector` columns queried with `.cosine_distance()`:

```sql
CREATE INDEX CONCURRENTLY chunks_embedding_cosine_idx
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

---

## Milestone / Status Columns

All milestone columns follow the same state machine: `idle → in_progress → succeeded / failed`.
Always pair a status column with a `CheckConstraint` and `server_default`:

```python
# Page-level milestone
ocr_milestone: Mapped[str] = mapped_column(
    String(20), default="idle", server_default="idle", nullable=False
)
# Book-level denormalized mirror (updated by BookMilestoneService)
ocr_milestone: Mapped[str] = mapped_column(
    String(20), default="idle", server_default="idle", nullable=False
)
```

**Denormalization pattern**: `Book` mirrors each step's milestone to avoid an aggregation join on every scanner query. `BookMilestoneService.update_book_milestone_for_step()` keeps them in sync. Use this pattern for any new pipeline step.

---

## Vector Columns

`pgvector` `Vector(768)` is used for semantic embeddings (Gemini `text-embedding-004`, 768 dimensions):

```python
from pgvector.sqlalchemy import Vector

embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768), nullable=True)
# Or non-nullable for tables that always have embeddings:
embedding: Mapped[List[float]] = mapped_column(Vector(768), nullable=False)
```

Always store embeddings as `nullable=True` during the pipeline (set to `None` initially, populated by the embedding job). Use `nullable=False` on summary tables where the embedding is always generated at insert time.

---

## Transactional Outbox Pattern (`pipeline_events`)

`PipelineEvent` is the outbox — write the event in the **same transaction** as the state change, never in a separate commit. The `event_dispatcher` scanner polls `processed=False` events and triggers downstream jobs:

```python
# In the same session as the milestone update:
session.add(PipelineEvent(
    page_id=page.id,
    event_type="ocr_succeeded",   # {step}_{succeeded|failed}
    payload='{"extra": "context"}',
))
await session.commit()  # both the milestone update and the event in one transaction
```

`processed` is indexed (`index=True`) — the dispatcher always filters `WHERE processed = FALSE`.

---

## system_configs Table

Hot-reloadable key/value store. No migration needed for new config entries — seed them via `packages/backend-core/app/db/seeds.py` or a one-time `INSERT`. Schema:

```
key     STRING(100) PK   — e.g. "gemini_ocr_model", "scanner_page_limit"
value   TEXT NOT NULL    — always stored as a string; cast at read time
description TEXT         — human-readable description for the admin UI
updated_at TIMESTAMPTZ  — auto-updated on write
```

Naming convention for keys: `snake_case`, prefixed by feature: `gemini_*`, `scanner_*`, `ocr_*`, `rag_*`, `maintenance_*`.

---

## Migration File Format

Every schema change ships as a numbered SQL file in `packages/backend-core/migrations/`:

```
NNN_short_description.sql
```

**File template:**

```sql
-- Migration: 035_add_retry_count_to_pages.sql
-- Description: Add retry_count column to pages for pipeline retry tracking
-- Author: <name>
-- Date: YYYY-MM-DD

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'pages' AND column_name = 'retry_count'
    ) THEN
        ALTER TABLE pages
            ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
    END IF;
END $$;

COMMIT;
```

**Rules:**
- Wrap in `BEGIN; ... COMMIT;`
- Use `IF NOT EXISTS` guards for `ADD COLUMN` and `CREATE INDEX` — makes migrations idempotent
- One logical change per file — don't bundle unrelated changes
- Name constraints explicitly: `{table}_{column(s)}_{type}` e.g. `pages_status_check`, `users_provider_provider_id_key`
- For index creation on large tables, use `CREATE INDEX CONCURRENTLY` (outside a transaction block — omit `BEGIN/COMMIT`)

**Apply locally:**
```bash
docker exec -i $(docker compose ps -q postgres) \
    psql -U postgres kitabim < packages/backend-core/migrations/035_my_change.sql
```

---

## Query Patterns

### Paginated list (with total count)
```python
from sqlalchemy import select, func

count_stmt = select(func.count()).select_from(select(MyModel).subquery())
total = (await session.execute(count_stmt)).scalar_one()

stmt = (
    select(MyModel)
    .where(MyModel.status == "active")
    .order_by(MyModel.created_at.desc())
    .offset((page - 1) * page_size)
    .limit(page_size)
)
rows = (await session.execute(stmt)).scalars().all()
```

### Bulk UPDATE (avoid per-row loops)
```python
from sqlalchemy import update

await session.execute(
    update(Page)
    .where(Page.id.in_(page_ids))
    .values(ocr_milestone="in_progress", last_updated=func.now())
)
await session.commit()
```

### Bulk upsert (ON CONFLICT)
```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = pg_insert(Chunk).values(records)
stmt = stmt.on_conflict_do_update(
    index_elements=["book_id", "page_number", "chunk_index"],
    set_={"text": stmt.excluded.text, "embedding": stmt.excluded.embedding},
)
await session.execute(stmt)
await session.commit()
```

### Atomic claim with skip-locked (scanner pattern)
```python
stmt = (
    select(Page.id, Page.book_id)
    .where(Page.ocr_milestone == "idle")
    .with_for_update(skip_locked=True)
    .limit(page_limit)
)
rows = (await session.execute(stmt)).fetchall()
```

### Vector similarity search
```python
stmt = (
    select(Chunk)
    .where(Chunk.book_id == book_id)
    .order_by(Chunk.embedding.cosine_distance(query_vector))
    .limit(top_k)
)
chunks = (await session.execute(stmt)).scalars().all()
```

---

## Workflow

1. **Write the migration file** — `NNN_description.sql` with `IF NOT EXISTS` guards and `BEGIN/COMMIT`.
2. **Apply it locally** — `docker exec ... psql ... < migration.sql`.
3. **Update the ORM model** — add the `Mapped` field with matching type, nullable, default, and constraints.
4. **Update affected repositories** — add new query methods if the column is queried.
5. **Update Pydantic schemas** — add the field to request/response models in `schemas.py`.
6. **Update stale watchdog** — if a new `*_milestone` column was added.
7. **Seed system_configs** — if new config keys were added, update `seeds.py`.
