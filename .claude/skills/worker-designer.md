# Worker Job Designer Skill — Kitabim AI

You are designing and implementing background processing jobs for the kitabim-ai worker service. The worker runs as a separate Docker container, processes the book pipeline (OCR → Chunking → Embedding → Spell-check), and executes periodic maintenance tasks.

---

## Architecture Overview

The worker has two types of async tasks:

| Type | Location | Trigger | Purpose |
|------|----------|---------|---------|
| **Scanner** | `services/worker/scanners/` | arq cron (every 1–30 min) | Claims idle work, transitions milestones to `in_progress`, enqueues jobs |
| **Job** | `services/worker/jobs/` | Scanner via `redis.enqueue_job()` | Does the actual heavy work (LLM calls, file I/O, embeddings) per claimed batch |

Scanners are **lightweight** — they only query, claim, and dispatch. Jobs are **heavy** — they call external APIs, process files, and update results.

Both are registered in `services/worker/worker.py`.

---

## Pipeline State Machine

Every `Page` row tracks four milestone columns, each following this state flow:

```
idle → in_progress → succeeded
                  ↘ failed  ──(retry_count < max)──→ idle (reset by pipeline_driver)
                             ──(retry_count ≥ max)──→ stays failed (book → error)
```

**Milestone columns on `Page`:**
- `ocr_milestone`
- `chunking_milestone`
- `embedding_milestone`
- `spell_check_milestone`

**Dependency chain** (each step requires the previous to be `succeeded`):
```
ocr_milestone=idle → OCR scanner claims → ocr job runs
  ↓ ocr_milestone=succeeded
chunking_milestone=idle → Chunking scanner claims
  ↓ chunking_milestone=succeeded
embedding_milestone=idle → Embedding scanner claims
  ↓ embedding_milestone=succeeded
spell_check_milestone=idle → Spell-check scanner claims (optional step)
```

**Book-level milestones** (denormalized on `Book`): `ocr_milestone`, `chunking_milestone`, `embedding_milestone`, `spell_check_milestone`. Always call `BookMilestoneService` after changing page milestones.

**Pipeline Driver** (`scanners/pipeline_driver.py`) runs every minute and:
1. Initializes new pages (`ocr_milestone = idle`)
2. Resets `failed` milestones back to `idle` when `retry_count < max_retries`
3. Marks books `ready` / `error` when all pages reach terminal state

**Stale Watchdog** (`scanners/stale_watchdog.py`) runs every 30 minutes and resets any `in_progress` page not updated within 30 minutes back to `idle` — handles crashed jobs.

---

## Scanner Pattern

Scanners claim pages atomically using `FOR UPDATE SKIP LOCKED` (prevents double-claiming when multiple worker instances run). They commit the claim, then enqueue the job **outside** the session.

```python
# services/worker/scanners/my_scanner.py
"""
My Scanner — claims idle my_step pages and dispatches MyJob.
Runs every 1 minute.
"""
from __future__ import annotations

import logging
from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page
from app.db.repositories.system_configs import SystemConfigsRepository
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.my_scanner")


async def run_my_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        page_limit = int(await config_repo.get_value("scanner_page_limit", "100"))

        # Claim idle pages: previous step succeeded AND this step is idle.
        id_stmt = (
            select(Page.id, Page.book_id)
            .where(
                Page.prev_milestone == "succeeded",   # dependency gate
                Page.my_milestone == "idle",
            )
            .with_for_update(skip_locked=True)        # atomic claim
            .limit(page_limit)
        )
        result = await session.execute(id_stmt)
        rows = result.fetchall()
        page_ids = [row[0] for row in rows]
        book_ids = list({row[1] for row in rows})

        if not page_ids:
            return

        # Transition claimed pages to in_progress
        await session.execute(
            update(Page)
            .where(Page.id.in_(page_ids))
            .values(my_milestone="in_progress", last_updated=func.now())
        )
        # Update denormalized book milestones
        for book_id in book_ids:
            await BookMilestoneService.update_book_milestone_for_step(session, book_id, "my_step")
        await session.commit()

    # Enqueue OUTSIDE the session — session must be closed first
    await redis.enqueue_job(
        "my_job",
        page_ids=page_ids,
        _job_id="my_job:batch",           # deduplication key
    )
    log_json(logger, logging.INFO, "my job dispatched", page_count=len(page_ids))
```

**When to group by book vs. across books:**
- Group **by book** (like OCR scanner) when the job needs a shared resource per book (e.g. downloading the PDF once).
- Claim **across all books** (like embedding scanner) when the job only needs data already in the DB.

---

## Job Pattern

Jobs process one page at a time, each in its own `async with async_session_factory()` scope. One page failure must never abort other pages.

```python
# services/worker/jobs/my_job.py
"""
My Job — processes a batch of claimed pages.

Receives: page_ids (list of Page.id already set to in_progress by scanner).
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page, PipelineEvent
from app.db.repositories.system_configs import SystemConfigsRepository
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.my_job")


async def my_job(ctx, page_ids: List[int]) -> None:
    log_json(logger, logging.INFO, "my job started", page_count=len(page_ids))

    # 1. Read dynamic config (DB-driven, hot-reloadable)
    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        my_model = await config_repo.get_value("my_model_config_key")
        if not my_model:
            raise RuntimeError("system_config 'my_model_config_key' is not set")

    # 2. Load page records (separate session — read-only)
    async with db_session.async_session_factory() as session:
        result = await session.execute(select(Page).where(Page.id.in_(page_ids)))
        pages = list(result.scalars().all())

    succeeded = 0
    failed = 0

    # 3. Process one page at a time — isolated session per page
    for page in pages:
        try:
            # Do the work (LLM call, transformation, etc.)
            result_data = await do_my_work(page, my_model)

            # Write success — milestone, result, PipelineEvent in one commit
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Page)
                    .where(Page.id == page.id)
                    .values(
                        my_result_field=result_data,
                        my_milestone="succeeded",
                        last_updated=func.now(),
                    )
                )
                session.add(PipelineEvent(
                    page_id=page.id,
                    event_type="my_step_succeeded",
                ))
                await session.commit()

            succeeded += 1
            log_json(logger, logging.DEBUG, "page succeeded",
                     book_id=page.book_id, page=page.page_number)

        except Exception as exc:
            # Write failure — increment retry, store error, never re-raise
            async with db_session.async_session_factory() as session:
                error_msg = str(exc)[:500]   # truncate — column has size limit
                await session.execute(
                    update(Page)
                    .where(Page.id == page.id)
                    .values(
                        my_milestone="failed",
                        retry_count=Page.retry_count + 1,
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

    # 4. Update book-level milestone after the batch
    if pages:
        book_id = pages[0].book_id
        async with db_session.async_session_factory() as session:
            await BookMilestoneService.update_book_milestone_for_step(session, book_id, "my_step")
            await session.commit()

    log_json(logger, logging.INFO, "my job completed", succeeded=succeeded, failed=failed)
```

---

## Book-Level Jobs (non-page)

Some jobs operate on an entire book, not individual pages (e.g. `summary_job`). They use a single session for the read phase, a separate session for the write phase, and catch all exceptions at the top level (re-raising so arq records the failure).

```python
async def my_book_job(ctx, book_id: str) -> None:
    log_json(logger, logging.INFO, "my book job started", book_id=book_id)
    try:
        async with db_session.async_session_factory() as session:
            # read phase
            ...

        result = await call_external_api(...)

        async with db_session.async_session_factory() as session:
            # write phase
            await repo.upsert(book_id=book_id, result=result)
            await session.commit()

        log_json(logger, logging.INFO, "my book job completed", book_id=book_id)

    except Exception as exc:
        log_json(logger, logging.ERROR, "my book job failed",
                 book_id=book_id, error=str(exc))
        raise   # let arq record the failure; do NOT swallow for book-level jobs
```

---

## Concurrency Control

When a job fans out over many pages concurrently, always bound parallelism with a semaphore. The limit should come from `SystemConfigsRepository` or `settings`, not be hardcoded.

```python
import asyncio

async with db_session.async_session_factory() as session:
    config_repo = SystemConfigsRepository(session)
    max_parallel = int(await config_repo.get_value("my_max_parallel_pages", "4"))

sem = asyncio.Semaphore(max_parallel)

async def bounded(page: Page) -> None:
    async with sem:
        await process_page(page)

await asyncio.gather(*[bounded(p) for p in pages])
```

---

## Registering in worker.py

After creating a scanner and/or job, register them in `services/worker/worker.py`:

```python
# Add import
from scanners.my_scanner import run_my_scanner
from jobs.my_job import my_job

class WorkerSettings:
    functions = [
        ...,
        my_job,          # job function registered here
    ]

    cron_jobs = [
        ...,
        cron(run_my_scanner),                        # every 1 min (default)
        cron(run_my_scanner, minute={0, 30}),        # every 30 min
        cron(run_my_scanner, hour=3, minute=0),      # daily at 3 AM
        cron(run_my_scanner, run_at_startup=True),   # also runs on worker boot
    ]
```

---

## Dynamic Config via SystemConfigsRepository

**Never hardcode tuneable parameters** in job or scanner files. Read them from the DB at runtime — this allows hot changes without redeployment:

```python
async with db_session.async_session_factory() as session:
    config_repo = SystemConfigsRepository(session)
    model_name  = await config_repo.get_value("gemini_ocr_model")          # required
    page_limit  = int(await config_repo.get_value("scanner_page_limit", "100"))  # with default
    max_retries = int(await config_repo.get_value("ocr_max_retry_count", "3"))
```

**Raise `RuntimeError`** (not `HTTPException`) when a required config key is missing — arq will log the failure and retry.

**Use `settings.*`** only for infrastructure config (DB URL, Redis URL, file paths, batch sizes) that requires a redeploy to change.

---

## PipelineEvent

Emit a `PipelineEvent` for every page milestone transition. This provides an audit trail and feeds the `event_dispatcher` scanner:

```python
from app.db.models import PipelineEvent

session.add(PipelineEvent(
    page_id=page.id,
    event_type="my_step_succeeded",          # or "my_step_failed"
    payload='{"extra": "context"}',          # optional JSON string
))
```

Naming convention for `event_type`: `{step}_{outcome}` — e.g. `ocr_succeeded`, `chunking_failed`, `embedding_succeeded`.

---

## Job Deduplication

Pass `_job_id` to `enqueue_job` to prevent the same job being queued twice if the scanner runs again before the job completes:

```python
# Page-level job (one per book): deduplicate by book
await redis.enqueue_job("ocr_job", book_id=book_id, page_ids=page_ids,
                        _job_id=f"ocr:{book_id}")

# Cross-book batch job: use a stable identifier
await redis.enqueue_job("embedding_job", page_ids=page_ids,
                        _job_id="embedding_job:batch")

# Book-level one-off job:
await redis.enqueue_job("summary_job", book_id=book_id,
                        _job_id=f"summary:{book_id}")
```

---

## Logger Naming Convention

```python
logger = logging.getLogger("app.worker.my_scanner")   # scanners
logger = logging.getLogger("app.worker.my_job")       # jobs
```

Always use `log_json` — never bare `logger.info("string")`:

```python
from app.utils.observability import log_json

log_json(logger, logging.INFO,  "job started",   book_id=book_id, page_count=len(page_ids))
log_json(logger, logging.DEBUG, "page ok",       book_id=page.book_id, page=page.page_number)
log_json(logger, logging.WARNING, "page failed", book_id=page.book_id, error=str(exc))
log_json(logger, logging.ERROR, "job aborted",   book_id=book_id, error=str(exc))
```

---

## Maintenance / Cleanup Scanners

For periodic housekeeping (deleting old events, resetting stale state):

```python
async def run_my_maintenance_scanner(ctx) -> None:
    try:
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            retention_days = int(
                await config_repo.get_value("my_retention_days") or settings.my_retention_days
            )
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

            result = await session.execute(
                delete(MyModel).where(MyModel.created_at < cutoff)
            )
            await session.commit()

        log_json(logger, logging.INFO, "maintenance done", deleted=result.rowcount)

    except Exception as exc:
        log_json(logger, logging.ERROR, "maintenance failed", error=str(exc))
        # Do NOT re-raise — maintenance failures are non-critical
```

---

## Workflow

1. **Define the milestone** — add the new `*_milestone` column to the `Page` model and a migration file.
2. **Wire the dependency** — decide which prior milestone must be `succeeded` before this step can claim a page.
3. **Write the scanner** — claim with `FOR UPDATE SKIP LOCKED`, transition to `in_progress`, update book milestone, enqueue with `_job_id`.
4. **Write the job** — isolated session per page, `succeeded`/`failed` + `PipelineEvent` in each outcome, book milestone update at the end.
5. **Register both** — add job to `WorkerSettings.functions`, scanner to `WorkerSettings.cron_jobs`.
6. **Add config keys** — add tuneable params (model name, page limit, max parallel) to the DB via seeds or a migration; never hardcode them.
7. **Stale watchdog coverage** — add the new `*_milestone` to the watchdog's `where_conditions` and `update_values` in `stale_watchdog.py`.
8. **Rebuild** — `./deploy/local/rebuild-and-restart.sh worker`.
