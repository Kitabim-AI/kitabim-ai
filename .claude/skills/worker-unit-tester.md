# Worker Unit Tester Skill — Kitabim AI Worker Service

You are acting as a backend test engineer for the kitabim-ai ARQ worker service. Your job is to write comprehensive, reliable unit tests for pipeline jobs, scanners, and the pipeline driver — covering happy paths, edge cases, per-page isolation, error handling, and state machine transitions.

## Testing Stack

| Tool | Purpose |
|------|---------|
| pytest | Test runner |
| pytest-asyncio (`asyncio_mode = auto`) | Async test support |
| `unittest.mock` | `AsyncMock`, `MagicMock`, `patch` |

**Run tests:**
```bash
# From project root
pytest services/worker/tests/ -v

# Single file
pytest services/worker/tests/jobs/test_ocr_job.py -v
```

---

## File Placement

Mirror the source tree under `tests/`:

```
services/worker/
  jobs/ocr_job.py              → tests/jobs/test_ocr_job.py
  jobs/chunking_job.py         → tests/jobs/test_chunking_job.py
  jobs/embedding_job.py        → tests/jobs/test_embedding_job.py
  jobs/spell_check_job.py      → tests/jobs/test_spell_check_job.py
  jobs/summary_job.py          → tests/jobs/test_summary_job.py
  jobs/auto_correct_job.py     → tests/jobs/test_auto_correct_job.py
  scanners/ocr_scanner.py      → tests/scanners/test_ocr_scanner.py
  scanners/pipeline_driver.py  → tests/scanners/test_pipeline_driver.py
  scanners/stale_watchdog.py   → tests/scanners/test_stale_watchdog.py
  ...
```

---

## The Core Mock: `async_session_factory`

Every job and scanner calls `async with db_session.async_session_factory() as session:`. This is the primary thing to mock.

**Standard setup:**
```python
from unittest.mock import AsyncMock, MagicMock, patch

mock_session = AsyncMock()
mock_session.add = MagicMock()   # session.add() is sync
# async_session_factory() returns a context manager
# so set __aenter__ to return the mock session

with patch("app.db.session.async_session_factory") as mock_factory:
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    await my_job(ctx, page_ids)
```

**When a job opens multiple sessions** (all jobs do this), the same `mock_factory` is called multiple times. If all sessions behave identically, a single mock is fine. If you need different behavior per session call, use `side_effect`:

```python
mock_factory.side_effect = [
    make_cm(session_1),   # first async with block
    make_cm(session_2),   # second async with block
    make_cm(session_3),   # third, etc.
]

def make_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm
```

---

## ARQ Context (`ctx`)

Jobs and scanners receive `ctx` as their first argument — the ARQ worker context dict.

```python
ctx = {
    "redis": AsyncMock(),   # arq Redis client — used to enqueue_job()
}
```

Set `ctx["redis"].enqueue_job = AsyncMock()` if you need to assert jobs were dispatched.

---

## Job Test Template

Jobs: `async def job_name(ctx, page_ids: List[int]) -> None`

**Shared page fixture:**
```python
from app.db.models import Page

def make_mock_page(page_id=1, book_id="book-1", page_number=1, **kwargs):
    page = MagicMock(spec=Page)
    page.id = page_id
    page.book_id = book_id
    page.page_number = page_number
    for k, v in kwargs.items():
        setattr(page, k, v)
    return page
```

**Full example — chunking_job:**
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from jobs.chunking_job import chunking_job
from app.db.models import Page

def make_mock_page(page_id=1, book_id="b1", page_number=1, **kw):
    p = MagicMock(spec=Page)
    p.id = page_id
    p.book_id = book_id
    p.page_number = page_number
    p.is_toc = kw.get("is_toc", False)
    p.text = kw.get("text", "Some text to chunk.")
    return p

@pytest.mark.asyncio
async def test_chunking_job_success():
    ctx = {"redis": AsyncMock()}
    page = make_mock_page(text="Hello world this is a page.")

    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    # First session.execute returns pages, subsequent calls return update results
    mock_pages_result = MagicMock()
    mock_pages_result.scalars.return_value.all.return_value = [page]
    mock_session.execute.side_effect = [
        mock_pages_result,   # select(Page) load
        MagicMock(),         # update(Book) pipeline_step
        MagicMock(),         # delete(Chunk)
        MagicMock(),         # update(Page) chunking_milestone
    ]

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("jobs.chunking_job.chunking_service") as mock_chunker, \
         patch("jobs.chunking_job.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_chunker.split_text.return_value = ["chunk 1", "chunk 2"]
        mock_milestone.update_book_milestone_for_step = AsyncMock()

        await chunking_job(ctx, [page.id])

    mock_chunker.split_text.assert_called_once_with(page.text)
    mock_milestone.update_book_milestone_for_step.assert_called()

@pytest.mark.asyncio
async def test_chunking_job_toc_page_skips_chunking():
    ctx = {"redis": AsyncMock()}
    page = make_mock_page(is_toc=True, text="Table of Contents...")

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_pages_result = MagicMock()
    mock_pages_result.scalars.return_value.all.return_value = [page]
    mock_session.execute.return_value = mock_pages_result

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("jobs.chunking_job.chunking_service") as mock_chunker, \
         patch("jobs.chunking_job.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_milestone.update_book_milestone_for_step = AsyncMock()

        await chunking_job(ctx, [page.id])

    # TOC pages must not be chunked
    mock_chunker.split_text.assert_not_called()

@pytest.mark.asyncio
async def test_chunking_job_page_failure_is_isolated():
    """A single page failure must not stop other pages from processing."""
    ctx = {"redis": AsyncMock()}
    good_page = make_mock_page(page_id=1, text="Good text")
    bad_page = make_mock_page(page_id=2, text="Bad text")

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_pages_result = MagicMock()
    mock_pages_result.scalars.return_value.all.return_value = [good_page, bad_page]
    mock_session.execute.return_value = mock_pages_result

    call_count = 0
    def split_text_side_effect(text):
        nonlocal call_count
        call_count += 1
        if call_count == 2:   # second page fails
            raise ValueError("chunking failed")
        return ["chunk"]

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("jobs.chunking_job.chunking_service") as mock_chunker, \
         patch("jobs.chunking_job.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_chunker.split_text.side_effect = split_text_side_effect
        mock_milestone.update_book_milestone_for_step = AsyncMock()

        # Should NOT raise — per-page isolation means errors are caught
        await chunking_job(ctx, [good_page.id, bad_page.id])

    assert mock_chunker.split_text.call_count == 2

@pytest.mark.asyncio
async def test_chunking_job_empty_page_ids():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    mock_empty = MagicMock()
    mock_empty.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_empty

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("jobs.chunking_job.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_milestone.update_book_milestone_for_step = AsyncMock()

        await chunking_job(ctx, [])

    mock_milestone.update_book_milestone_for_step.assert_not_called()
```

---

## Job: Config-Reading Pattern (OCR / Embedding)

Some jobs first fetch config from `SystemConfigsRepository`. Mock the repo at the job's import path:

```python
with patch("jobs.ocr_job.SystemConfigsRepository") as mock_config_cls:
    mock_config = mock_config_cls.return_value
    mock_config.get_value = AsyncMock(side_effect=lambda key, default=None: {
        "gemini_ocr_model": "gemini-pro-vision",
        "ocr_max_parallel_pages": "4",
    }.get(key, default))
    ...
```

**Raise RuntimeError when required config is missing:**
```python
@pytest.mark.asyncio
async def test_embedding_job_raises_when_model_not_configured():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("jobs.embedding_job.SystemConfigsRepository") as mock_config_cls:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="gemini_embedding_model"):
            await embedding_job(ctx, [1, 2])
```

---

## Scanner Test Template

Scanners: `async def run_scanner_name(ctx) -> None`

Key differences from jobs:
- They query for work, atomically claim pages, then dispatch jobs via `ctx["redis"].enqueue_job()`
- No per-page error isolation — the whole scan either runs or raises

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scanners.ocr_scanner import run_ocr_scanner

@pytest.mark.asyncio
async def test_ocr_scanner_dispatches_job_for_idle_pages():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}
    mock_session = AsyncMock()

    # Query 1: get books with idle OCR work
    mock_books_result = MagicMock()
    mock_books_result.fetchall.return_value = [("book-1",), ("book-2",)]

    # Query 2 (per book): claim idle page IDs
    mock_pages_result = MagicMock()
    mock_pages_result.fetchall.return_value = [(1,), (2,), (3,)]

    mock_session.execute.side_effect = [
        mock_books_result,    # book discovery query
        mock_pages_result,    # claim pages for book-1
        mock_pages_result,    # claim pages for book-2
    ]

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("scanners.ocr_scanner.SystemConfigsRepository") as mock_config_cls, \
         patch("scanners.ocr_scanner.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(return_value="10")
        mock_milestone.update_book_milestone_for_step = AsyncMock()

        await run_ocr_scanner(ctx)

    # Two books → two job dispatches
    assert mock_redis.enqueue_job.call_count == 2
    first_call = mock_redis.enqueue_job.call_args_list[0]
    assert first_call.kwargs["book_id"] == "book-1"
    assert first_call.kwargs["page_ids"] == [1, 2, 3]

@pytest.mark.asyncio
async def test_ocr_scanner_skips_books_with_no_idle_pages():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}
    mock_session = AsyncMock()

    mock_books_result = MagicMock()
    mock_books_result.fetchall.return_value = [("book-1",)]

    # No idle pages for book-1
    mock_no_pages = MagicMock()
    mock_no_pages.fetchall.return_value = []

    mock_session.execute.side_effect = [mock_books_result, mock_no_pages]

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("scanners.ocr_scanner.SystemConfigsRepository") as mock_config_cls, \
         patch("scanners.ocr_scanner.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(return_value="10")
        mock_milestone.update_book_milestone_for_step = AsyncMock()

        await run_ocr_scanner(ctx)

    mock_redis.enqueue_job.assert_not_called()

@pytest.mark.asyncio
async def test_ocr_scanner_no_books_to_process():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    mock_empty = MagicMock()
    mock_empty.fetchall.return_value = []
    mock_session.execute.return_value = mock_empty

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("scanners.ocr_scanner.SystemConfigsRepository") as mock_config_cls:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(return_value="10")

        await run_ocr_scanner(ctx)

    ctx["redis"].enqueue_job.assert_not_called()
```

---

## Pipeline Driver Test Template

The driver is a state machine with four phases: initialize, reset, detect terminal books, mark ready/error. Test each branch:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scanners.pipeline_driver import run_pipeline_driver

def _mock_execute_chain(session, side_effects):
    """Helper: configure session.execute() calls in order."""
    session.execute.side_effect = side_effects

def _row(book_id, total, terminal, succeeded, failed_exhausted):
    r = MagicMock()
    r.book_id = book_id
    r.total = total
    r.terminal = terminal
    r.succeeded = succeeded
    r.failed_exhausted = failed_exhausted
    return r

@pytest.mark.asyncio
async def test_pipeline_driver_marks_book_ready():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    # init_ids → some pages
    init_result = MagicMock(); init_result.fetchall.return_value = [(1,), (2,)]
    init_exec = MagicMock(); init_exec.rowcount = 2
    # reset_ids → none
    reset_result = MagicMock(); reset_result.fetchall.return_value = []
    # terminal books → one fully-ready book
    terminal_row = _row("book-1", total=10, terminal=10, succeeded=10, failed_exhausted=0)
    terminal_result = MagicMock(); terminal_result.fetchall.return_value = [terminal_row]
    # newly_ready query → book-1 is newly ready
    newly_ready_result = MagicMock(); newly_ready_result.fetchall.return_value = [("book-1",)]
    # mark ready update
    ready_exec = MagicMock(); ready_exec.rowcount = 1

    mock_session.execute.side_effect = [
        init_result, init_exec,       # initialize phase
        reset_result,                  # reset phase (no resets)
        terminal_result,               # detect terminal books
        newly_ready_result,            # newly ready query
        ready_exec,                    # UPDATE book → ready
    ]

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("scanners.pipeline_driver.SystemConfigsRepository") as mock_config_cls, \
         patch("scanners.pipeline_driver.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(return_value="3")
        mock_milestone.update_book_milestones = AsyncMock()

        await run_pipeline_driver(ctx)

    ctx["redis"].enqueue_job.assert_called_once_with(
        "summary_job",
        book_id="book-1",
        _job_id="summary:book-1",
    )

@pytest.mark.asyncio
async def test_pipeline_driver_marks_book_error_on_exhausted_retries():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    init_result = MagicMock(); init_result.fetchall.return_value = []
    reset_result = MagicMock(); reset_result.fetchall.return_value = []
    terminal_row = _row("book-1", total=10, terminal=10, succeeded=7, failed_exhausted=3)
    terminal_result = MagicMock(); terminal_result.fetchall.return_value = [terminal_row]
    error_exec = MagicMock(); error_exec.rowcount = 1

    mock_session.execute.side_effect = [
        init_result, reset_result, terminal_result, error_exec
    ]

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("scanners.pipeline_driver.SystemConfigsRepository") as mock_config_cls, \
         patch("scanners.pipeline_driver.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(return_value="3")
        mock_milestone.update_book_milestones = AsyncMock()

        await run_pipeline_driver(ctx)

    # No summary job for failed books
    ctx["redis"].enqueue_job.assert_not_called()

@pytest.mark.asyncio
async def test_pipeline_driver_resets_failed_pages_with_retries_remaining():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    init_result = MagicMock(); init_result.fetchall.return_value = []
    reset_ids_result = MagicMock(); reset_ids_result.fetchall.return_value = [(5,), (6,)]
    reset_exec = MagicMock(); reset_exec.rowcount = 2
    terminal_result = MagicMock(); terminal_result.fetchall.return_value = []

    mock_session.execute.side_effect = [
        init_result, reset_ids_result, reset_exec, terminal_result
    ]

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("scanners.pipeline_driver.SystemConfigsRepository") as mock_config_cls, \
         patch("scanners.pipeline_driver.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(return_value="3")
        mock_milestone.update_book_milestones = AsyncMock()

        await run_pipeline_driver(ctx)

    # Pages were reset — session.execute was called for the reset UPDATE
    assert mock_session.execute.call_count >= 3
```

---

## Stale Watchdog Test Template

```python
@pytest.mark.asyncio
async def test_stale_watchdog_resets_stale_pages():
    ctx = {}
    mock_session = AsyncMock()

    mock_row_1 = MagicMock(); mock_row_1.__iter__ = lambda s: iter([1, "book-1"])
    stale_result = MagicMock()
    stale_result.fetchall.return_value = [(1, "book-1"), (2, "book-1")]
    mock_session.execute.return_value = stale_result

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("scanners.stale_watchdog.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_milestone.update_book_milestones = AsyncMock()

        await run_stale_watchdog(ctx)

    mock_milestone.update_book_milestones.assert_called_with(mock_session, "book-1")
    mock_session.commit.assert_called()

@pytest.mark.asyncio
async def test_stale_watchdog_no_stale_pages():
    ctx = {}
    mock_session = AsyncMock()

    empty_result = MagicMock()
    empty_result.fetchall.return_value = []
    mock_session.execute.return_value = empty_result

    with patch("app.db.session.async_session_factory") as mock_factory, \
         patch("scanners.stale_watchdog.BookMilestoneService") as mock_milestone:

        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_milestone.update_book_milestones = AsyncMock()

        await run_stale_watchdog(ctx)

    mock_milestone.update_book_milestones.assert_not_called()
```

---

## Patch Path Reference

Always patch at the **module that imports the symbol**, not where it's defined:

| Target | Correct patch path |
|--------|-------------------|
| `db_session.async_session_factory` | `"app.db.session.async_session_factory"` |
| `BookMilestoneService` in scanner | `"scanners.ocr_scanner.BookMilestoneService"` |
| `chunking_service` in job | `"jobs.chunking_job.chunking_service"` |
| `SystemConfigsRepository` in job | `"jobs.ocr_job.SystemConfigsRepository"` |
| `GeminiEmbeddings` in embedding job | `"jobs.embedding_job.GeminiEmbeddings"` |
| `ocr_page_with_gemini` in OCR job | `"jobs.ocr_job.ocr_page_with_gemini"` |
| `storage.download_file` in OCR job | `"jobs.ocr_job.storage"` |

---

## What to Test

### Jobs — test these:
- **Happy path** — pages loaded, service called, milestones updated, session committed
- **Empty `page_ids`** — returns early, no DB calls beyond the initial select
- **Per-page error isolation** — one page raises, others still succeed, failure milestone written
- **Missing config** — `RuntimeError` raised when required `system_config` key is not set
- **TOC / empty page fast-exit** — skips processing, marks succeeded without calling service
- **`BookMilestoneService` called** — milestone updated after processing the batch

### Scanners — test these:
- **Jobs dispatched** — `ctx["redis"].enqueue_job` called with correct `book_id`, `page_ids`, `_job_id`
- **No work available** — `enqueue_job` not called when no idle pages found
- **Claim logic** — pages are atomically claimed (milestone set to `in_progress`) before dispatch
- **Book limit respected** — uses scanner config value as page/book cap

### Pipeline Driver — test these:
- **Marks book ready** — when all pages terminal with zero failures → `status=ready`, summary job enqueued
- **Marks book error** — when any page has exhausted retries → `status=error`, no summary job
- **Resets failed pages** — pages with retries remaining reset to `idle`
- **No double summary** — book already at `pipeline_step=ready` is not re-enqueued
- **Empty DB** — no pages/books → completes without error

### Do NOT test:
- SQLAlchemy query internals (specific SELECT clauses)
- ARQ job scheduling / cron configuration
- `BookMilestoneService` internal logic (it has its own tests)
- Log output (assert on side effects, not log calls)

---

## Common Mistakes to Avoid

| Mistake | Fix |
|---------|-----|
| `mock_factory.return_value.return_value = mock_session` | Use `mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)` |
| `session.add = AsyncMock()` | `session.add` is sync: use `session.add = MagicMock()` |
| `patch("app.db.session.async_session_factory")` but job imports it differently | Match the import path in the job file exactly |
| Not setting `__aexit__` | Always set: `mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)` |
| Forgetting `side_effect` for multi-session jobs | Each `async with` block calls the factory — use `side_effect` for distinct behaviors |
| Asserting `enqueue_job` was called without checking args | Use `enqueue_job.assert_called_once_with(...)` to verify `book_id`, `page_ids`, `_job_id` |

---

## Workflow

1. **Read the job or scanner source first** — count how many `async with db_session.async_session_factory()` blocks exist (each needs a mock CM call).
2. **Identify external services** — `ocr_page_with_gemini`, `chunking_service`, `GeminiEmbeddings`, `BookMilestoneService`, `storage` — patch them at the job's import path.
3. **Write the test** in `tests/jobs/` or `tests/scanners/`.
4. **Cover:** happy path, empty input, per-page failure isolation, missing config, no-work-available.
5. **Run:** `pytest services/worker/tests/ -v` to verify all tests pass.
