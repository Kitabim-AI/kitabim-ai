# API Unit Tester Skill — Kitabim AI Backend

You are acting as a backend test engineer for the kitabim-ai Python/FastAPI app. Your job is to write comprehensive, reliable unit tests for repositories, services, utilities, and endpoints — covering happy paths, edge cases, missing data, and error states.

## Testing Stack

| Tool | Purpose |
|------|---------|
| pytest | Test runner |
| pytest-asyncio (`asyncio_mode = auto`) | Async test support |
| `unittest.mock` | `AsyncMock`, `MagicMock`, `patch` |

**pytest.ini** (project root):
```ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
norecursedirs = scripts
```

`asyncio_mode = auto` means all `async def test_*` functions run as coroutines automatically — no `@pytest.mark.asyncio` required, but adding it is harmless.

**Run tests:**
```bash
# From project root
pytest packages/backend-core/tests/          # core package tests
pytest services/backend/tests/               # API endpoint/auth tests
pytest services/worker/tests/               # worker job/scanner tests

# Single file
pytest packages/backend-core/tests/app/db/test_books_repository.py -v

# With coverage
pytest packages/backend-core/tests/ --cov=app --cov-report=term-missing
```

---

## File Placement

Mirror the source tree under each package's `tests/` directory:

```
packages/backend-core/
  app/
    db/repositories/books.py          → tests/app/db/test_books_repository.py
    services/user_service.py          → tests/app/services/test_user_service.py
    utils/text.py                     → tests/app/utils/test_text.py
    core/i18n.py                      → tests/app/core/test_i18n.py

services/backend/
  api/endpoints/books.py              → tests/api/endpoints/test_books.py
  auth/jwt_handler.py                 → tests/auth/test_jwt_handler.py
```

**Naming:** `test_<module_name>.py` — always prefixed with `test_`.

---

## Environment Setup (conftest.py)

The `packages/backend-core/tests/conftest.py` forces test-safe env vars before any imports:

```python
# conftest.py — already exists, do not duplicate
os.environ["STORAGE_BACKEND"] = "local"
os.environ["ENVIRONMENT"] = "test"
```

This prevents GCS initialization and other prod-only side effects. If adding a new test package, add a `conftest.py` with the same env setup.

---

## The Four Test Types

### 1. Repository Tests

Repositories wrap SQLAlchemy `AsyncSession`. Mock the session; assert the result shape and that the session was used correctly.

**Key session mock patterns:**

```python
# List query: session.execute → .scalars().all()
mock_res = MagicMock()
mock_res.scalars.return_value.all.return_value = [MyModel(id="x")]
session.execute.return_value = mock_res

# Single-item query: session.execute → .scalar_one_or_none()
mock_res = MagicMock()
mock_res.scalar_one_or_none.return_value = MyModel(id="x")
session.execute.return_value = mock_res

# Scalar count: session.execute → .scalar_one()
mock_res = MagicMock()
mock_res.scalar_one.return_value = 42
session.execute.return_value = mock_res

# Raw rows: session.execute → .fetchall()
mock_res = MagicMock()
mock_res.fetchall.return_value = [row1, row2]
session.execute.return_value = mock_res

# Single raw row: session.execute → .fetchone()
mock_res = MagicMock()
mock_res.fetchone.return_value = mock_row
session.execute.return_value = mock_res

# Multiple sequential queries
session.execute.side_effect = [mock_res1, mock_res2, mock_res3]
```

**Full example:**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.books import BooksRepository
from app.db.models import Book

@pytest.mark.asyncio
async def test_find_by_hash():
    session = AsyncMock()
    repo = BooksRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Book(id="b1", content_hash="h1")
    session.execute.return_value = mock_res

    book = await repo.find_by_hash("h1")
    assert book.id == "b1"
    session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_find_many():
    session = AsyncMock()
    repo = BooksRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [Book(id="b1"), Book(id="b2")]
    session.execute.return_value = mock_res

    books = await repo.find_many(status="ready")
    assert len(books) == 2

@pytest.mark.asyncio
async def test_find_by_hash_not_found():
    session = AsyncMock()
    repo = BooksRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res

    book = await repo.find_by_hash("nonexistent")
    assert book is None

@pytest.mark.asyncio
async def test_create_record():
    session = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    repo = MyRepository(session)

    result = await repo.create_record(field="value")

    assert result.field == "value"
    assert session.add.called
    assert session.flush.called
    assert session.refresh.called

def test_get_repository_factory():
    """Test the factory function returns the correct type."""
    from app.db.repositories.books import get_books_repository
    session = AsyncMock()
    repo = get_books_repository(session)
    assert isinstance(repo, BooksRepository)
```

---

### 2. Service Tests

Services are thin orchestration layers over repositories. Patch the repository class at the module import path, then configure the mock instance's methods.

**Patching pattern:**
```python
with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
    mock_repo = mock_repo_cls.return_value   # the instantiated repo
    mock_repo.find_by_email = AsyncMock(return_value=mock_user_db)
    result = await get_user_by_email(session, "test@example.com")
```

**Full example:**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from app.services.user_service import get_user_by_id, create_user
from app.db.models import User as UserDB

@pytest.fixture
def mock_user_db():
    return UserDB(
        id=uuid4(),
        email="test@example.com",
        display_name="Test User",
        role="reader",
        provider="google",
        provider_id="123",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

@pytest.mark.asyncio
async def test_get_user_by_id(mock_user_db):
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get = AsyncMock(return_value=mock_user_db)

        user = await get_user_by_id(session, str(mock_user_db.id))

        assert user.email == mock_user_db.email
        mock_repo.get.assert_called_once_with(str(mock_user_db.id))

@pytest.mark.asyncio
async def test_get_user_by_id_not_found():
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get = AsyncMock(return_value=None)

        result = await get_user_by_id(session, "nonexistent")
        assert result is None

@pytest.mark.asyncio
async def test_create_user():
    session = AsyncMock()
    session.add = MagicMock()
    with patch("app.utils.security.hash_ip_if_present", return_value="hashed_ip"):
        user = await create_user(
            session,
            email="new@example.com",
            display_name="New User",
            provider="google",
            provider_id="456",
        )
        assert user.email == "new@example.com"
        assert session.add.called
        assert session.flush.called
```

---

### 3. Utility Tests

Pure functions — no mocking needed. Import and call directly.

```python
from app.utils.text import normalize_uyghur_chars, clean_uyghur_text

def test_normalize_removes_zwj():
    assert normalize_uyghur_chars("u\u200Cword") == "uword"

def test_normalize_empty_string():
    assert normalize_uyghur_chars("") == ""

def test_clean_text_joins_hyphenated_lines():
    result = clean_uyghur_text("كىت-\nاب")
    assert "كىتاب" in result

def test_raises_on_invalid_input():
    with pytest.raises(ValueError, match="expected non-empty"):
        my_util(None)
```

---

### 4. Endpoint Tests

Most endpoint tests are currently scaffolds. When writing real endpoint tests, use `httpx.AsyncClient` with the FastAPI `app` and override dependencies via `app.dependency_overrides`.

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from main import app
from app.api.deps import get_session, require_admin

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.mark.asyncio
async def test_get_books_endpoint(mock_session):
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[require_admin] = lambda: {"id": "admin1", "role": "admin"}

    try:
        with patch("app.api.endpoints.books.BooksRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.find_many = AsyncMock(return_value=[])
            mock_repo.count = AsyncMock(return_value=0)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/books/",
                    headers={"X-Kitabim-App-Id": "web"},
                )
            assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
```

> **Note:** Endpoint tests need the FastAPI app instantiated. Run them from the `services/backend/` directory so imports resolve correctly.

---

## Common Mocking Recipes

### Mock a repository method directly on an instance
```python
repo = BooksRepository(session)
repo.get = AsyncMock(return_value=mock_book)   # bypass internals
```

### Mock multiple sequential `session.execute` calls
```python
session.execute.side_effect = [mock_res_1, mock_res_2, mock_res_3]
```

### Mock a function that is patched at the usage site
```python
# If the service imports: from app.utils.security import hash_ip_if_present
with patch("app.services.user_service.hash_ip_if_present", return_value="x"):
    ...

# NOT: patch("app.utils.security.hash_ip_if_present")
```

### Build a raw row mock (used in complex pipeline stat queries)
```python
mock_row = MagicMock()
mock_row.book_id = "b1"
mock_row.ocr = 5
mock_row.ocr_failed = 0
```

### Assert session was NOT called (fast-exit path)
```python
stats = await repo.get_batch_stats([])
assert stats == {}
session.execute.assert_not_called()
```

---

## What to Test

### Repositories — test these:
- Happy path: returns the expected model/list/count
- Not-found: returns `None` or `[]`
- Empty input fast-exit: no DB call made
- Multiple sequential query ordering (use `side_effect`)
- Factory function returns correct type

### Services — test these:
- Happy path: correct data flows through to the caller
- Not-found / None input passthrough
- Each branch of conditional logic (e.g., different roles, statuses)
- That the correct repository method was called with the right args

### Utilities — test these:
- Known inputs → expected outputs
- Edge cases: empty string, None, boundary values
- Unicode/Uyghur text handling where relevant
- Exception raised on invalid input (use `pytest.raises`)

### Do NOT test:
- SQLAlchemy internals or ORM query construction
- Third-party library behavior (LangChain, Redis, GCS)
- `conftest.py` env-setup hooks
- Models/Pydantic schemas beyond basic field presence

---

## Common Mistakes to Avoid

| Mistake | Fix |
|---------|-----|
| `session.execute.return_value = [Book(...)]` | Wrap in `MagicMock()` with `.scalars().all()` chain |
| `patch("app.utils.security.hash_ip_if_present")` | Patch at the import site: `patch("app.services.user_service.hash_ip_if_present")` |
| Using `MagicMock()` for an async method | Use `AsyncMock()` — sync mock can't be awaited |
| `session = MagicMock()` for repo tests | Use `AsyncMock()` — session methods are async |
| Forgetting `session.flush` is async | It is — `session.flush = AsyncMock()` or `session = AsyncMock()` covers it |
| Creating a new `conftest.py` that re-imports modules before setting env vars | Set `os.environ` before any imports in conftest |

---

## Workflow

1. **Read the source file first** — understand what the function does, what it calls, and what it returns.
2. **Identify the mock boundary** — for repos: mock `session`; for services: mock the repo class via `patch`; for utils: no mocks.
3. **Create the test file** mirroring the source path under `tests/`.
4. **Cover:** happy path, not-found / empty, error/edge case, and any branching logic.
5. **Run:** `pytest path/to/test_file.py -v` to confirm all tests pass.
