# Worker Developer Skill — Kitabim AI

You are implementing, debugging, and testing background worker features for the kitabim-ai worker service. This skill covers the day-to-day developer workflow: running the worker, writing and wiring jobs/scanners, implementing services, writing tests, and debugging the pipeline.

---

## Local Dev

**Rebuild and restart the worker:**
```bash
./deploy/local/rebuild-and-restart.sh worker
```

**Tail worker logs:**
```bash
docker compose logs -f worker
```

**Run the worker directly (outside Docker — useful for fast iteration):**
```bash
PYTHONPATH=packages/backend-core:services/worker arq worker.WorkerSettings
```

**All worker code changes require a rebuild** — there is no hot-reload.

---

## Package Layout (what goes where)

| Code type | Location |
|-----------|----------|
| ARQ entry point, cron schedule | `services/worker/worker.py` |
| Scanner functions (cron) | `services/worker/scanners/<step>_scanner.py` |
| Job functions (dispatched) | `services/worker/jobs/<step>_job.py` |
| Business logic / processing | `packages/backend-core/app/services/<name>_service.py` |
| ORM models | `packages/backend-core/app/db/models.py` |
| DB repositories | `packages/backend-core/app/db/repositories/<name>.py` |
| Config settings | `packages/backend-core/app/core/config.py` |
| Dynamic / hot config | DB table `system_configs` via `SystemConfigsRepository` |
| SQL migrations | `packages/backend-core/migrations/NNN_description.sql` |
| Operational / debug scripts | `scripts/` (project root — never inside `services/worker/`) |
| Documentation | `docs/<branch-name>/` (e.g. `docs/main/` on the `main` branch) |

**Both `packages/backend-core` and `services/worker` are on `PYTHONPATH`** in the Docker image — import from either without path hacks.

---

## Session Management

This is the most important rule in the worker. **Never share one `AsyncSession` across multiple pages or concurrent tasks.**

```python
# CORRECT — new session per page, error-isolated
for page in pages:
    try:
        async with db_session.async_session_factory() as session:
            # read + write in one transaction
            await session.execute(update(Page).where(...).values(...))
            session.add(PipelineEvent(...))
            await session.commit()
    except Exception as exc:
        async with db_session.async_session_factory() as session:
            await session.execute(update(Page).where(...).values(milestone="failed"))
            await session.commit()

# WRONG — shared session across all pages, one failure corrupts the rest
async with db_session.async_session_factory() as session:
    for page in pages:
        await session.execute(...)   # don't do this
    await session.commit()
```

**Session phases within a single job:**

| Phase | Own session? | Notes |
|-------|-------------|-------|
| Read config | Yes | Separate short-lived session |
| Load page records | Yes | Read-only, closed before processing loop |
| Mark book `pipeline_step` | Yes | One bulk UPDATE, committed immediately |
| Process each page | Yes, per page | Includes write + `PipelineEvent` + commit |
| Update book milestone | Yes | After the loop, one final session |

---

## Reading Dynamic Config

All tuneable parameters (model names, limits, thresholds) must be read from `SystemConfigsRepository` at job/scanner startup — not hardcoded, not from `settings.*`:

```python
from app.db.repositories.system_configs import SystemConfigsRepository

async with db_session.async_session_factory() as session:
    config_repo = SystemConfigsRepository(session)

    # Required — raise if missing so arq records the failure clearly
    model = await config_repo.get_value("gemini_ocr_model")
    if not model:
        raise RuntimeError("system_config 'gemini_ocr_model' is not set")

    # Optional with default
    page_limit  = int(await config_repo.get_value("scanner_page_limit", "100"))
    max_retries = int(await config_repo.get_value("ocr_max_retry_count", "3"))
    max_parallel = int(await config_repo.get_value("ocr_max_parallel_pages", "4"))
```

Use `settings.*` only for infrastructure values that require a redeployment to change (DB URL, Redis URL, file paths, `embed_batch_size`).

---

## BookMilestoneService

Always call `BookMilestoneService` after changing page milestones — it keeps the denormalised book-level milestone columns in sync. Failure to do so means the scanner can't find the book's work in subsequent runs.

```python
from app.services.book_milestone_service import BookMilestoneService

# After updating pages for one step:
async with db_session.async_session_factory() as session:
    await BookMilestoneService.update_book_milestone_for_step(session, book_id, "ocr")
    await session.commit()

# After any milestone change (all steps):
async with db_session.async_session_factory() as session:
    await BookMilestoneService.update_book_milestones(session, book_id)
    await session.commit()
```

**When to call which:**
- `update_book_milestone_for_step(session, book_id, step)` — after a scanner or job updates one specific step's milestone.
- `update_book_milestones(session, book_id)` — after bulk changes (pipeline_driver, stale_watchdog) that may affect multiple steps.

---

## PipelineEvent

Every page milestone transition must emit a `PipelineEvent` in the **same commit** as the milestone update — not in a separate session:

```python
from app.db.models import PipelineEvent

# Inside the page's session block, before commit:
session.add(PipelineEvent(
    page_id=page.id,
    event_type="my_step_succeeded",   # convention: {step}_{succeeded|failed}
))
# or with extra context:
session.add(PipelineEvent(
    page_id=page.id,
    event_type="my_step_failed",
    payload=f'{{"error": "{error_msg}"}}',
))
await session.commit()
```

The `event_dispatcher` scanner reads unprocessed events and triggers fast downstream jobs (e.g. `ocr_succeeded` → enqueue `chunking_job` immediately, without waiting for the next cron tick). If you add a new pipeline step, update `event_dispatcher.py` to handle the new `event_type`.

---

## Error Handling in Jobs

```python
succeeded = 0
failed = 0

for page in pages:
    try:
        # ... do work ...
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Page).where(Page.id == page.id).values(
                    my_milestone="succeeded",
                    last_updated=func.now(),
                )
            )
            session.add(PipelineEvent(page_id=page.id, event_type="my_step_succeeded"))
            await session.commit()
        succeeded += 1

    except Exception as exc:
        async with db_session.async_session_factory() as session:
            error_msg = str(exc)[:500]          # truncate — DB column has size limit
            await session.execute(
                update(Page).where(Page.id == page.id).values(
                    my_milestone="failed",
                    retry_count=Page.retry_count + 1,   # SQL-side increment (safe under concurrency)
                    error=error_msg,
                    last_updated=func.now(),
                )
            )
            session.add(PipelineEvent(
                page_id=page.id,
                event_type="my_step_failed",
                payload=f'{{"error": "{error_msg}"}}',
            ))
            await session.commit()
        failed += 1
        log_json(logger, logging.WARNING, "page failed",
                 book_id=page.book_id, page=page.page_number, error=str(exc))
        # NEVER re-raise — let other pages continue
```

**Exception to the no-re-raise rule:** book-level jobs (`summary_job`, `auto_correct_job`) should re-raise after logging so arq records the failure and retries:

```python
except Exception as exc:
    log_json(logger, logging.ERROR, "book job failed", book_id=book_id, error=str(exc))
    raise   # arq handles retry for book-level jobs
```

---

## Manually Triggering a Scanner

Use `manual_scan.py` as a template for one-off debugging without waiting for cron:

```python
# services/worker/manual_scan.py pattern — adapt for any scanner
import asyncio
from app.db.session import init_db
from arq import create_pool
from arq.connections import RedisSettings
from app.core.config import settings
from scanners.my_scanner import run_my_scanner

async def main():
    await init_db("worker")
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    ctx = {"redis": redis}
    await run_my_scanner(ctx)
    await redis.close()

if __name__ == "__main__":
    asyncio.run(main())
```

Run from the worker container:
```bash
docker exec -it $(docker compose ps -q worker) \
    python manual_scan.py
```

---

## Stale Watchdog — Adding New Steps

When you add a new pipeline step with a `*_milestone` column, you **must** add it to the stale watchdog (`scanners/stale_watchdog.py`) so stuck `in_progress` pages are automatically recovered:

```python
# In run_stale_watchdog — add to both lists:

where_conditions = [
    ...,
    Page.my_milestone == "in_progress",   # add here
]

update_values = {
    ...,
    "my_milestone": case(              # and here
        (Page.my_milestone == "in_progress", "idle"),
        else_=Page.my_milestone
    ),
}
```

Also add `my_milestone` to `BookMilestoneService` if it tracks it.

---

## Event Dispatcher — Adding New Step Reactions

When a new step completes and should trigger the next one immediately (reactive pipeline, faster than cron), update `event_dispatcher.py`:

```python
elif event.event_type == "my_step_succeeded":
    await redis.enqueue_job("next_step_job", page_ids=[event.page_id])
    enqueued += 1
```

---

## Testing

Tests live in `services/worker/tests/`. Existing tests are scaffolds — write real implementations alongside any new job or scanner.

**Test layout:**
```
tests/
  jobs/test_<step>_job.py
  scanners/test_<step>_scanner.py
```

**Async test pattern** (use `pytest-asyncio`):
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

@pytest.mark.asyncio
async def test_my_job_success():
    mock_page = MagicMock()
    mock_page.id = 1
    mock_page.book_id = "book-123"
    mock_page.page_number = 1
    mock_page.text = "some text"
    mock_page.is_toc = False

    with patch("jobs.my_job.db_session.async_session_factory") as mock_factory, \
         patch("jobs.my_job.do_my_work", new_callable=AsyncMock, return_value="result"), \
         patch("jobs.my_job.BookMilestoneService.update_book_milestone_for_step",
               new_callable=AsyncMock):

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_page]

        ctx = {}
        await my_job(ctx, page_ids=[1])

        # Verify milestone was set to succeeded
        update_calls = [str(c) for c in mock_session.execute.call_args_list]
        assert any("succeeded" in c for c in update_calls)
```

**Testing the failure path:**
```python
@pytest.mark.asyncio
async def test_my_job_page_failure():
    with patch("jobs.my_job.do_my_work", new_callable=AsyncMock,
               side_effect=RuntimeError("API error")), \
         patch("jobs.my_job.db_session.async_session_factory") as mock_factory, \
         patch("jobs.my_job.BookMilestoneService.update_book_milestone_for_step",
               new_callable=AsyncMock):

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_page]

        ctx = {}
        # Job must NOT raise even when a page fails
        await my_job(ctx, page_ids=[1])

        # Check retry_count was incremented
        update_calls = str(mock_session.execute.call_args_list)
        assert "failed" in update_calls
        assert "retry_count" in update_calls
```

**Testing a scanner (claim + dispatch):**
```python
@pytest.mark.asyncio
async def test_my_scanner_dispatches_job():
    mock_redis = AsyncMock()

    with patch("scanners.my_scanner.db_session.async_session_factory") as mock_factory, \
         patch("scanners.my_scanner.BookMilestoneService.update_book_milestone_for_step",
               new_callable=AsyncMock):

        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        # Scanner finds 2 claimable pages
        mock_session.execute.return_value.fetchall.return_value = [(1, "book-1"), (2, "book-1")]

        ctx = {"redis": mock_redis}
        await run_my_scanner(ctx)

        mock_redis.enqueue_job.assert_called_once()
        call_kwargs = mock_redis.enqueue_job.call_args
        assert call_kwargs[0][0] == "my_job"
        assert set(call_kwargs[1]["page_ids"]) == {1, 2}


@pytest.mark.asyncio
async def test_my_scanner_no_work():
    mock_redis = AsyncMock()

    with patch("scanners.my_scanner.db_session.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session
        mock_session.execute.return_value.fetchall.return_value = []

        ctx = {"redis": mock_redis}
        await run_my_scanner(ctx)

        mock_redis.enqueue_job.assert_not_called()
```

**Run tests:**
```bash
cd services/worker && python -m pytest
cd services/worker && python -m pytest tests/jobs/test_my_job.py -v
```

---

## Logging

Always use `log_json` with structured fields — never `print()` or bare `logger.info("string")`:

```python
import logging
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.my_job")      # jobs
logger = logging.getLogger("app.worker.my_scanner")  # scanners

# Job lifecycle
log_json(logger, logging.INFO,    "my job started",   page_count=len(page_ids))
log_json(logger, logging.DEBUG,   "page ok",          book_id=page.book_id, page=page.page_number)
log_json(logger, logging.WARNING, "page failed",      book_id=page.book_id, error=str(exc))
log_json(logger, logging.INFO,    "my job completed", succeeded=succeeded, failed=failed)

# Scanner lifecycle
log_json(logger, logging.INFO, "my scanner dispatched", jobs_dispatched=n, page_count=m)
```

---

## Database Migrations

Same rules as the backend. Add a sequential `.sql` file for every schema change:

```
packages/backend-core/migrations/NNN_short_description.sql
```

Apply locally:
```bash
docker exec -i $(docker compose ps -q postgres) \
    psql -U postgres kitabim < packages/backend-core/migrations/035_my_change.sql
```

After adding a column, update:
1. SQLAlchemy model in `models.py`
2. Any repository queries that need it
3. Stale watchdog if it's a `*_milestone` column
4. `BookMilestoneService` if it tracks the new milestone

---

## Common Mistakes to Avoid

| Mistake | Correct approach |
|---------|----------------|
| Shared session across all pages in a loop | New `async with async_session_factory()` per page |
| Re-raising inside a page-level `except` block | Catch, write `failed` milestone, log, continue — never re-raise |
| Hardcoding model names or limits | Read from `SystemConfigsRepository` at job startup |
| `os.environ.get()` in job/scanner code | `settings.*` for infra; `SystemConfigsRepository` for tuneable params |
| Forgetting `BookMilestoneService` after page updates | Always call `update_book_milestone_for_step` after the processing loop |
| Adding a new `*_milestone` without updating stale_watchdog | Add to both `where_conditions` and `update_values` in stale_watchdog |
| Adding a new step without updating event_dispatcher | Add `event_type` handler so the pipeline stays reactive |
| `str(exc)` stored in DB without truncation | Always `str(exc)[:500]` — column has a size limit |
| `retry_count = page.retry_count + 1` in Python | Use SQL-side `retry_count=Page.retry_count + 1` — safe under concurrency |
| New operational scripts in `services/worker/` | All scripts go in the project root `scripts/` folder |
| `print()` for debugging | `log_json(logger, logging.DEBUG, ...)` |

---

## Workflow

1. **Migration first** — add the `.sql` file and apply it if a new column or table is needed.
2. **Update ORM model** — add the `Mapped` field to `models.py`.
3. **Write / extend the service** — add processing logic to `packages/backend-core/app/services/`; it must have no knowledge of arq or `AsyncSession` lifecycle.
4. **Write the scanner** — claim with `FOR UPDATE SKIP LOCKED`, transition to `in_progress`, call `BookMilestoneService`, commit, enqueue with `_job_id`.
5. **Write the job** — per-page session isolation, `succeeded`/`failed` + `PipelineEvent` + `BookMilestoneService` at the end.
6. **Register both** — `WorkerSettings.functions` for the job, `WorkerSettings.cron_jobs` for the scanner.
7. **Update stale_watchdog** — add the new `*_milestone` to `where_conditions` and `update_values`.
8. **Update event_dispatcher** — add the `event_type` handler if the new step should trigger downstream work reactively.
9. **Add system_config keys** — seed any new config keys (model name, limits) via `packages/backend-core/app/db/seeds.py` or a migration.
10. **Write tests** — at minimum: happy path, page failure path, empty-work (scanner finds nothing).
11. **Rebuild** — `./deploy/local/rebuild-and-restart.sh worker`.
