# Worker Code Review Skill — Kitabim AI

You are reviewing background worker code changes across `services/worker/` and any shared logic in `packages/backend-core/` that the worker depends on. Be direct and specific — cite file paths and line numbers. Label every issue **blocking** (data loss, stuck pipeline, silent failure, security) or **suggestion** (quality, performance, style).

---

## Review Checklist

Work through every applicable category for the diff.

---

### 1. Session Isolation (most critical)

- [ ] Every page/item in a processing loop has its **own** `async with db_session.async_session_factory() as session:` — no session is shared across loop iterations
- [ ] The page-load read phase uses a **separate** session that is closed before the processing loop begins — ORM objects from it are not accessed after the session closes (lazy-load trap)
- [ ] The config-read session is **separate** from the processing sessions — closed before any concurrency
- [ ] The book-milestone update at the end of the job uses a **fresh** session — not the one from the last page
- [ ] `await session.rollback()` is **not** manually called in a job's `except` block — the `async with` context manager rolls back automatically; a manual rollback followed by another `async with` block is the correct pattern
- [ ] No `session.execute()` calls leak outside the `async with` block (accessing the session after `__aexit__` is a silent bug)

---

### 2. Pipeline Correctness

- [ ] **Milestone transitions** are atomic with the result write and the `PipelineEvent` — all three happen in the same `session.commit()`
- [ ] **`retry_count`** is incremented using a SQL-side expression `retry_count=Page.retry_count + 1`, not a Python-side read-modify-write (`page.retry_count + 1`) which is unsafe under concurrency
- [ ] **Error messages** stored in `page.error` are truncated: `str(exc)[:500]` — never the raw `str(exc)` which can overflow the column
- [ ] **`BookMilestoneService.update_book_milestone_for_step`** is called after the processing loop in a fresh session, with an explicit `await session.commit()`
- [ ] **`PipelineEvent`** is emitted for both `succeeded` and `failed` outcomes — not only on success
- [ ] **`event_type`** follows the convention `{step}_{succeeded|failed}` (e.g. `ocr_succeeded`, `chunking_failed`)
- [ ] A new pipeline step updates **`event_dispatcher.py`** so the reactive pipeline handles the new `event_type`
- [ ] A new `*_milestone` column is added to **`stale_watchdog.py`** in both `where_conditions` and `update_values` — without this, stuck pages are never recovered

---

### 3. Scanner Correctness

- [ ] Page claiming uses `.with_for_update(skip_locked=True)` — without this, two scanner instances can double-claim the same pages
- [ ] The `UPDATE` to set `in_progress` and the `commit()` happen **inside** the `async with` session block
- [ ] `redis.enqueue_job(...)` is called **outside** the session block — after the session is closed and committed
- [ ] `_job_id=` is passed to `enqueue_job` to deduplicate — a scanner that runs every minute without deduplication floods the queue with duplicate jobs
- [ ] The scanner returns early (without enqueueing) when `page_ids` is empty — no empty jobs dispatched
- [ ] `BookMilestoneService.update_book_milestone_for_step` is called inside the claim session before committing
- [ ] The dependency gate (`prev_milestone == "succeeded"` in the `WHERE` clause) is correct for the step — e.g. chunking must check `ocr_milestone == "succeeded"`, embedding must check `chunking_milestone == "succeeded"`

---

### 4. Error Handling

- [ ] **Page-level jobs**: exceptions are caught per page, milestone set to `failed`, `retry_count` incremented, `PipelineEvent` emitted — the exception is **never re-raised**, so other pages continue
- [ ] **Book-level jobs** (`summary_job`, `auto_correct_job` style): top-level `try/except` catches, logs, and **re-raises** — so arq records the failure and can retry
- [ ] **Scanners** and **maintenance tasks**: `try/except` at the top level, log the error, **do not re-raise** — a scanner failure must not crash the worker process
- [ ] No bare `except:` or `except Exception as e: pass` — every caught exception is at minimum logged with `log_json`
- [ ] `RuntimeError` (not `HTTPException`) is raised when a required `system_config` key is missing

---

### 5. Configuration

- [ ] Tuneable parameters (model names, page limits, batch sizes, retry counts, parallel limits) are read from `SystemConfigsRepository` at job/scanner startup — not hardcoded in the function body
- [ ] `settings.*` is used only for infrastructure values (DB URL, Redis URL, file paths, `embed_batch_size`) that require a redeployment to change
- [ ] `os.environ.get()` does not appear anywhere in job or scanner files
- [ ] New tuneable parameters have a sensible default in `get_value("key", "default")` so the job does not fail if the config key has not yet been seeded
- [ ] Required config keys (no default) raise `RuntimeError` immediately at job start — not silently produce `None` and fail further in

---

### 6. Concurrency

- [ ] When a job fans out with `asyncio.gather`, parallelism is bounded by `asyncio.Semaphore(max_parallel)` — unbounded `gather` over hundreds of pages will exhaust DB connections and LLM rate limits
- [ ] `max_parallel` comes from `SystemConfigsRepository` — not a hardcoded integer
- [ ] Semaphore is created **once** before the gather, not inside the coroutine (creating a new semaphore per page is a no-op)
- [ ] `asyncio.gather` is used only when pages are independent — steps that must happen in sequence use `for page in pages:` with `await`

---

### 7. Registration

- [ ] New job functions are added to `WorkerSettings.functions` in `worker.py`
- [ ] New scanner functions are added to `WorkerSettings.cron_jobs` with the correct schedule
- [ ] Cron schedule is appropriate: per-minute for active pipeline scanners, every 5–30 min for backfill/maintenance
- [ ] `run_at_startup=True` is used only when the scanner must execute on worker boot (e.g. `pipeline_driver`, `event_dispatcher`) — not for every scanner
- [ ] `hour=3, minute=0` (daily at 3 AM) is used for heavy maintenance/bulk tasks to avoid peak hours

---

### 8. Storage & External Services

- [ ] `storage_service` (not raw `open()` or `gcs` SDK calls) is used for all file reads and writes
- [ ] Large files (PDFs) are **downloaded once per job**, not once per page — verify the download happens at the job level before the page loop (see `ocr_job.py` pattern)
- [ ] Local temp files are cleaned up or written to `settings.uploads_dir` — never `/tmp` with no cleanup
- [ ] LLM calls are **batched** using `settings.embed_batch_size` — not one call per chunk/page
- [ ] `GeminiEmbeddings` model instance is created **once** per job — not once per page

---

### 9. Database & Migrations

- [ ] Every new table or column has a corresponding SQL migration file `packages/backend-core/migrations/NNN_description.sql` with the next sequential number
- [ ] New `*_milestone` string columns have a `CheckConstraint` limiting values to the valid milestone states: `idle`, `in_progress`, `succeeded`, `failed`, `error`
- [ ] Bulk updates use `update(Model).where(...).values(...)` (single SQL statement) — not a loop of individual `session.execute(update(...).where(id == x))` calls
- [ ] `last_updated=func.now()` is included in every milestone update — the stale watchdog uses this column to detect stuck pages

---

### 10. Logging & Observability

- [ ] `log_json(logger, level, "message", key=value, ...)` is used — not `logger.info(f"string {var}")` or `print()`
- [ ] Logger is named `logging.getLogger("app.worker.<component>")` — not a generic name or `__name__` (which resolves to the module path, inconsistent with the project convention)
- [ ] Job lifecycle is logged: started (with `page_count` or `book_id`), completed (with `succeeded`/`failed` counts)
- [ ] Per-page outcomes are logged at `DEBUG` for success, `WARNING` for failure — not `ERROR` for expected retryable failures
- [ ] `ERROR` level is reserved for unrecoverable failures (PDF unavailable, missing required config, job abort)
- [ ] No secrets, tokens, or full text content appear in any log call
- [ ] `error=str(exc)` is always a structured field — not interpolated into the message string

---

### 11. Code Placement

- [ ] Worker-specific code (job functions, scanner functions) lives in `services/worker/` — not in `packages/backend-core/`
- [ ] Reusable business logic (text processing, LLM calls, chunking) lives in `packages/backend-core/app/services/` — not duplicated in a job file
- [ ] Operational / debug scripts are placed in the project root `scripts/` folder — not in `services/worker/`
- [ ] Documentation goes in `docs/<branch-name>/` (e.g. `docs/main/`) — not inline markdown files in `services/worker/`

---

### 12. Testing

- [ ] New job functions have tests for: happy path (all pages succeed), page failure path (one page fails, others continue), empty input (`page_ids=[]`)
- [ ] New scanner functions have tests for: pages found and dispatched, no pages found (early return, no `enqueue_job`)
- [ ] `db_session.async_session_factory` is mocked with `patch(...)` — no real DB connections in unit tests
- [ ] External services (Gemini, GCS, Redis) are mocked with `AsyncMock` — no real API calls in tests
- [ ] `mock_redis.enqueue_job` is asserted to verify the correct job name and `page_ids` / `book_id` arguments
- [ ] The failure path test asserts that `milestone="failed"` and `retry_count` increment appear in the DB update call — not just that no exception was raised

---

## How to Report

For each issue:

1. **File and line** — e.g. `services/worker/jobs/embedding_job.py:61`
2. **Severity** — `blocking` or `suggestion`
3. **What's wrong** — one sentence
4. **How to fix** — concrete change or minimal code snippet

Group by file. End with a verdict: **Approve**, **Approve with suggestions**, or **Request changes**.

---

## Saving the Report

After completing the review, write the report to:

```
docs/<branch-name>/code-review-worker-<YYYY-MM-DD>.md
```

1. Get the branch name: `git branch --show-current`
2. Use today's date in `YYYY-MM-DD` format.
3. Create the file with this structure:

```markdown
# Worker Code Review — <YYYY-MM-DD>

**Branch:** <branch-name>
**Verdict:** Approve | Approve with suggestions | Request changes

## Issues

### `path/to/file.py`

- **[blocking]** Line 61 — What's wrong. How to fix.
- **[suggestion]** Line 88 — What's wrong. How to fix.

### `path/to/other.py`

- **[suggestion]** Line 12 — What's wrong. How to fix.

## Summary

<1–3 sentence summary of the overall state of the change.>
```

If no issues are found, the Issues section should say "No issues found."
