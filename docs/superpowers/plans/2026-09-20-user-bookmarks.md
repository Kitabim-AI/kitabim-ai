# User Bookmarks & Reading Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let signed-in readers silently resume a book where they left off, and explicitly save named whole-page or passage bookmarks, surfaced via per-page icons, a per-book drawer, two new Library tabs, and profile-menu shortcuts.

**Architecture:** Two new tables (`reading_progress` upserted per user+book, `bookmarks` appended per user+book) behind a new `bookmarks_router.py` (7 auth-required endpoints). Frontend: a `useBookmarks(bookId?)` hook wraps the CRUD calls; a shared `BookmarkPrompt` popover handles both creation (name required) and rename/delete; existing per-page/`AppContext` scroll-tracking is reused to drive silent progress saves and resume.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), React + TypeScript + Vite + vitest/@testing-library/react (frontend), PostgreSQL (numbered SQL migrations with paired rollbacks).

**Spec:** `docs/superpowers/specs/2026-09-20-user-bookmarks-design.md`

## Global Constraints

- No `print()` — use `log_json(logger, level, "message", key=value)`.
- No `os.environ.get()` in application code — use `settings.*` from `core/config.py`.
- No hardcoded user-visible strings — use `t("errors.key")` (backend, `packages/backend-core/app/core/i18n.py` + `services/backend/locales/*.json`) or `t('key')` (frontend, `apps/frontend/src/i18n/I18nContext.tsx` + `apps/frontend/src/locales/*.json`).
- No raw SQL with user input — always SQLAlchemy bound parameters / the ORM.
- Migration file first, ORM model second, repository third, endpoint last.
- All new API endpoints need an auth dependency — never skip it. Every endpoint in this plan uses `Depends(require_reader)`.
- **Uyghur translations in this plan are draft, best-effort text** placed in `ug.json` so no step ships with an empty/placeholder string — per standing project guidance, machine-quality Uyghur is not acceptable for shipping. Before merging any task that touches `ug.json`, have a native speaker review and correct the added `ug.json` lines; do not treat the drafts here as final copy.

---

## File Structure

**Backend (new):**
- `packages/backend-core/migrations/095_create_reading_progress.sql` + `095_rollback_create_reading_progress.sql`
- `packages/backend-core/migrations/096_create_bookmarks.sql` + `096_rollback_create_bookmarks.sql`
- `packages/backend-core/app/db/repositories/reading_progress_repository.py`
- `packages/backend-core/app/db/repositories/bookmarks_repository.py`
- `packages/backend-core/tests/app/db/reading_progress_repository_test.py`
- `packages/backend-core/tests/app/db/bookmarks_repository_test.py`
- `services/backend/api/endpoints/bookmarks_router.py`
- `services/backend/tests/api/endpoints/bookmarks_router_test.py`

**Backend (modified):**
- `packages/backend-core/app/db/models.py` — add `ReadingProgress`, `Bookmark` ORM classes.
- `services/backend/main.py` — import + register `bookmarks_router`.
- `services/backend/locales/en.json`, `services/backend/locales/ug.json` — add `errors.bookmark_not_found`.

**Frontend (new):**
- `packages/shared/src/types.ts` — add `Bookmark`, `ReadingProgressEntry` interfaces (modified, not new file, listed here for visibility).
- `apps/frontend/src/hooks/useBookmarks.ts`
- `apps/frontend/src/tests/hooks/useBookmarks.test.tsx`
- `apps/frontend/src/components/reader/BookmarkPrompt.tsx`
- `apps/frontend/src/tests/components/reader/BookmarkPrompt.test.tsx`
- `apps/frontend/src/components/reader/BookmarksDrawer.tsx`
- `apps/frontend/src/tests/components/reader/BookmarksDrawer.test.tsx`
- `apps/frontend/src/components/library/ContinueReadingTab.tsx`
- `apps/frontend/src/tests/components/library/ContinueReadingTab.test.tsx`
- `apps/frontend/src/components/library/BookmarksTab.tsx`
- `apps/frontend/src/tests/components/library/BookmarksTab.test.tsx`

**Frontend (modified):**
- `apps/frontend/src/services/persistenceService.ts` — add progress/bookmark API methods.
- `apps/frontend/src/context/AppContext.tsx` — debounced progress-save effect; `library` sub-tab routing.
- `apps/frontend/src/hooks/useBookActions.ts` — `openReader` resumes from saved progress.
- `apps/frontend/src/components/reader/PageItem.tsx` — per-page bookmark icon + passage bookmark button.
- `apps/frontend/src/components/reader/ReaderView.tsx` — thread bookmark props, add drawer toggle.
- `apps/frontend/src/components/reader/VirtualScrollReader.tsx` — thread bookmark props to `PageItem`.
- `apps/frontend/src/components/library/LibraryView.tsx` — 3-tab layout.
- `apps/frontend/src/components/auth/AuthButton.tsx` — `UserMenu` shortcuts.
- `apps/frontend/src/tests/hooks/useBookActions.test.tsx`, `apps/frontend/src/tests/components/reader/PageItem.test.tsx`, `apps/frontend/src/tests/components/library/LibraryView.test.tsx` — extended.
- `apps/frontend/src/locales/en.json`, `apps/frontend/src/locales/ug.json` — new `bookmarks.*` namespace, `reader.*`/`library.*` additions.

---

### Task 1: Database migrations

**Files:**
- Create: `packages/backend-core/migrations/095_create_reading_progress.sql`
- Create: `packages/backend-core/migrations/095_rollback_create_reading_progress.sql`
- Create: `packages/backend-core/migrations/096_create_bookmarks.sql`
- Create: `packages/backend-core/migrations/096_rollback_create_bookmarks.sql`

**Interfaces:**
- Produces: tables `reading_progress(id, user_id, book_id, page_number, updated_at)` unique on `(user_id, book_id)`, and `bookmarks(id, user_id, book_id, page_number, name, quote_text, created_at)`. Task 2's ORM models map onto these exactly.

- [x] **Step 1: Write migration 095 (reading_progress)**

```sql
-- Migration 095: Add reading_progress table (silent per-user, per-book resume position)
CREATE TABLE IF NOT EXISTS reading_progress (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    book_id VARCHAR(64) NOT NULL REFERENCES books (id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_reading_progress_user_book UNIQUE (user_id, book_id)
);

CREATE INDEX IF NOT EXISTS idx_reading_progress_user_updated ON reading_progress (user_id, updated_at DESC);
```

- [x] **Step 2: Write rollback 095**

```sql
-- Rollback Migration 095: Drop reading_progress table
DROP TABLE IF EXISTS reading_progress;
```

- [x] **Step 3: Write migration 096 (bookmarks)**

```sql
-- Migration 096: Add bookmarks table (named whole-page or passage bookmarks)
CREATE TABLE IF NOT EXISTS bookmarks (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    book_id VARCHAR(64) NOT NULL REFERENCES books (id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    quote_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_user_book ON bookmarks (user_id, book_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks (user_id);
```

- [x] **Step 4: Write rollback 096**

```sql
-- Rollback Migration 096: Drop bookmarks table
DROP TABLE IF EXISTS bookmarks;
```

- [x] **Step 5: Apply both migrations to the local dev database**

Run (per `packages/backend-core/migrations/README.md`'s documented apply method — the same one used for every prior numbered migration in this directory):

```bash
cd /Users/Omarjan/Projects/kitabim-ai
cat packages/backend-core/migrations/095_create_reading_progress.sql | psql "$DATABASE_URL"
cat packages/backend-core/migrations/096_create_bookmarks.sql | psql "$DATABASE_URL"
```

Expected: both print `CREATE TABLE`/`CREATE INDEX` with no errors. Verify:

```bash
psql "$DATABASE_URL" -c "\d reading_progress" -c "\d bookmarks"
```

Expected: both tables listed with the columns above.

- [x] **Step 6: Commit**

```bash
git add packages/backend-core/migrations/095_create_reading_progress.sql packages/backend-core/migrations/095_rollback_create_reading_progress.sql packages/backend-core/migrations/096_create_bookmarks.sql packages/backend-core/migrations/096_rollback_create_bookmarks.sql
git commit -m "feat(db): add reading_progress and bookmarks tables"
```

---

### Task 2: ORM models and repositories

**Files:**
- Modify: `packages/backend-core/app/db/models.py`
- Create: `packages/backend-core/app/db/repositories/reading_progress_repository.py`
- Create: `packages/backend-core/app/db/repositories/bookmarks_repository.py`
- Test: `packages/backend-core/tests/app/db/reading_progress_repository_test.py`
- Test: `packages/backend-core/tests/app/db/bookmarks_repository_test.py`

**Interfaces:**
- Consumes: `BaseRepository[ModelType]` from `packages/backend-core/app/db/repositories/base_repository.py` (`__init__(self, session, model)`, inherited `get(id)`).
- Produces:
  - `ReadingProgressRepository.upsert(user_id: str, book_id: str, page_number: int) -> ReadingProgress`
  - `ReadingProgressRepository.get_for_book(user_id: str, book_id: str) -> Optional[ReadingProgress]`
  - `ReadingProgressRepository.list_recent(user_id: str, limit: int = 50) -> List[ReadingProgress]` (each row's `.book` relationship eager-loaded)
  - `BookmarksRepository.create(user_id: str, book_id: str, page_number: int, name: str, quote_text: Optional[str] = None) -> Bookmark`
  - `BookmarksRepository.list(user_id: str, book_id: Optional[str] = None) -> List[Bookmark]` (each row's `.book` relationship eager-loaded, ordered by `page_number` when `book_id` given, else `created_at DESC`)
  - `BookmarksRepository.get(bookmark_id: str, user_id: str) -> Optional[Bookmark]` (ownership-checked)
  - `BookmarksRepository.rename(bookmark_id: str, user_id: str, name: str) -> Optional[Bookmark]`
  - `BookmarksRepository.delete(bookmark_id: str, user_id: str) -> bool`

- [x] **Step 1: Add `ReadingProgress` and `Bookmark` ORM models**

Add to `packages/backend-core/app/db/models.py`, immediately after the `ConversationMessage` class (the nearest existing example of a per-user, UUID-keyed, `func.now()`-defaulted table):

```python
class ReadingProgress(Base):
    """Silent per-user, per-book resume position"""

    __tablename__ = "reading_progress"
    __table_args__ = (UniqueConstraint("user_id", "book_id", name="uq_reading_progress_user_book"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    book: Mapped["Book"] = relationship("Book", lazy="selectin")
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Bookmark(Base):
    """A user's named whole-page or passage bookmark"""

    __tablename__ = "bookmarks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book: Mapped["Book"] = relationship("Book", lazy="selectin")
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    quote_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
```

Check the top of `models.py` already imports `UniqueConstraint`; if not, add it to the existing `from sqlalchemy import (...)` block.

```bash
grep -n "^from sqlalchemy import\|UniqueConstraint" packages/backend-core/app/db/models.py | head -5
```

If `UniqueConstraint` isn't already imported, add it to that import line.

- [x] **Step 2: Write the failing repository tests**

Create `packages/backend-core/tests/app/db/reading_progress_repository_test.py`:

```python
"""Tests for ReadingProgressRepository"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.db.models import ReadingProgress
from app.db.repositories.reading_progress_repository import ReadingProgressRepository


@pytest.mark.asyncio
async def test_upsert_creates_row_when_none_exists():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res
    session.add = MagicMock()
    repo = ReadingProgressRepository(session)

    progress = await repo.upsert(user_id="u1", book_id="b1", page_number=42)

    assert progress.user_id == "u1"
    assert progress.book_id == "b1"
    assert progress.page_number == 42
    assert session.add.called
    assert session.commit.called


@pytest.mark.asyncio
async def test_upsert_updates_existing_row_page_number():
    session = AsyncMock()
    existing = ReadingProgress(id="rp1", user_id="u1", book_id="b1", page_number=5)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_res
    repo = ReadingProgressRepository(session)

    progress = await repo.upsert(user_id="u1", book_id="b1", page_number=42)

    assert progress.page_number == 42
    assert session.commit.called


@pytest.mark.asyncio
async def test_get_for_book_not_found_returns_none():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res
    repo = ReadingProgressRepository(session)

    result = await repo.get_for_book(user_id="u1", book_id="missing")
    assert result is None


@pytest.mark.asyncio
async def test_list_recent_orders_by_updated_at_desc():
    session = AsyncMock()
    rows = [ReadingProgress(id="rp1", user_id="u1", book_id="b1", page_number=1)]
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = rows
    session.execute.return_value = mock_res
    repo = ReadingProgressRepository(session)

    result = await repo.list_recent(user_id="u1", limit=10)
    assert result == rows
```

Create `packages/backend-core/tests/app/db/bookmarks_repository_test.py`:

```python
"""Tests for BookmarksRepository"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.db.models import Bookmark
from app.db.repositories.bookmarks_repository import BookmarksRepository


@pytest.mark.asyncio
async def test_create_bookmark_whole_page():
    session = AsyncMock()
    session.add = MagicMock()
    repo = BookmarksRepository(session)

    bookmark = await repo.create(user_id="u1", book_id="b1", page_number=42, name="Page 42")

    assert bookmark.user_id == "u1"
    assert bookmark.page_number == 42
    assert bookmark.name == "Page 42"
    assert bookmark.quote_text is None
    assert session.add.called
    assert session.commit.called


@pytest.mark.asyncio
async def test_create_bookmark_with_quote():
    session = AsyncMock()
    session.add = MagicMock()
    repo = BookmarksRepository(session)

    bookmark = await repo.create(
        user_id="u1", book_id="b1", page_number=10, name="Nice line", quote_text="a quoted passage"
    )

    assert bookmark.quote_text == "a quoted passage"


@pytest.mark.asyncio
async def test_list_scoped_to_book():
    session = AsyncMock()
    rows = [Bookmark(id="bm1", user_id="u1", book_id="b1", page_number=1, name="A")]
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = rows
    session.execute.return_value = mock_res
    repo = BookmarksRepository(session)

    result = await repo.list(user_id="u1", book_id="b1")
    assert result == rows


@pytest.mark.asyncio
async def test_get_returns_none_for_other_users_bookmark():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res
    repo = BookmarksRepository(session)

    result = await repo.get(bookmark_id="bm1", user_id="someone-else")
    assert result is None


@pytest.mark.asyncio
async def test_rename_updates_name_when_owned():
    session = AsyncMock()
    existing = Bookmark(id="bm1", user_id="u1", book_id="b1", page_number=1, name="Old")
    get_res = MagicMock()
    get_res.scalar_one_or_none.return_value = existing
    session.execute.return_value = get_res
    repo = BookmarksRepository(session)

    result = await repo.rename(bookmark_id="bm1", user_id="u1", name="New")

    assert result is not None
    assert result.name == "New"
    assert session.commit.called


@pytest.mark.asyncio
async def test_delete_returns_true_when_row_deleted():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res
    repo = BookmarksRepository(session)

    result = await repo.delete(bookmark_id="bm1", user_id="u1")
    assert result is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_not_owned_or_missing():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 0
    session.execute.return_value = mock_res
    repo = BookmarksRepository(session)

    result = await repo.delete(bookmark_id="bm1", user_id="u1")
    assert result is False
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/db/reading_progress_repository_test.py tests/app/db/bookmarks_repository_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.repositories.reading_progress_repository'` (and same for `bookmarks_repository`).

- [x] **Step 3: Implement `ReadingProgressRepository`**

Create `packages/backend-core/app/db/repositories/reading_progress_repository.py`:

```python
"""Repository for per-user, per-book silent reading progress (resume position)"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReadingProgress
from app.db.repositories.base_repository import BaseRepository


class ReadingProgressRepository(BaseRepository[ReadingProgress]):
    """Repository for reading_progress rows"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ReadingProgress)

    async def upsert(self, user_id: str, book_id: str, page_number: int) -> ReadingProgress:
        """Create or update this user's saved page for a book"""
        existing = await self.get_for_book(user_id, book_id)
        if existing:
            existing.page_number = page_number
        else:
            existing = ReadingProgress(user_id=user_id, book_id=book_id, page_number=page_number)
            self.session.add(existing)
        await self.session.commit()
        await self.session.refresh(existing)
        return existing

    async def get_for_book(self, user_id: str, book_id: str) -> Optional[ReadingProgress]:
        """Fetch this user's saved progress for a single book, if any"""
        stmt = select(ReadingProgress).where(
            ReadingProgress.user_id == user_id, ReadingProgress.book_id == book_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(self, user_id: str, limit: int = 50) -> List[ReadingProgress]:
        """List this user's books with progress, most recently updated first"""
        stmt = (
            select(ReadingProgress)
            .where(ReadingProgress.user_id == user_id)
            .order_by(ReadingProgress.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


def get_reading_progress_repository(session: AsyncSession) -> ReadingProgressRepository:
    """Factory helper for ReadingProgressRepository"""
    return ReadingProgressRepository(session)
```

- [x] **Step 4: Implement `BookmarksRepository`**

Create `packages/backend-core/app/db/repositories/bookmarks_repository.py`:

```python
"""Repository for user-created page and passage bookmarks"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, update as sql_update, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bookmark
from app.db.repositories.base_repository import BaseRepository


class BookmarksRepository(BaseRepository[Bookmark]):
    """Repository for bookmark rows, always scoped to the owning user"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Bookmark)

    async def create(
        self,
        user_id: str,
        book_id: str,
        page_number: int,
        name: str,
        quote_text: Optional[str] = None,
    ) -> Bookmark:
        """Create a new bookmark"""
        bookmark = Bookmark(
            user_id=user_id,
            book_id=book_id,
            page_number=page_number,
            name=name,
            quote_text=quote_text,
        )
        self.session.add(bookmark)
        await self.session.commit()
        await self.session.refresh(bookmark)
        return bookmark

    async def list(self, user_id: str, book_id: Optional[str] = None) -> List[Bookmark]:
        """List this user's bookmarks, optionally scoped to one book"""
        stmt = select(Bookmark).where(Bookmark.user_id == user_id)
        if book_id is not None:
            stmt = stmt.where(Bookmark.book_id == book_id).order_by(Bookmark.page_number.asc())
        else:
            stmt = stmt.order_by(Bookmark.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, bookmark_id: str, user_id: str) -> Optional[Bookmark]:
        """Fetch a bookmark by id, only if owned by this user"""
        stmt = select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def rename(self, bookmark_id: str, user_id: str, name: str) -> Optional[Bookmark]:
        """Rename a bookmark if owned by this user"""
        bookmark = await self.get(bookmark_id, user_id)
        if bookmark is None:
            return None
        bookmark.name = name
        await self.session.commit()
        await self.session.refresh(bookmark)
        return bookmark

    async def delete(self, bookmark_id: str, user_id: str) -> bool:
        """Delete a bookmark if owned by this user. Returns True if a row was deleted"""
        stmt = sql_delete(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0


def get_bookmarks_repository(session: AsyncSession) -> BookmarksRepository:
    """Factory helper for BookmarksRepository"""
    return BookmarksRepository(session)
```

Note: `rename`'s test mocks `session.execute` once for the `get()` lookup inside it — this matches because `get()` is the only `session.execute` call in that path.

- [x] **Step 5: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/db/reading_progress_repository_test.py tests/app/db/bookmarks_repository_test.py -v`
Expected: all tests PASS.

- [x] **Step 6: Commit**

```bash
git add packages/backend-core/app/db/models.py packages/backend-core/app/db/repositories/reading_progress_repository.py packages/backend-core/app/db/repositories/bookmarks_repository.py packages/backend-core/tests/app/db/reading_progress_repository_test.py packages/backend-core/tests/app/db/bookmarks_repository_test.py
git commit -m "feat(db): add ReadingProgress/Bookmark models and repositories"
```

---

### Task 3: Backend API — `bookmarks_router.py`

**Files:**
- Create: `services/backend/api/endpoints/bookmarks_router.py`
- Test: `services/backend/tests/api/endpoints/bookmarks_router_test.py`
- Modify: `services/backend/main.py`
- Modify: `services/backend/locales/en.json`
- Modify: `services/backend/locales/ug.json`

**Interfaces:**
- Consumes: `ReadingProgressRepository`, `BookmarksRepository` (Task 2); `require_reader`, `get_session` (existing, `auth/dependencies.py`, `app/db/session.py`).
- Produces (all under `prefix="/api/bookmarks"`, all `Depends(require_reader)`):
  - `PUT /progress/{book_id}` body `{page_number: int}` → `{"bookId", "pageNumber", "updatedAt"}`
  - `GET /progress/{book_id}` → `{"pageNumber": int} | {"pageNumber": null}` (this single-book lookup is an addition beyond the spec's 6 listed endpoints, needed by Task 5's `openReader` resume check — fetching the entire `GET /progress` list just to check one book would be wasteful)
  - `GET /progress` → `{"items": [{"bookId", "bookTitle", "bookCoverUrl", "pageNumber", "updatedAt"}]}`
  - `POST /{book_id}` body `{page_number: int, name: str, quote_text?: str}` → bookmark dict (see Step 3)
  - `GET /` query `?book_id=` optional → `{"bookmarks": [bookmark dict, ...]}`
  - `PATCH /{bookmark_id}` body `{name: str}` → bookmark dict, 404 if not owned
  - `DELETE /{bookmark_id}` → `{"success": true}`, 404 if not owned

- [x] **Step 1: Write the failing router tests**

Create `services/backend/tests/api/endpoints/bookmarks_router_test.py`:

```python
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def make_user(user_id="user-1"):
    from app.models.user import User

    user = MagicMock(spec=User)
    user.id = user_id
    user.role = "reader"
    return user


@pytest.mark.asyncio
async def test_upsert_progress_endpoint():
    setup_paths()
    from api.endpoints.bookmarks_router import upsert_progress_endpoint, UpsertProgressRequest
    from app.db.models import ReadingProgress

    session = AsyncMock()
    with_repo = ReadingProgress(
        user_id="user-1", book_id="book-1", page_number=42, updated_at=datetime.now(timezone.utc)
    )
    with _mock_repo("api.endpoints.bookmarks_router.ReadingProgressRepository", "upsert", with_repo):
        response = await upsert_progress_endpoint(
            book_id="book-1",
            req=UpsertProgressRequest(page_number=42),
            current_user=make_user(),
            session=session,
        )

    assert response["bookId"] == "book-1"
    assert response["pageNumber"] == 42


@pytest.mark.asyncio
async def test_get_progress_for_book_returns_none_when_missing():
    setup_paths()
    from api.endpoints.bookmarks_router import get_progress_for_book_endpoint

    session = AsyncMock()
    with _mock_repo("api.endpoints.bookmarks_router.ReadingProgressRepository", "get_for_book", None):
        response = await get_progress_for_book_endpoint(
            book_id="book-1", current_user=make_user(), session=session
        )

    assert response["pageNumber"] is None


@pytest.mark.asyncio
async def test_list_progress_endpoint():
    setup_paths()
    from api.endpoints.bookmarks_router import list_progress_endpoint
    from app.db.models import ReadingProgress, Book

    session = AsyncMock()
    row = ReadingProgress(
        user_id="user-1", book_id="book-1", page_number=5, updated_at=datetime.now(timezone.utc)
    )
    row.book = Book(id="book-1", title="My Book", content_hash="h")
    with _mock_repo("api.endpoints.bookmarks_router.ReadingProgressRepository", "list_recent", [row]):
        response = await list_progress_endpoint(current_user=make_user(), session=session)

    assert response["items"][0]["bookId"] == "book-1"
    assert response["items"][0]["bookTitle"] == "My Book"
    assert response["items"][0]["pageNumber"] == 5


@pytest.mark.asyncio
async def test_create_bookmark_endpoint():
    setup_paths()
    from api.endpoints.bookmarks_router import create_bookmark_endpoint, CreateBookmarkRequest
    from app.db.models import Bookmark, Book

    session = AsyncMock()
    bookmark = Bookmark(
        id="bm1", user_id="user-1", book_id="book-1", page_number=3, name="My mark",
        created_at=datetime.now(timezone.utc),
    )
    bookmark.book = Book(id="book-1", title="My Book", content_hash="h")
    with _mock_repo("api.endpoints.bookmarks_router.BookmarksRepository", "create", bookmark):
        response = await create_bookmark_endpoint(
            book_id="book-1",
            req=CreateBookmarkRequest(page_number=3, name="My mark"),
            current_user=make_user(),
            session=session,
        )

    assert response["id"] == "bm1"
    assert response["name"] == "My mark"
    assert response["quoteText"] is None


@pytest.mark.asyncio
async def test_list_bookmarks_endpoint_with_book_filter():
    setup_paths()
    from api.endpoints.bookmarks_router import list_bookmarks_endpoint
    from app.db.models import Bookmark, Book

    session = AsyncMock()
    bookmark = Bookmark(
        id="bm1", user_id="user-1", book_id="book-1", page_number=3, name="My mark",
        created_at=datetime.now(timezone.utc),
    )
    bookmark.book = Book(id="book-1", title="My Book", content_hash="h")
    with _mock_repo("api.endpoints.bookmarks_router.BookmarksRepository", "list", [bookmark]) as mock_repo_class:
        response = await list_bookmarks_endpoint(book_id="book-1", current_user=make_user(), session=session)
        mock_repo_class.return_value.list.assert_called_once_with(user_id="user-1", book_id="book-1")

    assert len(response["bookmarks"]) == 1


@pytest.mark.asyncio
async def test_rename_bookmark_endpoint_not_found_raises_404():
    setup_paths()
    from api.endpoints.bookmarks_router import rename_bookmark_endpoint, RenameBookmarkRequest
    from fastapi import HTTPException

    session = AsyncMock()
    with _mock_repo("api.endpoints.bookmarks_router.BookmarksRepository", "rename", None):
        with pytest.raises(HTTPException) as exc_info:
            await rename_bookmark_endpoint(
                bookmark_id="missing",
                req=RenameBookmarkRequest(name="New"),
                current_user=make_user(),
                session=session,
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_bookmark_endpoint_not_found_raises_404():
    setup_paths()
    from api.endpoints.bookmarks_router import delete_bookmark_endpoint
    from fastapi import HTTPException

    session = AsyncMock()
    with _mock_repo("api.endpoints.bookmarks_router.BookmarksRepository", "delete", False):
        with pytest.raises(HTTPException) as exc_info:
            await delete_bookmark_endpoint(bookmark_id="missing", current_user=make_user(), session=session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_bookmark_endpoint_success():
    setup_paths()
    from api.endpoints.bookmarks_router import delete_bookmark_endpoint

    session = AsyncMock()
    with _mock_repo("api.endpoints.bookmarks_router.BookmarksRepository", "delete", True):
        response = await delete_bookmark_endpoint(bookmark_id="bm1", current_user=make_user(), session=session)

    assert response == {"success": True}


def _mock_repo(target_path: str, method_name: str, return_value):
    """Patch <RepositoryClass>(session).<method_name> to return return_value"""
    from unittest.mock import patch

    mock_instance = MagicMock()
    setattr(mock_instance, method_name, AsyncMock(return_value=return_value))
    return patch(target_path, return_value=mock_instance)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd services/backend && python -m pytest tests/api/endpoints/bookmarks_router_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.endpoints.bookmarks_router'`.

- [x] **Step 3: Implement `bookmarks_router.py`**

Create `services/backend/api/endpoints/bookmarks_router.py`:

```python
"""Endpoints for silent reading progress and user-created bookmarks"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.db.session import get_session
from app.db.repositories.reading_progress_repository import ReadingProgressRepository
from app.db.repositories.bookmarks_repository import BookmarksRepository
from app.models.user import User
from auth.dependencies import require_reader

router = APIRouter()


class UpsertProgressRequest(BaseModel):
    page_number: int


class CreateBookmarkRequest(BaseModel):
    page_number: int
    name: str
    quote_text: Optional[str] = None


class RenameBookmarkRequest(BaseModel):
    name: str


@router.put("/progress/{book_id}")
async def upsert_progress_endpoint(
    book_id: str,
    req: UpsertProgressRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Silently save this user's current page for a book"""
    repo = ReadingProgressRepository(session)
    progress = await repo.upsert(user_id=current_user.id, book_id=book_id, page_number=req.page_number)
    return {
        "bookId": progress.book_id,
        "pageNumber": progress.page_number,
        "updatedAt": progress.updated_at.isoformat(),
    }


@router.get("/progress/{book_id}")
async def get_progress_for_book_endpoint(
    book_id: str,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Fetch this user's saved page for a single book, used to resume on open"""
    repo = ReadingProgressRepository(session)
    progress = await repo.get_for_book(user_id=current_user.id, book_id=book_id)
    return {"pageNumber": progress.page_number if progress else None}


@router.get("/progress")
async def list_progress_endpoint(
    limit: int = 50,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """List this user's books with saved progress, most recent first (Continue Reading tab)"""
    repo = ReadingProgressRepository(session)
    rows = await repo.list_recent(user_id=current_user.id, limit=limit)
    return {
        "items": [
            {
                "bookId": row.book_id,
                "bookTitle": row.book.title if row.book else None,
                "bookCoverUrl": row.book.cover_url if row.book else None,
                "pageNumber": row.page_number,
                "updatedAt": row.updated_at.isoformat(),
            }
            for row in rows
        ]
    }


def _serialize_bookmark(bookmark) -> dict:
    return {
        "id": bookmark.id,
        "bookId": bookmark.book_id,
        "bookTitle": bookmark.book.title if bookmark.book else None,
        "pageNumber": bookmark.page_number,
        "name": bookmark.name,
        "quoteText": bookmark.quote_text,
        "createdAt": bookmark.created_at.isoformat(),
    }


@router.post("/{book_id}")
async def create_bookmark_endpoint(
    book_id: str,
    req: CreateBookmarkRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Create a whole-page or passage bookmark"""
    repo = BookmarksRepository(session)
    bookmark = await repo.create(
        user_id=current_user.id,
        book_id=book_id,
        page_number=req.page_number,
        name=req.name,
        quote_text=req.quote_text,
    )
    return _serialize_bookmark(bookmark)


@router.get("/")
async def list_bookmarks_endpoint(
    book_id: Optional[str] = None,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """List this user's bookmarks, optionally scoped to one book"""
    repo = BookmarksRepository(session)
    bookmarks = await repo.list(user_id=current_user.id, book_id=book_id)
    return {"bookmarks": [_serialize_bookmark(b) for b in bookmarks]}


@router.patch("/{bookmark_id}")
async def rename_bookmark_endpoint(
    bookmark_id: str,
    req: RenameBookmarkRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Rename a bookmark owned by this user"""
    repo = BookmarksRepository(session)
    bookmark = await repo.rename(bookmark_id=bookmark_id, user_id=current_user.id, name=req.name)
    if bookmark is None:
        raise HTTPException(status_code=404, detail=t("errors.bookmark_not_found"))
    return _serialize_bookmark(bookmark)


@router.delete("/{bookmark_id}")
async def delete_bookmark_endpoint(
    bookmark_id: str,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Delete a bookmark owned by this user"""
    repo = BookmarksRepository(session)
    deleted = await repo.delete(bookmark_id=bookmark_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=t("errors.bookmark_not_found"))
    return {"success": True}
```

- [x] **Step 4: Add the `bookmark_not_found` i18n key**

In `services/backend/locales/en.json`, inside `"errors"`, add (alphabetically near `book_not_found`):

```json
    "bookmark_not_found": "Bookmark not found",
```

In `services/backend/locales/ug.json`, inside `"errors"`, add (draft — needs native-speaker review per Global Constraints):

```json
    "bookmark_not_found": "بەلگە تېپىلمىدى",
```

- [x] **Step 5: Register the router in `main.py`**

In `services/backend/main.py`, add `bookmarks_router` to the `from api.endpoints import (...)` block (alphabetical among the existing names):

```python
from api.endpoints import (
    ai_router,
    auth_router,
    bookmarks_router,
    books_router,
    chat_router,
    users_router,
    system_configs_router,
    stats_router,
    contact_router,
    spell_check_router,
    auto_correct_rules_router,
    dictionary_router,
    words_router,
    synonyms_router,
    history_dictionary_router,
    names_dictionary_router,
    english_uyghur_router,
    share_router,
    cache_router,
    questions_router,
    proverbs_router,
    quran_router,
    graph_admin_router,
    admin_history_dictionary_router,
)
```

Add the `include_router` call next to `books_router`'s (both operate on books):

```python
app.include_router(books_router.router, prefix="/api/books", tags=["books"])
app.include_router(bookmarks_router.router, prefix="/api/bookmarks", tags=["bookmarks"])
```

- [x] **Step 6: Run tests to verify they pass**

Run: `cd services/backend && python -m pytest tests/api/endpoints/bookmarks_router_test.py -v`
Expected: all tests PASS.

- [x] **Step 7: Rebuild and smoke-test locally**

Run: `./deploy/local/rebuild-and-restart.sh backend`

Then, as a signed-in user (grab a bearer token from the browser's localStorage after logging in at http://localhost:30080, or use an existing integration-test helper if the repo has one):

```bash
curl -s -X PUT http://localhost:30800/api/bookmarks/progress/<a-real-book-id> \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"page_number": 3}'
```

Expected: `{"bookId": "...", "pageNumber": 3, "updatedAt": "..."}`.

- [x] **Step 8: Commit**

```bash
git add services/backend/api/endpoints/bookmarks_router.py services/backend/tests/api/endpoints/bookmarks_router_test.py services/backend/main.py services/backend/locales/en.json services/backend/locales/ug.json
git commit -m "feat(api): add bookmarks and reading-progress endpoints"
```

---

### Task 4: Frontend types and `PersistenceService` methods

**Files:**
- Modify: `packages/shared/src/types.ts`
- Modify: `apps/frontend/src/services/persistenceService.ts`
- Test: `apps/frontend/src/tests/services/persistenceService.bookmarks.test.ts` (new)

**Interfaces:**
- Produces:
  - `interface Bookmark { id: string; bookId: string; bookTitle: string | null; pageNumber: number; name: string; quoteText: string | null; createdAt: string; }`
  - `interface ReadingProgressEntry { bookId: string; bookTitle: string | null; bookCoverUrl: string | null; pageNumber: number; updatedAt: string; }`
  - `PersistenceService.saveReadingProgress(bookId: string, pageNumber: number): Promise<void>`
  - `PersistenceService.getReadingProgress(bookId: string): Promise<number | null>`
  - `PersistenceService.listReadingProgress(): Promise<ReadingProgressEntry[]>`
  - `PersistenceService.createBookmark(bookId: string, pageNumber: number, name: string, quoteText?: string): Promise<Bookmark>`
  - `PersistenceService.listBookmarks(bookId?: string): Promise<Bookmark[]>`
  - `PersistenceService.renameBookmark(id: string, name: string): Promise<void>`
  - `PersistenceService.deleteBookmark(id: string): Promise<void>`

- [x] **Step 1: Add the shared types**

In `packages/shared/src/types.ts`, the file ends with an `export interface ChatRequest { ... }` block and no trailing `export default` — append these two new interfaces after it, at the end of the file:

```typescript
export interface Bookmark {
  id: string;
  bookId: string;
  bookTitle: string | null;
  pageNumber: number;
  name: string;
  quoteText: string | null;
  createdAt: string;
}

export interface ReadingProgressEntry {
  bookId: string;
  bookTitle: string | null;
  bookCoverUrl: string | null;
  pageNumber: number;
  updatedAt: string;
}
```

- [x] **Step 2: Write the failing service tests**

Create `apps/frontend/src/tests/services/persistenceService.bookmarks.test.ts`:

```typescript
import { PersistenceService } from '@/src/services/persistenceService';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

import { authFetch } from '@/src/services/authService';

const jsonResponse = (body: unknown, ok = true) => ({
  ok,
  json: async () => body,
} as Response);

beforeEach(() => {
  vi.clearAllMocks();
});

test('saveReadingProgress PUTs the page number', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ bookId: 'b1', pageNumber: 5 }));

  await PersistenceService.saveReadingProgress('b1', 5);

  expect(authFetch).toHaveBeenCalledWith(
    '/api/bookmarks/progress/b1',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ page_number: 5 }) })
  );
});

test('getReadingProgress returns the saved page number', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ pageNumber: 12 }));

  const result = await PersistenceService.getReadingProgress('b1');

  expect(result).toBe(12);
});

test('getReadingProgress returns null when none saved', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ pageNumber: null }));

  const result = await PersistenceService.getReadingProgress('b1');

  expect(result).toBeNull();
});

test('getReadingProgress returns null on failure', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({}, false));

  const result = await PersistenceService.getReadingProgress('b1');

  expect(result).toBeNull();
});

test('listReadingProgress returns the items array', async () => {
  const items = [{ bookId: 'b1', bookTitle: 'T', bookCoverUrl: null, pageNumber: 5, updatedAt: 'now' }];
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ items }));

  const result = await PersistenceService.listReadingProgress();

  expect(result).toEqual(items);
});

test('createBookmark POSTs page, name, and optional quote', async () => {
  const bookmark = { id: 'bm1', bookId: 'b1', bookTitle: 'T', pageNumber: 3, name: 'N', quoteText: 'Q', createdAt: 'now' };
  vi.mocked(authFetch).mockResolvedValue(jsonResponse(bookmark));

  const result = await PersistenceService.createBookmark('b1', 3, 'N', 'Q');

  expect(authFetch).toHaveBeenCalledWith(
    '/api/bookmarks/b1',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ page_number: 3, name: 'N', quote_text: 'Q' }),
    })
  );
  expect(result).toEqual(bookmark);
});

test('listBookmarks omits bookId query param when not scoped', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ bookmarks: [] }));

  await PersistenceService.listBookmarks();

  expect(authFetch).toHaveBeenCalledWith('/api/bookmarks');
});

test('listBookmarks includes bookId query param when scoped', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ bookmarks: [] }));

  await PersistenceService.listBookmarks('b1');

  expect(authFetch).toHaveBeenCalledWith('/api/bookmarks?book_id=b1');
});

test('renameBookmark PATCHes the new name', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({}));

  await PersistenceService.renameBookmark('bm1', 'New name');

  expect(authFetch).toHaveBeenCalledWith(
    '/api/bookmarks/bm1',
    expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ name: 'New name' }) })
  );
});

test('deleteBookmark DELETEs the bookmark', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ success: true }));

  await PersistenceService.deleteBookmark('bm1');

  expect(authFetch).toHaveBeenCalledWith('/api/bookmarks/bm1', expect.objectContaining({ method: 'DELETE' }));
});
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/services/persistenceService.bookmarks.test.ts`
Expected: FAIL — `PersistenceService.saveReadingProgress is not a function` (and similarly for the other new methods).

- [x] **Step 4: Implement the `PersistenceService` methods**

In `apps/frontend/src/services/persistenceService.ts`, add near `setPageToc` (both are small book-scoped mutations):

```typescript
  async saveReadingProgress(bookId: string, pageNumber: number): Promise<void> {
    try {
      await authFetch(`${API_BASE}/bookmarks/progress/${bookId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_number: pageNumber }),
      });
    } catch (error) {
      console.error("Failed to save reading progress", error);
    }
  },

  async getReadingProgress(bookId: string): Promise<number | null> {
    try {
      const response = await authFetch(`${API_BASE}/bookmarks/progress/${bookId}`);
      if (!response.ok) return null;
      const data = await response.json();
      return data.pageNumber ?? null;
    } catch (error) {
      console.error("Failed to fetch reading progress", error);
      return null;
    }
  },

  async listReadingProgress(): Promise<ReadingProgressEntry[]> {
    try {
      const response = await authFetch(`${API_BASE}/bookmarks/progress`);
      if (!response.ok) return [];
      const data = await response.json();
      return data.items || [];
    } catch (error) {
      console.error("Failed to fetch reading progress list", error);
      return [];
    }
  },

  async createBookmark(bookId: string, pageNumber: number, name: string, quoteText?: string): Promise<Bookmark> {
    const response = await authFetch(`${API_BASE}/bookmarks/${bookId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_number: pageNumber, name, quote_text: quoteText }),
    });
    if (!response.ok) throw new Error("Failed to create bookmark");
    return response.json();
  },

  async listBookmarks(bookId?: string): Promise<Bookmark[]> {
    try {
      const url = bookId ? `${API_BASE}/bookmarks?book_id=${bookId}` : `${API_BASE}/bookmarks`;
      const response = await authFetch(url);
      if (!response.ok) return [];
      const data = await response.json();
      return data.bookmarks || [];
    } catch (error) {
      console.error("Failed to fetch bookmarks", error);
      return [];
    }
  },

  async renameBookmark(id: string, name: string): Promise<void> {
    const response = await authFetch(`${API_BASE}/bookmarks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) throw new Error("Failed to rename bookmark");
  },

  async deleteBookmark(id: string): Promise<void> {
    const response = await authFetch(`${API_BASE}/bookmarks/${id}`, { method: 'DELETE' });
    if (!response.ok) throw new Error("Failed to delete bookmark");
  },
```

Add the import at the top of the file:

```typescript
import { Book, PaginatedBooks, Bookmark, ReadingProgressEntry } from '@shared/types';
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/services/persistenceService.bookmarks.test.ts`
Expected: all tests PASS.

- [x] **Step 6: Commit**

```bash
git add packages/shared/src/types.ts apps/frontend/src/services/persistenceService.ts apps/frontend/src/tests/services/persistenceService.bookmarks.test.ts
git commit -m "feat(frontend): add bookmark/progress types and service methods"
```

---

### Task 5: Auto reading-progress — save and resume

**Files:**
- Modify: `apps/frontend/src/context/AppContext.tsx`
- Modify: `apps/frontend/src/hooks/useBookActions.ts`
- Modify: `apps/frontend/src/tests/hooks/useBookActions.test.tsx`
- Test: `apps/frontend/src/tests/context/AppContext.progress.test.tsx` (new)

**Interfaces:**
- Consumes: `PersistenceService.saveReadingProgress`, `PersistenceService.getReadingProgress` (Task 4).
- Produces: `useBookActions(...).openReader(book, initialPage?: number)` — when `initialPage` is omitted, resolves from saved progress (falls back to `1`). `AppContext` debounces a progress save whenever `currentPage`/`selectedBook` are set while in the reader.

- [x] **Step 1: Write the failing `openReader` resume tests**

In `apps/frontend/src/tests/hooks/useBookActions.test.tsx`, add `getReadingProgress` to the mocked `PersistenceService` (Step 1 of the existing `vi.mock` block):

```typescript
vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    uploadPdf: vi.fn(),
    getBookById: vi.fn(),
    getReadingProgress: vi.fn(),
    saveBookGlobally: vi.fn(),
    deleteBook: vi.fn(),
    updateBookMetadata: vi.fn(),
    updatePage: vi.fn(),
    resetPage: vi.fn(),
    setPageToc: vi.fn(),
    reprocessLlmSpellCheck: vi.fn(),
    triggerLlmSpellCheckPage: vi.fn(),
  }
}));
```

Update the existing `'useBookActions handles openReader'` test to also mock `getReadingProgress` resolving `null` (so it keeps asserting the page-1 default through the new resume path instead of the old unconditional default), then add three more tests covering explicit page, resumed page, and no-saved-progress fallback:

```typescript
test('useBookActions handles openReader', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue(mockBook as any);
  vi.mocked(PersistenceService.getReadingProgress).mockResolvedValue(null);
  const { result, setSelectedBook, setView, setChatMessages, setCurrentPage } = createHook();

  await act(async () => {
    await result.current.openReader(mockBook);
  });

  expect(setSelectedBook).toHaveBeenCalledWith(mockBook);
  expect(setChatMessages).toHaveBeenCalledWith([]);
  expect(setView).toHaveBeenCalledWith('reader');
  expect(setCurrentPage).toHaveBeenCalledWith(1);
});

test('useBookActions openReader uses an explicit initialPage without checking progress', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue(mockBook as any);
  const { result, setCurrentPage } = createHook();

  await act(async () => {
    await result.current.openReader(mockBook, 7);
  });

  expect(setCurrentPage).toHaveBeenCalledWith(7);
  expect(PersistenceService.getReadingProgress).not.toHaveBeenCalled();
});

test('useBookActions openReader resumes from saved progress when no initialPage given', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue(mockBook as any);
  vi.mocked(PersistenceService.getReadingProgress).mockResolvedValue(15);
  const { result, setCurrentPage } = createHook();

  await act(async () => {
    await result.current.openReader(mockBook);
  });

  expect(PersistenceService.getReadingProgress).toHaveBeenCalledWith('1');
  expect(setCurrentPage).toHaveBeenCalledWith(15);
});

test('useBookActions openReader falls back to page 1 with no saved progress', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue(mockBook as any);
  vi.mocked(PersistenceService.getReadingProgress).mockResolvedValue(null);
  const { result, setCurrentPage } = createHook();

  await act(async () => {
    await result.current.openReader(mockBook);
  });

  expect(setCurrentPage).toHaveBeenCalledWith(1);
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useBookActions.test.tsx`
Expected: FAIL — `PersistenceService.getReadingProgress` mock not called as expected (current `openReader` always defaults to `1` without checking progress); the "explicit initialPage" test also fails only if the current signature's default parameter interferes (it currently should pass since 7 is a real arg — but the `not.toHaveBeenCalled()` assertion also needs the implementation NOT to fetch when a page is given, which the current code already satisfies since it never calls `getReadingProgress` at all — verify this test's baseline behavior; the *resume* and *fallback* tests are the ones expected to fail).

- [x] **Step 3: Update `openReader` to resume from saved progress**

In `apps/frontend/src/hooks/useBookActions.ts`, change the `openReader` signature and body:

```typescript
  const openReader = async (book: Book | { id: string }, initialPage?: number) => {
    setIsOpeningBook(true);
    try {
      const fullBook = await PersistenceService.getBookById(book.id);
      if (!fullBook) throw new Error("Could not load book content");

      // Ensure pages is an array
      if (!fullBook.pages) fullBook.pages = [];

      const resolvedPage = initialPage ?? (await PersistenceService.getReadingProgress(book.id)) ?? 1;

      setSelectedBook(fullBook);
      setChatMessages([]);
      setView('reader');
      setCurrentPage(resolvedPage);
    } catch (err) {
      console.error("Error opening reader:", err);
      setModal({
        isOpen: true,
        title: t('modal.loadError.title'),
        message: t('modal.loadError.message'),
        type: 'alert'
      });
    } finally {
      setIsOpeningBook(false);
    }
  };
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useBookActions.test.tsx`
Expected: all tests PASS.

- [x] **Step 5: Write the failing `AppContext` debounced-save test**

Create `apps/frontend/src/tests/context/AppContext.progress.test.tsx`:

```typescript
import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AppProvider, useAppContext } from '@/src/context/AppContext';
import { AuthProvider } from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { NotificationProvider } from '@/src/context/NotificationContext';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookById: vi.fn().mockResolvedValue(null),
    saveReadingProgress: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/src/hooks/useBooks', () => ({
  useBooks: () => ({
    books: [], setBooks: vi.fn(), totalBooks: 0, totalReady: 0, sortedBooks: [],
    sortConfig: { key: 'title', direction: 'asc' }, refreshLibrary: vi.fn(),
    loadMoreShelf: vi.fn(), isLoading: false, isLoadingMoreShelf: false, hasMoreShelf: false,
  }),
}));

vi.mock('@/src/hooks/useChat', () => ({
  useChat: () => ({ setChatMessages: vi.fn(), selectedCharacterId: '', setSelectedCharacterId: vi.fn() }),
}));

// AppProvider's useBookActions() calls useNotification(), which throws without
// a NotificationProvider ancestor — mirror AppContext.test.tsx's full wrapper
// rather than a bare AppProvider.
const i18nMockValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <NotificationProvider>
    <AuthProvider>
      <I18nContext.Provider value={i18nMockValue}>
        <AppProvider>{children}</AppProvider>
      </I18nContext.Provider>
    </AuthProvider>
  </NotificationProvider>
);

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

test('debounces reading-progress saves after currentPage settles', async () => {
  const { result } = renderHook(() => useAppContext(), { wrapper });

  act(() => {
    result.current.setSelectedBook({ id: 'book-1' } as any);
  });
  act(() => {
    result.current.setCurrentPage(5);
  });
  act(() => {
    result.current.setCurrentPage(6);
  });

  expect(PersistenceService.saveReadingProgress).not.toHaveBeenCalled();

  await act(async () => {
    vi.advanceTimersByTime(2100);
  });

  expect(PersistenceService.saveReadingProgress).toHaveBeenCalledTimes(1);
  expect(PersistenceService.saveReadingProgress).toHaveBeenCalledWith('book-1', 6);
});

test('does not save progress when no book is selected', async () => {
  renderHook(() => useAppContext(), { wrapper });

  await act(async () => {
    vi.advanceTimersByTime(3000);
  });

  expect(PersistenceService.saveReadingProgress).not.toHaveBeenCalled();
});
```

- [x] **Step 6: Run test to verify it fails**

Run: `cd apps/frontend && npx vitest run src/tests/context/AppContext.progress.test.tsx`
Expected: FAIL — `saveReadingProgress` never called (no debounced effect exists yet).

- [x] **Step 7: Add the debounced progress-save effect to `AppContext`**

In `apps/frontend/src/context/AppContext.tsx`, add after the existing deep-link `useEffect` (the one calling `PersistenceService.getBookById(initialBookId)`):

```typescript
  // Silently persist reading progress a couple seconds after the centered
  // page settles, so a normal scroll doesn't spam the API on every tick.
  useEffect(() => {
    if (!selectedBook || currentPage === null) return;
    const bookId = selectedBook.id;
    const pageNumber = currentPage;
    const timeoutId = window.setTimeout(() => {
      PersistenceService.saveReadingProgress(bookId, pageNumber);
    }, 2000);
    return () => window.clearTimeout(timeoutId);
  }, [selectedBook, currentPage]);
```

- [x] **Step 8: Run test to verify it passes**

Run: `cd apps/frontend && npx vitest run src/tests/context/AppContext.progress.test.tsx`
Expected: both tests PASS.

- [x] **Step 9: Commit**

```bash
git add apps/frontend/src/context/AppContext.tsx apps/frontend/src/hooks/useBookActions.ts apps/frontend/src/tests/hooks/useBookActions.test.tsx apps/frontend/src/tests/context/AppContext.progress.test.tsx
git commit -m "feat(reader): silently save and resume reading progress"
```

---

### Task 6: `useBookmarks` hook

**Files:**
- Create: `apps/frontend/src/hooks/useBookmarks.ts`
- Test: `apps/frontend/src/tests/hooks/useBookmarks.test.tsx`

**Interfaces:**
- Consumes: `PersistenceService.listBookmarks/createBookmark/renameBookmark/deleteBookmark` (Task 4), `useAuth()` (existing, for `isAuthenticated`).
- Produces: `useBookmarks(bookId?: string): { bookmarks: Bookmark[]; isLoading: boolean; refresh: () => Promise<void>; create: (pageNumber: number, name: string, quoteText?: string) => Promise<Bookmark>; rename: (id: string, name: string) => Promise<void>; remove: (id: string) => Promise<void>; }`. Task 7 (PageItem icons) and Task 8 (drawer) call this with a `bookId`; Task 10 (Library Bookmarks tab) calls it with no argument.

- [x] **Step 1: Write the failing hook tests**

Create `apps/frontend/src/tests/hooks/useBookmarks.test.tsx`:

```typescript
import { useBookmarks } from '@/src/hooks/useBookmarks';
import { PersistenceService } from '@/src/services/persistenceService';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    listBookmarks: vi.fn(),
    createBookmark: vi.fn(),
    renameBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
  },
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({ isAuthenticated: true })),
}));

import { useAuth } from '@/src/hooks/useAuth';

const mockBookmark = {
  id: 'bm1', bookId: 'b1', bookTitle: 'T', pageNumber: 3, name: 'N', quoteText: null, createdAt: 'now',
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: true } as any);
});

test('loads bookmarks scoped to a book on mount', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([mockBookmark]);

  const { result } = renderHook(() => useBookmarks('b1'));

  await waitFor(() => expect(result.current.bookmarks).toEqual([mockBookmark]));
  expect(PersistenceService.listBookmarks).toHaveBeenCalledWith('b1');
});

test('loads all bookmarks when no bookId given', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([mockBookmark]);

  renderHook(() => useBookmarks());

  await waitFor(() => expect(PersistenceService.listBookmarks).toHaveBeenCalledWith(undefined));
});

test('skips fetching and clears list for guests', async () => {
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: false } as any);

  const { result } = renderHook(() => useBookmarks('b1'));

  await waitFor(() => expect(result.current.isLoading).toBe(false));
  expect(PersistenceService.listBookmarks).not.toHaveBeenCalled();
  expect(result.current.bookmarks).toEqual([]);
});

test('create appends the new bookmark to state', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([]);
  vi.mocked(PersistenceService.createBookmark).mockResolvedValue(mockBookmark);
  const { result } = renderHook(() => useBookmarks('b1'));
  await waitFor(() => expect(result.current.isLoading).toBe(false));

  await act(async () => {
    await result.current.create(3, 'N');
  });

  expect(PersistenceService.createBookmark).toHaveBeenCalledWith('b1', 3, 'N', undefined);
  expect(result.current.bookmarks).toEqual([mockBookmark]);
});

test('rename updates the bookmark name in state', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([mockBookmark]);
  const { result } = renderHook(() => useBookmarks('b1'));
  await waitFor(() => expect(result.current.bookmarks).toEqual([mockBookmark]));

  await act(async () => {
    await result.current.rename('bm1', 'Renamed');
  });

  expect(PersistenceService.renameBookmark).toHaveBeenCalledWith('bm1', 'Renamed');
  expect(result.current.bookmarks[0].name).toBe('Renamed');
});

test('remove drops the bookmark from state', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([mockBookmark]);
  const { result } = renderHook(() => useBookmarks('b1'));
  await waitFor(() => expect(result.current.bookmarks).toEqual([mockBookmark]));

  await act(async () => {
    await result.current.remove('bm1');
  });

  expect(PersistenceService.deleteBookmark).toHaveBeenCalledWith('bm1');
  expect(result.current.bookmarks).toEqual([]);
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useBookmarks.test.tsx`
Expected: FAIL — `Cannot find module '@/src/hooks/useBookmarks'`.

- [x] **Step 3: Implement `useBookmarks`**

Create `apps/frontend/src/hooks/useBookmarks.ts`:

```typescript
import { Bookmark } from '@shared/types';
import { useCallback, useEffect, useState } from 'react';
import { PersistenceService } from '../services/persistenceService';
import { useAuth } from './useAuth';

export function useBookmarks(bookId?: string) {
  const { isAuthenticated } = useAuth();
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setBookmarks([]);
      return;
    }
    setIsLoading(true);
    try {
      const result = await PersistenceService.listBookmarks(bookId);
      setBookmarks(result);
    } finally {
      setIsLoading(false);
    }
  }, [bookId, isAuthenticated]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(async (pageNumber: number, name: string, quoteText?: string) => {
    if (!bookId) throw new Error('bookId is required to create a bookmark');
    const bookmark = await PersistenceService.createBookmark(bookId, pageNumber, name, quoteText);
    setBookmarks(prev => [...prev, bookmark]);
    return bookmark;
  }, [bookId]);

  const rename = useCallback(async (id: string, name: string) => {
    await PersistenceService.renameBookmark(id, name);
    setBookmarks(prev => prev.map(b => (b.id === id ? { ...b, name } : b)));
  }, []);

  const remove = useCallback(async (id: string) => {
    await PersistenceService.deleteBookmark(id);
    setBookmarks(prev => prev.filter(b => b.id !== id));
  }, []);

  return { bookmarks, isLoading, refresh, create, rename, remove };
}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useBookmarks.test.tsx`
Expected: all tests PASS.

- [x] **Step 5: Commit**

```bash
git add apps/frontend/src/hooks/useBookmarks.ts apps/frontend/src/tests/hooks/useBookmarks.test.tsx
git commit -m "feat(reader): add useBookmarks hook"
```

---

### Task 7: Bookmark creation UI in the reader

**Files:**
- Create: `apps/frontend/src/components/reader/BookmarkPrompt.tsx`
- Test: `apps/frontend/src/tests/components/reader/BookmarkPrompt.test.tsx`
- Modify: `apps/frontend/src/components/reader/PageItem.tsx`
- Modify: `apps/frontend/src/components/reader/VirtualScrollReader.tsx`
- Modify: `apps/frontend/src/components/reader/ReaderView.tsx`
- Modify: `apps/frontend/src/tests/components/reader/PageItem.test.tsx`
- Modify: `apps/frontend/src/locales/en.json`, `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Consumes: `useBookmarks(bookId)` (Task 6), `useAuth()` (existing), `OAuthButtonGroup` (existing, `apps/frontend/src/components/auth/AuthButton.tsx`).
- Produces: `BookmarkPrompt` component; `PageItem` gains props `bookmarks?: Bookmark[]`, `onCreateBookmark?: (pageNumber: number, name: string, quoteText?: string) => Promise<void>`, `onRenameBookmark?: (id: string, name: string) => Promise<void>`, `onDeleteBookmark?: (id: string) => Promise<void>`, `isAuthenticated?: boolean` — threaded through `VirtualScrollReader` and `ReaderView` exactly like the existing `bookId`/`bookTitle` props.

- [ ] **Step 1: Write the failing `BookmarkPrompt` tests**

Create `apps/frontend/src/tests/components/reader/BookmarkPrompt.test.tsx`:

```typescript
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { BookmarkPrompt } from '@/src/components/reader/BookmarkPrompt';
import { I18nContext } from '@/src/i18n/I18nContext';

// BookmarkPrompt's guest branch renders OAuthButtonGroup, which calls the
// real useAuth() hook — mock it so this test doesn't need a real AuthProvider.
vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({ loginWithGoogle: vi.fn(), loginWithFacebook: vi.fn(), isLoading: false })),
}));

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const renderPrompt = (props: Partial<React.ComponentProps<typeof BookmarkPrompt>> = {}) => {
  const defaultProps: React.ComponentProps<typeof BookmarkPrompt> = {
    top: 0,
    left: 0,
    mode: 'create',
    defaultName: 'Page 1',
    isAuthenticated: true,
    onSave: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
  };
  return render(
    <I18nContext.Provider value={i18nValue}>
      <BookmarkPrompt {...defaultProps} {...props} />
    </I18nContext.Provider>
  );
};

beforeEach(() => vi.clearAllMocks());

test('create mode pre-fills the default name and saves on confirm', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  renderPrompt({ mode: 'create', defaultName: 'Page 42', onSave });

  const input = screen.getByRole('textbox') as HTMLInputElement;
  expect(input.value).toBe('Page 42');

  fireEvent.click(screen.getByText('bookmarks.save'));
  expect(onSave).toHaveBeenCalledWith('Page 42');
});

test('create mode blocks save when the name is emptied', () => {
  const onSave = vi.fn();
  renderPrompt({ mode: 'create', defaultName: 'Page 42', onSave });

  const input = screen.getByRole('textbox');
  fireEvent.change(input, { target: { value: '   ' } });
  fireEvent.click(screen.getByText('bookmarks.save'));

  expect(onSave).not.toHaveBeenCalled();
});

test('edit mode shows rename and delete actions', () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onDelete = vi.fn().mockResolvedValue(undefined);
  renderPrompt({ mode: 'edit', defaultName: 'Existing name', onSave, onDelete });

  fireEvent.click(screen.getByText('bookmarks.delete'));
  expect(onDelete).toHaveBeenCalled();
});

test('guests see a sign-in prompt instead of the name form', () => {
  renderPrompt({ isAuthenticated: false });

  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(screen.getByText('bookmarks.signInToSave')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/BookmarkPrompt.test.tsx`
Expected: FAIL — `Cannot find module '@/src/components/reader/BookmarkPrompt'`.

- [ ] **Step 3: Implement `BookmarkPrompt`**

Create `apps/frontend/src/components/reader/BookmarkPrompt.tsx`:

```tsx
import { Bookmark as BookmarkIcon, Trash2 } from 'lucide-react';
import React from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { OAuthButtonGroup } from '../auth/AuthButton';

interface BookmarkPromptProps {
  top: number;
  left: number;
  mode: 'create' | 'edit';
  defaultName: string;
  isAuthenticated: boolean;
  onSave: (name: string) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

export const BookmarkPrompt: React.FC<BookmarkPromptProps> = ({
  top, left, mode, defaultName, isAuthenticated, onSave, onDelete, onClose,
}) => {
  const { t } = useI18n();
  const [name, setName] = React.useState(defaultName);

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    await onSave(trimmed);
    onClose();
  };

  const handleDelete = async () => {
    await onDelete?.();
    onClose();
  };

  return createPortal(
    <div
      style={{ position: 'fixed', top, left, transform: 'translateX(-50%)' }}
      className="z-[260] w-72 bg-white dark:bg-slate-900 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 rounded-2xl shadow-2xl p-4"
    >
      {isAuthenticated ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-[#0369a1] dark:text-[#38bdf8] text-sm font-bold">
            <BookmarkIcon size={16} />
            {t(mode === 'create' ? 'bookmarks.newBookmark' : 'bookmarks.editBookmark')}
          </div>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 rounded-xl border border-[#0369a1]/20 dark:border-[#38bdf8]/20 bg-white dark:bg-slate-800 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8]"
            autoFocus
          />
          <div className="flex items-center justify-between gap-2">
            {mode === 'edit' && onDelete && (
              <button
                onClick={handleDelete}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 text-xs font-bold uppercase"
              >
                <Trash2 size={14} /> {t('bookmarks.delete')}
              </button>
            )}
            <div className="flex items-center gap-2 ms-auto">
              <button onClick={onClose} className="px-3 py-1.5 rounded-xl text-slate-400 dark:text-slate-500 text-xs font-bold uppercase">
                {t('common.cancel')}
              </button>
              <button
                onClick={handleSave}
                className="px-3 py-1.5 rounded-xl bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 text-xs font-bold uppercase"
              >
                {t('bookmarks.save')}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-3 text-center">
          <p className="text-sm text-[#1a1a1a] dark:text-slate-100">{t('bookmarks.signInToSave')}</p>
          <OAuthButtonGroup align="down" side="center" />
        </div>
      )}
    </div>,
    document.body
  );
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/BookmarkPrompt.test.tsx`
Expected: all tests PASS.

- [ ] **Step 5: Write the failing `PageItem` bookmark tests**

In `apps/frontend/src/tests/components/reader/PageItem.test.tsx`, extend the `useAuth` mock (Step: change the top-level `vi.mock('@/src/hooks/useAuth', ...)` block to also export `useAuth`, and set a default in `beforeEach`):

```typescript
vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(),
  useIsEditor: vi.fn(),
  useIsAdmin: vi.fn(),
}));
```

```typescript
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(true);
  vi.mocked(AuthModule.useAuth).mockReturnValue({ isAuthenticated: true } as any);
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('open', vi.fn());
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
  Range.prototype.getBoundingClientRect = function (this: Range) {
    return { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON() {} } as DOMRect;
  };
});
```

Add new tests at the end of the file:

```typescript
test('PageItem shows an outline bookmark icon for readers when the page has no bookmark', () => {
  renderPageItem({ page: { ...mockPage, pageNumber: 5 }, bookmarks: [] });
  expect(screen.getByTitle('bookmarks.bookmarkPage')).toBeInTheDocument();
});

test('PageItem shows a filled bookmark icon when the page already has a whole-page bookmark', () => {
  renderPageItem({
    page: { ...mockPage, pageNumber: 5 },
    bookmarks: [{ id: 'bm1', bookId: 'book-1', bookTitle: 'B', pageNumber: 5, name: 'N', quoteText: null, createdAt: 'now' }],
  });
  expect(screen.getByTitle('bookmarks.editBookmarkTitle')).toBeInTheDocument();
});

test('PageItem bookmark icon is visible for non-editor readers (unlike the editor toolbar)', () => {
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(false);
  renderPageItem({ page: { ...mockPage, pageNumber: 5 }, bookmarks: [] });
  expect(screen.getByTitle('bookmarks.bookmarkPage')).toBeInTheDocument();
});

test('PageItem clicking the bookmark icon opens the create-bookmark prompt', () => {
  renderPageItem({ page: { ...mockPage, pageNumber: 5 }, bookmarks: [] });
  fireEvent.click(screen.getByTitle('bookmarks.bookmarkPage'));
  expect(screen.getByText('bookmarks.newBookmark')).toBeInTheDocument();
});

test('PageItem saving the create-bookmark prompt calls onCreateBookmark with the page number', async () => {
  const onCreateBookmark = vi.fn().mockResolvedValue(undefined);
  renderPageItem({ page: { ...mockPage, pageNumber: 5 }, bookmarks: [], onCreateBookmark });

  fireEvent.click(screen.getByTitle('bookmarks.bookmarkPage'));
  fireEvent.click(screen.getByText('bookmarks.save'));

  expect(onCreateBookmark).toHaveBeenCalledWith(5, 'chat.pageNumber', undefined);
});

test('PageItem shows a bookmark button near a text selection, alongside share', () => {
  renderPageItem({
    page: { ...mockPage, text: 'Hello world example text', pageNumber: 5 },
    bookId: 'book-1',
    bookmarks: [],
  });

  const contentParagraph = screen.getByText(/Hello world example text/);
  const textNode = contentParagraph.firstChild!;
  const range = document.createRange();
  range.setStart(textNode, 6);
  range.setEnd(textNode, 11);
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
  fireEvent(document, new Event('selectionchange'));

  expect(screen.getByTitle('share.shareQuote')).toBeInTheDocument();
  expect(screen.getByTitle('bookmarks.bookmarkQuote')).toBeInTheDocument();

  fireEvent.click(screen.getByTitle('bookmarks.bookmarkQuote'));
  expect(screen.getByText('bookmarks.newBookmark')).toBeInTheDocument();
});

test('PageItem guests see the sign-in prompt when tapping the bookmark icon', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({ isAuthenticated: false } as any);
  renderPageItem({ page: { ...mockPage, pageNumber: 5 }, bookmarks: [] });

  fireEvent.click(screen.getByTitle('bookmarks.bookmarkPage'));
  expect(screen.getByText('bookmarks.signInToSave')).toBeInTheDocument();
});
```

Note: `chat.pageNumber` is the mocked `t()`'s literal echo of the translation key used to build the default bookmark name (the test's `i18nValue.t` returns the key itself, not an interpolated string) — the real app renders an actual page label there; the test only needs to assert the default-name plumbing reaches `onCreateBookmark` unmodified.

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/PageItem.test.tsx`
Expected: FAIL — no element with title `bookmarks.bookmarkPage` etc. (feature not implemented yet).

- [ ] **Step 7: Add bookmark props and UI to `PageItem`**

In `apps/frontend/src/components/reader/PageItem.tsx`:

Add to the imports:

```typescript
import { Bookmark as BookmarkIcon, BookmarkCheck as BookmarkFilledIcon, Edit3, ListTree, ListX, Loader2, RotateCcw, Save, Share2, Sparkles } from 'lucide-react';
import { useAuth, useIsEditor } from '../../hooks/useAuth';
import { Bookmark } from '@shared/types';
import { BookmarkPrompt } from './BookmarkPrompt';
```

(Remove the old standalone `BookmarkCheck` import name — it's now aliased `BookmarkFilledIcon` and reused for the filled bookmark state instead of only the editor's "Set as Page 1" button, so update that button's icon reference too: `<BookmarkFilledIcon size={14} />` in the existing `onSetStartPage` button, `PageItem.tsx:118`.)

Add to `PageItemProps`:

```typescript
  bookmarks?: Bookmark[];
  onCreateBookmark?: (pageNumber: number, name: string, quoteText?: string) => Promise<void>;
  onRenameBookmark?: (id: string, name: string) => Promise<void>;
  onDeleteBookmark?: (id: string) => Promise<void>;
```

Destructure them in the component signature:

```typescript
  bookId, bookTitle, bookAuthor, highlightQuote, onHighlightApplied,
  bookmarks = [], onCreateBookmark, onRenameBookmark, onDeleteBookmark,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const isEditor = useIsEditor();
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const contentRef = React.useRef<HTMLDivElement>(null);
  const [shareState, setShareState] = React.useState<{ content: string; quote?: string } | null>(null);
  const [bookmarkPrompt, setBookmarkPrompt] = React.useState<{
    top: number; left: number; mode: 'create' | 'edit'; defaultName: string; quoteText?: string; existing?: Bookmark;
  } | null>(null);

  const pageBookmark = bookmarks.find(b => b.pageNumber === page.pageNumber && !b.quoteText);
```

Add the whole-page bookmark icon next to the existing share button (in the `<div className="flex items-center gap-3">` block, before the share button):

```tsx
          <button
            onClick={(e) => {
              const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
              if (pageBookmark) {
                setBookmarkPrompt({ top: rect.bottom + 8, left: rect.left, mode: 'edit', defaultName: pageBookmark.name, existing: pageBookmark });
              } else {
                setBookmarkPrompt({
                  top: rect.bottom + 8,
                  left: rect.left,
                  mode: 'create',
                  defaultName: t('chat.pageNumber', { page: page.displayPageNumber || page.display_page_number || page.pageNumber }),
                });
              }
            }}
            title={pageBookmark ? t('bookmarks.editBookmarkTitle') : t('bookmarks.bookmarkPage')}
            className={`flex items-center justify-center h-8 w-8 rounded-lg transition-all ${pageBookmark ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950' : 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950'} ${isActive ? 'opacity-100' : 'opacity-0'} sm:group-hover:opacity-100`}
          >
            {pageBookmark ? <BookmarkFilledIcon size={14} /> : <BookmarkIcon size={14} />}
          </button>
```

Add the passage-bookmark button next to the existing quote-share floating button (right after the `{textSelection && createPortal(...share button...)}` block):

```tsx
      {textSelection && createPortal(
        <button
          onClick={() => {
            const rect = { top: textSelection.top - 44, left: textSelection.left + 48 };
            setBookmarkPrompt({
              top: rect.top,
              left: rect.left,
              mode: 'create',
              defaultName: textSelection.text.slice(0, 40),
              quoteText: textSelection.text,
            });
            window.getSelection()?.removeAllRanges();
          }}
          title={t('bookmarks.bookmarkQuote')}
          style={{
            position: 'fixed',
            top: textSelection.top - 44,
            left: textSelection.left + 48,
            transform: 'translateX(-50%)',
          }}
          className="z-[250] flex items-center justify-center h-9 w-9 rounded-full bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-lg"
        >
          <BookmarkIcon size={16} />
        </button>,
        document.body
      )}
```

Add the `BookmarkPrompt` render, alongside the existing `{shareState && (...)}` block:

```tsx
      {bookmarkPrompt && (
        <BookmarkPrompt
          top={bookmarkPrompt.top}
          left={bookmarkPrompt.left}
          mode={bookmarkPrompt.mode}
          defaultName={bookmarkPrompt.defaultName}
          isAuthenticated={isAuthenticated}
          onSave={async (name) => {
            if (bookmarkPrompt.mode === 'edit' && bookmarkPrompt.existing) {
              await onRenameBookmark?.(bookmarkPrompt.existing.id, name);
            } else {
              await onCreateBookmark?.(page.pageNumber, name, bookmarkPrompt.quoteText);
            }
          }}
          onDelete={bookmarkPrompt.mode === 'edit' && bookmarkPrompt.existing
            ? async () => { await onDeleteBookmark?.(bookmarkPrompt.existing!.id); }
            : undefined}
          onClose={() => setBookmarkPrompt(null)}
        />
      )}
```

- [ ] **Step 8: Thread the new props through `VirtualScrollReader` and `ReaderView`**

In `apps/frontend/src/components/reader/VirtualScrollReader.tsx`, add to `VirtualScrollReaderProps`:

```typescript
  bookmarks?: any[];
  onCreateBookmark?: (pageNumber: number, name: string, quoteText?: string) => Promise<void>;
  onRenameBookmark?: (id: string, name: string) => Promise<void>;
  onDeleteBookmark?: (id: string) => Promise<void>;
```

destructure them in the component signature (next to `onTocPageClick`):

```typescript
  onTocPageClick,
  bookmarks = [],
  onCreateBookmark,
  onRenameBookmark,
  onDeleteBookmark,
}) => {
```

and pass them to the `<PageItem>` render (next to `onTocPageClick={handleTocPageClick}`):

```tsx
                  onTocPageClick={handleTocPageClick}
                  bookmarks={bookmarks}
                  onCreateBookmark={onCreateBookmark}
                  onRenameBookmark={onRenameBookmark}
                  onDeleteBookmark={onDeleteBookmark}
```

In `apps/frontend/src/components/reader/ReaderView.tsx`, add the `useBookmarks` hook and pass its methods to both render paths. Add the import:

```typescript
import { useBookmarks } from '../../hooks/useBookmarks';
```

Add the hook call near the top of the component body (after `selectedBook` is destructured from `useAppContext()`):

```typescript
  const { bookmarks, create: createBookmark, rename: renameBookmark, remove: removeBookmark } = useBookmarks(selectedBook?.id);
```

Pass to the `VirtualScrollReader` render (next to `onTocPageClick={handleTocPageClick}`):

```tsx
                onTocPageClick={handleTocPageClick}
                bookmarks={bookmarks}
                onCreateBookmark={createBookmark}
                onRenameBookmark={renameBookmark}
                onDeleteBookmark={removeBookmark}
```

Pass to the non-virtual-scroll `<PageItem>` render (next to `onTocPageClick={handleTocPageClick}` in that branch — same props, same values):

```tsx
                        onTocPageClick={handleTocPageClick}
                        bookmarks={bookmarks}
                        onCreateBookmark={createBookmark}
                        onRenameBookmark={renameBookmark}
                        onDeleteBookmark={removeBookmark}
```

`ReaderView` now calls `useBookmarks(selectedBook.id)` unconditionally on mount, which calls `PersistenceService.listBookmarks`. `apps/frontend/src/tests/components/reader/ReaderView.test.tsx`'s existing `vi.mock('@/src/services/persistenceService', ...)` predates this hook and only stubs `getBookContent`/`getBookPages`/`downloadBook` — since its `useAuth` mock already sets `isAuthenticated: true`, `useBookmarks`'s effect fires for real and throws `TypeError: PersistenceService.listBookmarks is not a function` as an unhandled rejection during every test in that file (tests still pass, but the rejections are real noise masking future failures). Fix by extending that mock:

```typescript
vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookContent: vi.fn(),
    getBookPages: vi.fn(),
    downloadBook: vi.fn(),
    listBookmarks: vi.fn().mockResolvedValue([]),
    createBookmark: vi.fn(),
    renameBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
  }
}));
```

- [ ] **Step 9: Add the new i18n keys**

In `apps/frontend/src/locales/en.json`, add a new top-level `"bookmarks"` object (after `"share"`):

```json
  "bookmarks": {
    "bookmarkPage": "Bookmark this page",
    "editBookmarkTitle": "Edit bookmark",
    "bookmarkQuote": "Bookmark this passage",
    "newBookmark": "New bookmark",
    "editBookmark": "Edit bookmark",
    "save": "Save",
    "delete": "Delete",
    "signInToSave": "Sign in to save bookmarks"
  },
```

In `apps/frontend/src/locales/ug.json`, add the same key set with draft Uyghur text (needs native-speaker review per Global Constraints):

```json
  "bookmarks": {
    "bookmarkPage": "بۇ بەتنى بەلگىلەش",
    "editBookmarkTitle": "بەلگىنى تەھرىرلەش",
    "bookmarkQuote": "بۇ ئىبارىنى بەلگىلەش",
    "newBookmark": "يېڭى بەلگە",
    "editBookmark": "بەلگىنى تەھرىرلەش",
    "save": "ساقلاش",
    "delete": "ئۆچۈرۈش",
    "signInToSave": "بەلگە ساقلاش ئۈچۈن كىرىڭ"
  },
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/PageItem.test.tsx src/tests/components/reader/BookmarkPrompt.test.tsx`
Expected: all tests PASS.

- [ ] **Step 11: Rebuild and manually verify**

Run: `./deploy/local/rebuild-and-restart.sh frontend`

Open http://localhost:30080, sign in, open a book, hover a page: confirm an outline bookmark icon appears next to the existing share icon; click it, confirm the name prompt appears pre-filled with a page label; save; confirm the icon becomes filled. Select a sentence; confirm a second floating button (bookmark icon) appears next to the quote-share button; use it to save a passage bookmark.

- [ ] **Step 12: Commit**

```bash
git add apps/frontend/src/components/reader/BookmarkPrompt.tsx apps/frontend/src/components/reader/PageItem.tsx apps/frontend/src/components/reader/VirtualScrollReader.tsx apps/frontend/src/components/reader/ReaderView.tsx apps/frontend/src/tests/components/reader/BookmarkPrompt.test.tsx apps/frontend/src/tests/components/reader/PageItem.test.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "feat(reader): add whole-page and passage bookmark creation UI"
```

---

### Task 8: Per-book bookmarks drawer

**Files:**
- Create: `apps/frontend/src/components/reader/BookmarksDrawer.tsx`
- Test: `apps/frontend/src/tests/components/reader/BookmarksDrawer.test.tsx`
- Modify: `apps/frontend/src/components/reader/ReaderView.tsx`
- Modify: `apps/frontend/src/locales/en.json`, `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Consumes: `bookmarks`, `renameBookmark`, `removeBookmark` (Task 7's `useBookmarks(selectedBook?.id)` call, already in `ReaderView`).
- Produces: `BookmarksDrawer` component with props `{ bookmarks: Bookmark[]; onJumpTo: (pageNumber: number, quoteText?: string) => void; onRename: (id: string, name: string) => Promise<void>; onDelete: (id: string) => Promise<void>; onClose: () => void; }`. A new toolbar icon in `ReaderView` toggles it.

- [ ] **Step 1: Write the failing drawer tests**

Create `apps/frontend/src/tests/components/reader/BookmarksDrawer.test.tsx`:

```typescript
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { BookmarksDrawer } from '@/src/components/reader/BookmarksDrawer';
import { I18nContext } from '@/src/i18n/I18nContext';

const i18nValue = { language: 'en' as const, setLanguage: vi.fn(), t: (key: string) => key };

const bookmarks = [
  { id: 'bm1', bookId: 'b1', bookTitle: 'B', pageNumber: 10, name: 'Chapter 2', quoteText: null, createdAt: 'now' },
  { id: 'bm2', bookId: 'b1', bookTitle: 'B', pageNumber: 3, name: 'Good line', quoteText: 'a nice passage', createdAt: 'now' },
];

const renderDrawer = (props: Partial<React.ComponentProps<typeof BookmarksDrawer>> = {}) => {
  const defaultProps: React.ComponentProps<typeof BookmarksDrawer> = {
    bookmarks,
    onJumpTo: vi.fn(),
    onRename: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
  };
  return render(
    <I18nContext.Provider value={i18nValue}>
      <BookmarksDrawer {...defaultProps} {...props} />
    </I18nContext.Provider>
  );
};

beforeEach(() => vi.clearAllMocks());

test('lists bookmarks sorted by page number ascending', () => {
  renderDrawer();
  const names = screen.getAllByTestId('bookmark-drawer-name').map(el => el.textContent);
  expect(names).toEqual(['Good line', 'Chapter 2']);
});

test('shows a quote snippet for passage bookmarks only', () => {
  renderDrawer();
  expect(screen.getByText('a nice passage')).toBeInTheDocument();
});

test('clicking an entry jumps to its page and quote', () => {
  const onJumpTo = vi.fn();
  renderDrawer({ onJumpTo });
  fireEvent.click(screen.getByText('Good line'));
  expect(onJumpTo).toHaveBeenCalledWith(3, 'a nice passage');
});

test('deleting an entry calls onDelete with its id', () => {
  const onDelete = vi.fn().mockResolvedValue(undefined);
  renderDrawer({ onDelete });
  fireEvent.click(screen.getAllByTitle('bookmarks.delete')[0]);
  expect(onDelete).toHaveBeenCalledWith('bm2');
});

test('renaming an entry switches it to an input and calls onRename on save', () => {
  const onRename = vi.fn().mockResolvedValue(undefined);
  renderDrawer({ onRename });

  fireEvent.click(screen.getAllByTitle('bookmarks.rename')[0]);
  const input = screen.getByDisplayValue('Good line');
  fireEvent.change(input, { target: { value: 'Better line' } });
  fireEvent.click(screen.getByText('bookmarks.save'));

  expect(onRename).toHaveBeenCalledWith('bm2', 'Better line');
});

test('clicking an entry while renaming does not jump to its page', () => {
  const onJumpTo = vi.fn();
  renderDrawer({ onJumpTo });

  fireEvent.click(screen.getAllByTitle('bookmarks.rename')[0]);
  fireEvent.click(screen.getByDisplayValue('Good line'));

  expect(onJumpTo).not.toHaveBeenCalled();
});

test('shows an empty state when there are no bookmarks', () => {
  renderDrawer({ bookmarks: [] });
  expect(screen.getByText('bookmarks.emptyForBook')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/BookmarksDrawer.test.tsx`
Expected: FAIL — `Cannot find module '@/src/components/reader/BookmarksDrawer'`.

- [ ] **Step 3: Implement `BookmarksDrawer`**

Create `apps/frontend/src/components/reader/BookmarksDrawer.tsx`:

```tsx
import { Bookmark as BookmarkIcon, Edit3, Trash2, X } from 'lucide-react';
import { Bookmark } from '@shared/types';
import React from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';

interface BookmarksDrawerProps {
  bookmarks: Bookmark[];
  onJumpTo: (pageNumber: number, quoteText?: string) => void;
  onRename: (id: string, name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onClose: () => void;
}

export const BookmarksDrawer: React.FC<BookmarksDrawerProps> = ({ bookmarks, onJumpTo, onRename, onDelete, onClose }) => {
  const { t } = useI18n();
  const sorted = [...bookmarks].sort((a, b) => a.pageNumber - b.pageNumber);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingName, setEditingName] = React.useState('');

  const startEditing = (bookmark: Bookmark) => {
    setEditingId(bookmark.id);
    setEditingName(bookmark.name);
  };

  const saveEditing = async () => {
    const trimmed = editingName.trim();
    if (editingId && trimmed) {
      await onRename(editingId, trimmed);
    }
    setEditingId(null);
  };

  return createPortal(
    <div className="fixed inset-0 z-[300] flex justify-end bg-black/20" onClick={onClose}>
      <div
        className="h-full w-full max-w-sm bg-white dark:bg-slate-900 shadow-2xl p-5 overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-[#1a1a1a] dark:text-slate-100 flex items-center gap-2">
            <BookmarkIcon size={18} className="text-[#0369a1] dark:text-[#38bdf8]" />
            {t('bookmarks.drawerTitle')}
          </h3>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X size={18} />
          </button>
        </div>

        {sorted.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-10">{t('bookmarks.emptyForBook')}</p>
        ) : (
          <ul className="space-y-2">
            {sorted.map((bookmark) => (
              <li key={bookmark.id} className="rounded-xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10">
                {editingId === bookmark.id ? (
                  <div className="p-3 space-y-2">
                    <input
                      type="text"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      className="w-full px-2 py-1.5 rounded-lg border border-[#0369a1]/20 dark:border-[#38bdf8]/20 bg-white dark:bg-slate-800 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none"
                      autoFocus
                    />
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setEditingId(null)} className="px-2 py-1 rounded-lg text-slate-400 text-xs font-bold uppercase">
                        {t('common.cancel')}
                      </button>
                      <button onClick={saveEditing} className="px-2 py-1 rounded-lg bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 text-xs font-bold uppercase">
                        {t('bookmarks.save')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => onJumpTo(bookmark.pageNumber, bookmark.quoteText ?? undefined)}
                      className="w-full text-start p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span data-testid="bookmark-drawer-name" className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100">
                          {bookmark.name}
                        </span>
                        <span className="text-xs text-slate-400 dark:text-slate-500">{bookmark.pageNumber}</span>
                      </div>
                      {bookmark.quoteText && (
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">{bookmark.quoteText}</p>
                      )}
                    </button>
                    <div className="flex justify-end gap-1 px-3 pb-2">
                      <button
                        onClick={() => startEditing(bookmark)}
                        title={t('bookmarks.rename')}
                        className="p-1.5 rounded-lg text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        onClick={() => onDelete(bookmark.id)}
                        title={t('bookmarks.delete')}
                        className="p-1.5 rounded-lg text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>,
    document.body
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/BookmarksDrawer.test.tsx`
Expected: all tests PASS.

- [ ] **Step 5: Wire the drawer toggle into `ReaderView`'s toolbar**

In `apps/frontend/src/components/reader/ReaderView.tsx`, add state and the toolbar icon. Add near the other reader UI state (e.g. `showFontSlider`):

```typescript
  const [showBookmarksDrawer, setShowBookmarksDrawer] = useState(false);
```

Add the import:

```typescript
import { BookmarksDrawer } from './BookmarksDrawer';
```

and add `Bookmark as BookmarkIcon` to the existing `lucide-react` import at the top of the file.

Add the toolbar button, in the same row as the font-size button (right before it, so order reads: bookmarks, font size, fullscreen, close):

```tsx
              <button
                onClick={() => setShowBookmarksDrawer(true)}
                title={t('bookmarks.drawerTitle')}
                className="p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all bg-white/60 dark:bg-slate-800/80 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10"
              >
                <BookmarkIcon size={18} className="sm:w-5 sm:h-5" />
              </button>
```

Add the drawer render at the end of the component's JSX (a sibling of the other portal-rendered overlays, e.g. right before the closing tag of the outermost reader `<div>`):

```tsx
      {showBookmarksDrawer && (
        <BookmarksDrawer
          bookmarks={bookmarks}
          onRename={renameBookmark}
          onDelete={removeBookmark}
          onJumpTo={(pageNumber, quoteText) => {
            setCurrentPage(pageNumber);
            if (quoteText) setPendingQuoteHighlight(quoteText);
            setShowBookmarksDrawer(false);
          }}
          onClose={() => setShowBookmarksDrawer(false)}
        />
      )}
```

- [ ] **Step 6: Add the new i18n keys**

In `apps/frontend/src/locales/en.json`, extend the `"bookmarks"` object added in Task 7:

```json
    "drawerTitle": "Bookmarks in this book",
    "emptyForBook": "No bookmarks in this book yet",
    "rename": "Rename"
```

In `apps/frontend/src/locales/ug.json` (draft, needs review):

```json
    "drawerTitle": "بۇ كىتابتىكى بەلگىلەر",
    "emptyForBook": "بۇ كىتابتا تېخى بەلگە يوق",
    "rename": "ئات ئۆزگەرتىش"
```

- [ ] **Step 7: Rebuild and manually verify**

Run: `./deploy/local/rebuild-and-restart.sh frontend`

Open a book with at least one bookmark saved (from Task 7's manual check), click the new bookmarks toolbar icon, confirm the drawer lists it sorted by page, clicking it scrolls to that page (and highlights the quote if it's a passage bookmark), and delete works.

- [ ] **Step 8: Commit**

```bash
git add apps/frontend/src/components/reader/BookmarksDrawer.tsx apps/frontend/src/components/reader/ReaderView.tsx apps/frontend/src/tests/components/reader/BookmarksDrawer.test.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "feat(reader): add per-book bookmarks drawer"
```

---

### Task 9: Library tabs — scaffolding + Continue Reading

**Files:**
- Modify: `apps/frontend/src/context/AppContext.tsx`
- Modify: `apps/frontend/src/components/library/LibraryView.tsx`
- Create: `apps/frontend/src/components/library/ContinueReadingTab.tsx`
- Test: `apps/frontend/src/tests/components/library/ContinueReadingTab.test.tsx`
- Modify: `apps/frontend/src/tests/components/library/LibraryView.test.tsx`
- Modify: `apps/frontend/src/locales/en.json`, `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Consumes: `PersistenceService.listReadingProgress` (Task 4), `activeTab`/`setActiveTab` (existing, `AppContext`), `bookActions.openReader` (Task 5), `GuestAuthWall` (existing), `BookCard` (existing).
- Produces: `LibraryView` renders a 3-button tab row (`all-books` default / `continue-reading` / `bookmarks`); `/library/continue-reading` and `/library/bookmarks` URLs route to `view: 'library'`, matching the existing `/admin/<tab>` convention. `ContinueReadingTab` component with an internal client-side filter input.

- [ ] **Step 1: Extend `AppContext`'s path routing for library sub-tabs**

In `apps/frontend/src/context/AppContext.tsx`, in `parsePath`, change:

```typescript
    if (viewPortion === 'library') view = 'library';
```

to:

```typescript
    if (viewPortion === 'library') {
      view = 'library';
      tab = parts[1] || 'all-books';
    }
```

In `getPathFromView`, add a `library` branch before the generic fallback:

```typescript
  const getPathFromView = (v: string, t?: string) => {
    if (v === 'home') return '/';
    if (v === 'global-chat') return '/chat';
    if (v === 'admin' && t && t !== 'books') return `/admin/${t}`;
    if (v === 'library' && t && t !== 'all-books') return `/library/${t}`;
    return `/${v}`;
  };
```

In `setView`, the existing history-push call already passes `activeTab` as the tab for any view — no change needed there since it already reads `getPathFromView(newView, newView === 'admin' ? activeTab : undefined)`. Update this to also cover `library`:

```typescript
        const path = getPathFromView(newView, (newView === 'admin' || newView === 'library') ? activeTab : undefined);
```

Since navigating to `library` via the Navbar doesn't reset `activeTab` today, add a reset so it doesn't carry over a stale admin sub-tab. In `setView`, right before `setViewInternal(newView)`, add:

```typescript
      if (newView === 'library' && view !== 'reader') {
        setActiveTabInternal('all-books');
      }
```

- [ ] **Step 2: Write the failing `LibraryView` tab tests**

`apps/frontend/src/tests/components/library/LibraryView.test.tsx` currently mocks `useAppContext` per-test with `vi.mocked(AppContextModule.useAppContext).mockReturnValue({...} as any)` and has no shared render helper — each test builds its own context value inline. Add `fireEvent` to the existing `@testing-library/react` import, add `activeTab`/`setActiveTab` to both existing tests' mocked context values (so the tab bar has a defined active tab), and add two new tests:

```typescript
import { LibraryView } from '@/src/components/library/LibraryView';
import * as AppContextModule from '@/src/context/AppContext';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { Book } from '@shared/types';
import { fireEvent, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
```

Update the two existing `mockReturnValue({...})` calls to include `activeTab: 'all-books', setActiveTab: vi.fn(),`. Then add:

```typescript
test('renders the 3 library tabs and defaults to All Books', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'all-books',
    setActiveTab: vi.fn(),
  } as any);

  render(<LibraryView />);

  expect(screen.getByText('library.tabs.allBooks')).toBeInTheDocument();
  expect(screen.getByText('library.tabs.continueReading')).toBeInTheDocument();
  expect(screen.getByText('library.tabs.bookmarks')).toBeInTheDocument();
});

test('clicking the Continue Reading tab calls setActiveTab', () => {
  const setActiveTab = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'all-books',
    setActiveTab,
  } as any);

  render(<LibraryView />);
  fireEvent.click(screen.getByText('library.tabs.continueReading'));

  expect(setActiveTab).toHaveBeenCalledWith('continue-reading');
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/library/LibraryView.test.tsx`
Expected: FAIL — tab labels not found (no tab bar exists yet).

- [ ] **Step 4: Add the tab bar to `LibraryView`**

In `apps/frontend/src/components/library/LibraryView.tsx`, add `activeTab`/`setActiveTab` to the destructured `useAppContext()` call:

```typescript
  const {
    sortedBooks: books,
    totalBooks,
    isLoading: isInitialLoading,
    isLoadingMoreShelf: isLoadingMore,
    hasMoreShelf: hasMore,
    bookActions,
    loaderRef,
    loadMoreShelf: loadMore,
    activeTab,
    setActiveTab,
  } = useAppContext();
```

Add the import:

```typescript
import { ContinueReadingTab } from './ContinueReadingTab';
```

Add the tab bar right after the header `</div>` and before the `{/* Grid Section */}` comment:

```tsx
      <div className="flex items-center gap-2 border-b border-[#0369a1]/10 dark:border-[#38bdf8]/10 pb-0">
        {([
          { key: 'all-books', label: t('library.tabs.allBooks') },
          { key: 'continue-reading', label: t('library.tabs.continueReading') },
          { key: 'bookmarks', label: t('library.tabs.bookmarks') },
        ] as const).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`px-4 py-2.5 text-sm font-bold rounded-t-xl transition-all ${
              (activeTab === key || (key === 'all-books' && activeTab !== 'continue-reading' && activeTab !== 'bookmarks'))
                ? 'bg-white dark:bg-slate-900 text-[#0369a1] dark:text-[#38bdf8] border border-b-0 border-[#0369a1]/10 dark:border-[#38bdf8]/10'
                : 'text-slate-400 dark:text-slate-500 hover:text-[#0369a1] dark:hover:text-[#38bdf8]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
```

Wrap the existing grid/empty/infinite-scroll JSX (everything from `{/* Grid Section */}` through the `{/* Infinite Scroll Trigger */}` block) in a conditional, and add the two new tab bodies as siblings:

```tsx
      {(activeTab !== 'continue-reading' && activeTab !== 'bookmarks') && (
        <>
          {/* Grid Section */}
          <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-3 sm:gap-x-8 gap-y-8 sm:gap-y-12 justify-items-center">
            {/* ...unchanged existing content... */}
          </div>

          {/* Infinite Scroll Trigger */}
          <div ref={loaderRef as any} className="h-64 flex flex-col items-center justify-center gap-6">
            {/* ...unchanged existing content... */}
          </div>
        </>
      )}

      {activeTab === 'continue-reading' && (
        <ContinueReadingTab onOpenBook={(bookId) => bookActions.openReader({ id: bookId })} />
      )}
```

(The `activeTab === 'bookmarks'` branch is added in Task 10.)

- [ ] **Step 5: Write the failing `ContinueReadingTab` tests**

Create `apps/frontend/src/tests/components/library/ContinueReadingTab.test.tsx`:

```typescript
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { ContinueReadingTab } from '@/src/components/library/ContinueReadingTab';
import { I18nContext } from '@/src/i18n/I18nContext';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: { listReadingProgress: vi.fn() },
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({ isAuthenticated: true })),
}));

import { useAuth } from '@/src/hooks/useAuth';

const i18nValue = { language: 'en' as const, setLanguage: vi.fn(), t: (key: string) => key };

const items = [
  { bookId: 'b1', bookTitle: 'Alpha Book', bookCoverUrl: null, pageNumber: 10, updatedAt: '2026-09-01' },
  { bookId: 'b2', bookTitle: 'Beta Story', bookCoverUrl: null, pageNumber: 3, updatedAt: '2026-09-05' },
];

const renderTab = (onOpenBook = vi.fn()) => render(
  <I18nContext.Provider value={i18nValue}>
    <ContinueReadingTab onOpenBook={onOpenBook} />
  </I18nContext.Provider>
);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: true } as any);
});

test('renders each book with progress', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(items);
  renderTab();
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());
  expect(screen.getByText('Beta Story')).toBeInTheDocument();
});

test('filters the list by title as the user types', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(items);
  renderTab();
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());

  fireEvent.change(screen.getByPlaceholderText('library.continueReading.searchPlaceholder'), { target: { value: 'beta' } });

  expect(screen.queryByText('Alpha Book')).not.toBeInTheDocument();
  expect(screen.getByText('Beta Story')).toBeInTheDocument();
});

test('clicking a book calls onOpenBook with its id', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(items);
  const onOpenBook = vi.fn();
  renderTab(onOpenBook);
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());

  fireEvent.click(screen.getByText('Alpha Book'));
  expect(onOpenBook).toHaveBeenCalledWith('b1');
});

test('shows an empty state when there is no reading history', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue([]);
  renderTab();
  await waitFor(() => expect(screen.getByText('library.continueReading.empty')).toBeInTheDocument());
});

test('shows the guest auth wall instead of fetching for signed-out users', () => {
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: false } as any);
  renderTab();
  expect(screen.getByTestId('guest-auth-wall')).toBeInTheDocument();
  expect(PersistenceService.listReadingProgress).not.toHaveBeenCalled();
});
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/library/ContinueReadingTab.test.tsx`
Expected: FAIL — `Cannot find module '@/src/components/library/ContinueReadingTab'`.

- [ ] **Step 7: Implement `ContinueReadingTab`**

Create `apps/frontend/src/components/library/ContinueReadingTab.tsx`:

```tsx
import { Search } from 'lucide-react';
import { ReadingProgressEntry } from '@shared/types';
import React from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { GuestAuthWall } from '../reader/GuestAuthWall';

interface ContinueReadingTabProps {
  onOpenBook: (bookId: string) => void;
}

export const ContinueReadingTab: React.FC<ContinueReadingTabProps> = ({ onOpenBook }) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const [items, setItems] = React.useState<ReadingProgressEntry[]>([]);
  const [query, setQuery] = React.useState('');

  React.useEffect(() => {
    if (!isAuthenticated) return;
    PersistenceService.listReadingProgress().then(setItems);
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return <GuestAuthWall />;
  }

  const filtered = items.filter(item =>
    (item.bookTitle || '').toLowerCase().includes(query.trim().toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="relative max-w-md">
        <Search size={16} className="absolute top-1/2 -translate-y-1/2 start-3 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('library.continueReading.searchPlaceholder')}
          className="w-full ps-9 pe-3 py-2.5 rounded-2xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 bg-white dark:bg-slate-900 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8]"
        />
      </div>

      {items.length === 0 ? (
        <p className="text-center text-slate-400 dark:text-slate-500 py-20">{t('library.continueReading.empty')}</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-6">
          {filtered.map(item => (
            <button
              key={item.bookId}
              onClick={() => onOpenBook(item.bookId)}
              className="text-start rounded-2xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 p-4 hover:shadow-lg transition-all bg-white dark:bg-slate-900"
            >
              <p className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100 truncate">{item.bookTitle}</p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                {t('chat.pageNumber', { page: item.pageNumber })}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/library/ContinueReadingTab.test.tsx src/tests/components/library/LibraryView.test.tsx`
Expected: all tests PASS.

- [ ] **Step 9: Add the new i18n keys**

In `apps/frontend/src/locales/en.json`, extend `"library"`:

```json
    "tabs": {
      "allBooks": "All Books",
      "continueReading": "Continue Reading",
      "bookmarks": "Bookmarks"
    },
    "continueReading": {
      "searchPlaceholder": "Search your books...",
      "empty": "You haven't started reading anything yet"
    },
```

In `apps/frontend/src/locales/ug.json` (draft, needs review):

```json
    "tabs": {
      "allBooks": "بارلىق كىتابلار",
      "continueReading": "ئوقۇشنى داۋاملاشتۇرۇش",
      "bookmarks": "بەلگىلەر"
    },
    "continueReading": {
      "searchPlaceholder": "كىتابلىرىڭىزنى ئىزدەڭ...",
      "empty": "سىز تېخى ھېچقانداق كىتاب ئوقۇشنى باشلىمىدىڭىز"
    },
```

- [ ] **Step 10: Rebuild and manually verify**

Run: `./deploy/local/rebuild-and-restart.sh frontend`

Sign in, read partway into a book, go to Library, confirm the "Continue Reading" tab shows it and clicking opens the reader at the right page; type in the search box and confirm it filters instantly.

- [ ] **Step 11: Commit**

```bash
git add apps/frontend/src/context/AppContext.tsx apps/frontend/src/components/library/LibraryView.tsx apps/frontend/src/components/library/ContinueReadingTab.tsx apps/frontend/src/tests/components/library/ContinueReadingTab.test.tsx apps/frontend/src/tests/components/library/LibraryView.test.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "feat(library): add Library tabs and Continue Reading tab"
```

---

### Task 10: Bookmarks tab

**Files:**
- Create: `apps/frontend/src/components/library/BookmarksTab.tsx`
- Test: `apps/frontend/src/tests/components/library/BookmarksTab.test.tsx`
- Modify: `apps/frontend/src/components/library/LibraryView.tsx`
- Modify: `apps/frontend/src/locales/en.json`, `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Consumes: `useBookmarks()` (Task 6, called with no `bookId` for the unscoped list), `GuestAuthWall` (existing).
- Produces: `BookmarksTab` component with props `{ onOpenBookmark: (bookId: string, pageNumber: number, quoteText?: string) => void }`, grouped-by-book rendering, client-side filter, inline rename/delete.

- [ ] **Step 1: Write the failing tests**

Create `apps/frontend/src/tests/components/library/BookmarksTab.test.tsx`:

```typescript
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { BookmarksTab } from '@/src/components/library/BookmarksTab';
import { I18nContext } from '@/src/i18n/I18nContext';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    listBookmarks: vi.fn(),
    createBookmark: vi.fn(),
    renameBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
  },
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({ isAuthenticated: true })),
}));

import { useAuth } from '@/src/hooks/useAuth';

const i18nValue = { language: 'en' as const, setLanguage: vi.fn(), t: (key: string) => key };

const bookmarks = [
  { id: 'bm1', bookId: 'b1', bookTitle: 'Alpha Book', pageNumber: 10, name: 'Great chapter', quoteText: null, createdAt: 'now' },
  { id: 'bm2', bookId: 'b2', bookTitle: 'Beta Story', pageNumber: 3, name: 'Nice line', quoteText: 'a quoted passage', createdAt: 'now' },
];

const renderTab = (onOpenBookmark = vi.fn()) => render(
  <I18nContext.Provider value={i18nValue}>
    <BookmarksTab onOpenBookmark={onOpenBookmark} />
  </I18nContext.Provider>
);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: true } as any);
});

test('groups bookmarks by book title', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  renderTab();
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());
  expect(screen.getByText('Beta Story')).toBeInTheDocument();
  expect(screen.getByText('Great chapter')).toBeInTheDocument();
  expect(screen.getByText('Nice line')).toBeInTheDocument();
});

test('filters by bookmark name or book title', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  renderTab();
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());

  fireEvent.change(screen.getByPlaceholderText('library.bookmarksTab.searchPlaceholder'), { target: { value: 'nice' } });

  expect(screen.queryByText('Alpha Book')).not.toBeInTheDocument();
  expect(screen.getByText('Beta Story')).toBeInTheDocument();
});

test('clicking a bookmark calls onOpenBookmark with book, page, and quote', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  const onOpenBookmark = vi.fn();
  renderTab(onOpenBookmark);
  await waitFor(() => expect(screen.getByText('Nice line')).toBeInTheDocument());

  fireEvent.click(screen.getByText('Nice line'));
  expect(onOpenBookmark).toHaveBeenCalledWith('b2', 3, 'a quoted passage');
});

test('deleting a bookmark removes it from the list', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  vi.mocked(PersistenceService.deleteBookmark).mockResolvedValue(undefined);
  renderTab();
  await waitFor(() => expect(screen.getByText('Great chapter')).toBeInTheDocument());

  fireEvent.click(screen.getAllByTitle('bookmarks.delete')[0]);

  await waitFor(() => expect(screen.queryByText('Great chapter')).not.toBeInTheDocument());
});

test('renaming a bookmark switches it to an input and saves the new name', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  vi.mocked(PersistenceService.renameBookmark).mockResolvedValue(undefined);
  renderTab();
  await waitFor(() => expect(screen.getByText('Great chapter')).toBeInTheDocument());

  fireEvent.click(screen.getAllByTitle('bookmarks.rename')[0]);
  const input = screen.getByDisplayValue('Great chapter');
  fireEvent.change(input, { target: { value: 'Even better chapter' } });
  fireEvent.click(screen.getByText('bookmarks.save'));

  await waitFor(() => expect(PersistenceService.renameBookmark).toHaveBeenCalledWith('bm1', 'Even better chapter'));
});

test('shows an empty state with no bookmarks', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([]);
  renderTab();
  await waitFor(() => expect(screen.getByText('library.bookmarksTab.empty')).toBeInTheDocument());
});

test('shows the guest auth wall for signed-out users', () => {
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: false } as any);
  renderTab();
  expect(screen.getByTestId('guest-auth-wall')).toBeInTheDocument();
  expect(PersistenceService.listBookmarks).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/library/BookmarksTab.test.tsx`
Expected: FAIL — `Cannot find module '@/src/components/library/BookmarksTab'`.

- [ ] **Step 3: Implement `BookmarksTab`**

Create `apps/frontend/src/components/library/BookmarksTab.tsx`:

```tsx
import { Edit3, Search, Trash2 } from 'lucide-react';
import React from 'react';
import { useBookmarks } from '../../hooks/useBookmarks';
import { useI18n } from '../../i18n/I18nContext';
import { GuestAuthWall } from '../reader/GuestAuthWall';
import { useAuth } from '../../hooks/useAuth';

interface BookmarksTabProps {
  onOpenBookmark: (bookId: string, pageNumber: number, quoteText?: string) => void;
}

export const BookmarksTab: React.FC<BookmarksTabProps> = ({ onOpenBookmark }) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const { bookmarks, rename, remove } = useBookmarks();
  const [query, setQuery] = React.useState('');
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingName, setEditingName] = React.useState('');

  if (!isAuthenticated) {
    return <GuestAuthWall />;
  }

  const q = query.trim().toLowerCase();
  const filtered = bookmarks.filter(b =>
    !q || b.name.toLowerCase().includes(q) || (b.bookTitle || '').toLowerCase().includes(q)
  );

  const grouped = filtered.reduce<Record<string, typeof filtered>>((acc, bookmark) => {
    const key = bookmark.bookTitle || bookmark.bookId;
    (acc[key] ||= []).push(bookmark);
    return acc;
  }, {});

  const startEditing = (id: string, currentName: string) => {
    setEditingId(id);
    setEditingName(currentName);
  };

  const saveEditing = async () => {
    const trimmed = editingName.trim();
    if (editingId && trimmed) {
      await rename(editingId, trimmed);
    }
    setEditingId(null);
  };

  return (
    <div className="space-y-6">
      <div className="relative max-w-md">
        <Search size={16} className="absolute top-1/2 -translate-y-1/2 start-3 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('library.bookmarksTab.searchPlaceholder')}
          className="w-full ps-9 pe-3 py-2.5 rounded-2xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 bg-white dark:bg-slate-900 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8]"
        />
      </div>

      {bookmarks.length === 0 ? (
        <p className="text-center text-slate-400 dark:text-slate-500 py-20">{t('library.bookmarksTab.empty')}</p>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([bookTitle, group]) => (
            <div key={bookTitle}>
              <h4 className="font-bold text-[#1a1a1a] dark:text-slate-100 mb-2">{bookTitle}</h4>
              <ul className="space-y-2">
                {group.map(bookmark => (
                  <li key={bookmark.id} className="rounded-xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 p-3">
                    {editingId === bookmark.id ? (
                      <div className="space-y-2">
                        <input
                          type="text"
                          value={editingName}
                          onChange={(e) => setEditingName(e.target.value)}
                          className="w-full px-2 py-1.5 rounded-lg border border-[#0369a1]/20 dark:border-[#38bdf8]/20 bg-white dark:bg-slate-800 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none"
                          autoFocus
                        />
                        <div className="flex justify-end gap-2">
                          <button onClick={() => setEditingId(null)} className="px-2 py-1 rounded-lg text-slate-400 text-xs font-bold uppercase">
                            {t('common.cancel')}
                          </button>
                          <button onClick={saveEditing} className="px-2 py-1 rounded-lg bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 text-xs font-bold uppercase">
                            {t('bookmarks.save')}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2">
                        <button
                          onClick={() => onOpenBookmark(bookmark.bookId, bookmark.pageNumber, bookmark.quoteText ?? undefined)}
                          className="text-start flex-1"
                        >
                          <p className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100">{bookmark.name}</p>
                          {bookmark.quoteText && (
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">{bookmark.quoteText}</p>
                          )}
                        </button>
                        <button
                          onClick={() => startEditing(bookmark.id, bookmark.name)}
                          title={t('bookmarks.rename')}
                          className="p-1.5 rounded-lg text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10"
                        >
                          <Edit3 size={14} />
                        </button>
                        <button
                          onClick={() => remove(bookmark.id)}
                          title={t('bookmarks.delete')}
                          className="p-1.5 rounded-lg text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/library/BookmarksTab.test.tsx`
Expected: all tests PASS.

- [ ] **Step 5: Wire the tab into `LibraryView`**

In `apps/frontend/src/components/library/LibraryView.tsx`, add the import:

```typescript
import { BookmarksTab } from './BookmarksTab';
```

and add the branch (after the `activeTab === 'continue-reading'` block from Task 9):

```tsx
      {activeTab === 'bookmarks' && (
        <BookmarksTab
          onOpenBookmark={(bookId, pageNumber) => bookActions.openReader({ id: bookId }, pageNumber)}
        />
      )}
```

(The passage-bookmark quote highlight on arrival is out of scope for this click path in `LibraryView` — `openReader` only accepts a page number, matching Task 5's signature. Opening at the right page is the primary behavior; highlighting the quote from a cold-open deep link is already covered by the existing `pendingQuoteHighlight` mechanism when the bookmark is opened from the in-reader drawer, Task 8, which sets it directly via `AppContext`.)

- [ ] **Step 6: Add the new i18n keys**

In `apps/frontend/src/locales/en.json`, extend `"library"`:

```json
    "bookmarksTab": {
      "searchPlaceholder": "Search your bookmarks...",
      "empty": "You haven't saved any bookmarks yet"
    }
```

In `apps/frontend/src/locales/ug.json` (draft, needs review):

```json
    "bookmarksTab": {
      "searchPlaceholder": "بەلگىلىرىڭىزنى ئىزدەڭ...",
      "empty": "سىز تېخى ھېچقانداق بەلگە ساقلىمىدىڭىز"
    }
```

- [ ] **Step 7: Rebuild and manually verify**

Run: `./deploy/local/rebuild-and-restart.sh frontend`

Go to Library → Bookmarks tab, confirm bookmarks are grouped by book, search filters correctly, clicking opens the reader at the right page, delete removes the entry.

- [ ] **Step 8: Commit**

```bash
git add apps/frontend/src/components/library/BookmarksTab.tsx apps/frontend/src/components/library/LibraryView.tsx apps/frontend/src/tests/components/library/BookmarksTab.test.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "feat(library): add Bookmarks tab"
```

---

### Task 11: Profile menu shortcuts

**Files:**
- Modify: `apps/frontend/src/components/auth/AuthButton.tsx`
- Test: `apps/frontend/src/tests/components/auth/AuthButton.test.tsx` (new file — no test currently covers `AuthButton.tsx`)
- Modify: `apps/frontend/src/locales/en.json`, `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Consumes: `useAppContext()`'s `setView`/`setActiveTab` (existing + Task 9's library-tab routing).
- Produces: `UserMenu` renders two new buttons ("Continue Reading", "Bookmarks") between the user header and Logout, each calling `setView('library')` + `setActiveTab(...)`.

- [ ] **Step 1: Create the `AuthButton` test file**

No test file for `AuthButton.tsx` exists yet (confirmed: `find apps/frontend/src/tests -iname "*AuthButton*"` returns nothing). Create `apps/frontend/src/tests/components/auth/AuthButton.test.tsx`, following `LibraryView.test.tsx`'s established pattern of `renderWithProviders` plus a `vi.mock('@/src/context/AppContext', ...)` override:

```typescript
import { UserMenu } from '@/src/components/auth/AuthButton';
import * as AppContextModule from '@/src/context/AppContext';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    user: { displayName: 'Test User', email: 't@example.com', avatarUrl: null, role: 'reader' },
    logout: vi.fn(),
    isLoading: false,
  })),
}));

vi.mock('@/src/context/AppContext', async () => {
  const actual = await vi.importActual('@/src/context/AppContext');
  return {
    ...actual as any,
    useAppContext: vi.fn(),
  };
});

const renderMenu = () => {
  const setView = vi.fn();
  const setActiveTab = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({ setView, setActiveTab } as any);
  render(<UserMenu />);
  return { setView, setActiveTab };
};

beforeEach(() => vi.clearAllMocks());

test('shows Continue Reading and Bookmarks shortcuts for signed-in users', () => {
  renderMenu();
  fireEvent.click(screen.getByRole('button'));

  expect(screen.getByText('nav.continueReading')).toBeInTheDocument();
  expect(screen.getByText('nav.bookmarks')).toBeInTheDocument();
});

test('Continue Reading shortcut navigates to the Library continue-reading tab', () => {
  const { setView, setActiveTab } = renderMenu();
  fireEvent.click(screen.getByRole('button'));
  fireEvent.click(screen.getByText('nav.continueReading'));

  expect(setView).toHaveBeenCalledWith('library');
  expect(setActiveTab).toHaveBeenCalledWith('continue-reading');
});

test('Bookmarks shortcut navigates to the Library bookmarks tab', () => {
  const { setView, setActiveTab } = renderMenu();
  fireEvent.click(screen.getByRole('button'));
  fireEvent.click(screen.getByText('nav.bookmarks'));

  expect(setView).toHaveBeenCalledWith('library');
  expect(setActiveTab).toHaveBeenCalledWith('bookmarks');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/auth/AuthButton.test.tsx`
Expected: FAIL — `nav.continueReading`/`nav.bookmarks` text not found (shortcuts don't exist yet).

- [ ] **Step 3: Add the shortcuts to `UserMenu`**

In `apps/frontend/src/components/auth/AuthButton.tsx`, add the import:

```typescript
import { BookOpen, ChevronDown, Edit3, LogIn, LogOut, Shield, BookMarked, History } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
```

In `UserMenu`, add `useAppContext()`:

```typescript
export function UserMenu({ onLogout, side = 'left', inline = false }: { onLogout?: () => void; side?: 'left' | 'right'; inline?: boolean }) {
  const { user, logout, isLoading } = useAuth();
  const { setView, setActiveTab } = useAppContext();
  const { t } = useI18n();
```

Add the two buttons inside `menuContent`, in the `<div className="p-1 space-y-1">` block, right before the existing Logout button:

```tsx
        <button
          onClick={() => {
            setIsOpen(false);
            setView('library');
            setActiveTab('continue-reading');
          }}
          className="w-full flex items-center justify-between px-4 py-3 text-[#1a1a1a] dark:text-slate-200 hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/10 rounded-2xl transition-all font-normal text-sm active:scale-95 group"
          dir="rtl"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl group-hover:bg-[#0369a1] dark:group-hover:bg-[#38bdf8] group-hover:text-white dark:group-hover:text-slate-950 transition-all shadow-sm">
              <History size={16} strokeWidth={2.5} />
            </div>
            <span className="group-hover:text-[#0369a1] dark:group-hover:text-[#38bdf8] transition-colors uyghur-text">{t('nav.continueReading')}</span>
          </div>
        </button>
        <button
          onClick={() => {
            setIsOpen(false);
            setView('library');
            setActiveTab('bookmarks');
          }}
          className="w-full flex items-center justify-between px-4 py-3 text-[#1a1a1a] dark:text-slate-200 hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/10 rounded-2xl transition-all font-normal text-sm active:scale-95 group"
          dir="rtl"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl group-hover:bg-[#0369a1] dark:group-hover:bg-[#38bdf8] group-hover:text-white dark:group-hover:text-slate-950 transition-all shadow-sm">
              <BookMarked size={16} strokeWidth={2.5} />
            </div>
            <span className="group-hover:text-[#0369a1] dark:group-hover:text-[#38bdf8] transition-colors uyghur-text">{t('nav.bookmarks')}</span>
          </div>
        </button>
```

(`UserMenu` already returns `null` when `!user`, at the top of the function — no additional guest-check needed; these buttons simply never render for guests.)

Note `isOpen`/`setIsOpen` used above are already in scope from `UserMenu`'s existing state — no new state needed. If the actual test's `renderMenu()` needs `isOpen` to start `false` and the menu to be a button that toggles it, that already matches `UserMenu`'s existing top-level `<button onClick={() => setIsOpen(!isOpen)}>` — the test's `fireEvent.click(screen.getByRole('button'))` (Step 1) opens the dropdown before checking for the shortcuts.

- [ ] **Step 4: Add the new i18n keys**

In `apps/frontend/src/locales/en.json`, the `"nav"` object currently reads `{"home", "library", "globalChat", "spellCheck", "joinUs", "admin", "addBook", "graph", "dictionary", "quran", "switchLanguage"}`. Add two more keys to it:

```json
    "continueReading": "Continue Reading",
    "bookmarks": "Bookmarks",
```

In `apps/frontend/src/locales/ug.json` (draft, needs review):

```json
    "continueReading": "ئوقۇشنى داۋاملاشتۇرۇش",
    "bookmarks": "بەلگىلەر",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/auth/AuthButton.test.tsx`
Expected: all tests PASS.

- [ ] **Step 6: Rebuild and manually verify**

Run: `./deploy/local/rebuild-and-restart.sh frontend`

Sign in, open the profile menu (avatar, top right), confirm "Continue Reading" and "Bookmarks" appear above Logout, and each opens the Library page on the correct tab. Sign out and confirm the menu doesn't render at all for guests (existing behavior, unchanged).

- [ ] **Step 7: Commit**

```bash
git add apps/frontend/src/components/auth/AuthButton.tsx apps/frontend/src/tests/components/auth/AuthButton.test.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "feat(auth): add Continue Reading and Bookmarks shortcuts to profile menu"
```

---

## Final Verification

- [ ] Run the full backend test suite: `cd packages/backend-core && python -m pytest` and `cd services/backend && python -m pytest`. Expected: all PASS, no regressions in existing suites.
- [ ] Run the full frontend test suite: `cd apps/frontend && npx vitest run`. Expected: all PASS.
- [ ] Manual end-to-end pass (signed-in user): read partway into a book, close it, reopen from Library "All Books" — confirm it resumes at the right page. Bookmark a whole page and a selected passage; confirm both appear (correct name/snippet) in the per-book drawer, the Library "Bookmarks" tab, and the profile-menu shortcut path; rename and delete from both places. Confirm the "Continue Reading" tab and its profile-menu shortcut show the right book/page and that its search box filters instantly.
- [ ] Manual guest pass: confirm tapping either bookmark control shows the inline sign-in prompt and creates nothing; confirm the Library "Continue Reading" and "Bookmarks" tabs show `GuestAuthWall` instead of fetching.
- [ ] Visual check in both RTL layout and dark mode: bookmark icons, the name-prompt popover, the drawer, and both new Library tabs.
- [ ] Flag the `ug.json` additions (Tasks 3, 7, 8, 9, 10, 11) to a native Uyghur speaker for review before this branch ships, per Global Constraints.
