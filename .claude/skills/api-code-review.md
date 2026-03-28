# API Code Review Skill — Kitabim AI Backend

You are reviewing backend code changes for the kitabim-ai FastAPI service. Cover all changed files across `services/backend/`, `services/worker/`, and `packages/backend-core/`. Be direct and specific — cite file paths and line numbers. Label every issue as **blocking** (incorrect behaviour, security risk, data loss) or **suggestion** (quality, style, performance).

---

## Review Checklist

Work through each category that applies to the change.

---

### 1. Correctness

- [ ] All async functions are `await`-ed — no unawaited coroutines
- [ ] `await session.commit()` is called after every write; `await session.refresh(obj)` after inserts/updates that need the DB-generated state
- [ ] `await session.rollback()` is called in every `except` block that catches a DB error before re-raising or continuing
- [ ] No `session.execute()` or ORM calls in endpoint files or service files — all DB access goes through repository methods
- [ ] No business logic (branching, calculations, orchestration) inside repository methods — repositories are CRUD only
- [ ] Worker jobs create a **new `async with async_session_factory()`** per page/item — never one shared session across all items
- [ ] Background task errors are caught per-item so one failure does not abort the entire batch
- [ ] `scalar_one_or_none()` is used instead of `scalar_one()` when the record may not exist; `scalar_one()` raises if the row is missing
- [ ] `model_dump(exclude_unset=True)` is used on PATCH/update request bodies — not `model_dump()` (which overwrites with `None`)
- [ ] SQLAlchemy relationships are not accessed after the session closes (lazy-load outside session context)

---

### 2. Security & Authentication

- [ ] Every write endpoint (`POST`, `PUT`, `PATCH`, `DELETE`) has an auth dependency — minimum `require_reader`; destructive or admin operations use `require_admin`
- [ ] No endpoint returns another user's private data without ownership or role check
- [ ] `get_current_user_optional` is used only for endpoints that are genuinely public (guest + auth both valid) — not as a shortcut to skip auth
- [ ] No secrets, tokens, API keys, or passwords are logged — check `log_json` calls and exception handlers
- [ ] IP addresses are hashed before storing (use `security.hash_ip()` from `app.utils.security`) — never stored raw
- [ ] File uploads validate MIME type and extension — not just the filename
- [ ] No raw SQL string interpolation — always use SQLAlchemy bound parameters
- [ ] `enforce_app_id` middleware cannot be bypassed by a new public route that should be protected

---

### 3. Architecture & Layering

- [ ] The call graph flows: **endpoint → service → repository → DB** — no layer is skipped
- [ ] Services do not import from `services/backend/` (auth deps, FastAPI) — they are framework-agnostic
- [ ] Endpoint files do not import SQLAlchemy models directly or call `session.execute()` — only repositories do
- [ ] New shared logic is placed in `packages/backend-core/` not duplicated across `services/backend/` and `services/worker/`
- [ ] Background job enqueueing is done via `arq` Redis pool — never via a `BackgroundTasks` task that does heavy I/O directly in the request cycle
- [ ] `os.environ.get()` is not called in application code — all config comes from `settings.*` (`core/config.py`)

---

### 4. Database & Migrations

- [ ] Every new table or column has a corresponding SQL migration file in `packages/backend-core/migrations/NNN_description.sql` with the correct sequential number
- [ ] New string columns that hold enum-like values have a `CheckConstraint` in the model
- [ ] Foreign keys specify `ondelete=` behaviour (`CASCADE`, `SET NULL`, or `RESTRICT`) — not left as default
- [ ] `Mapped` type annotations match the actual column type (`Mapped[str]` vs `Mapped[Optional[str]]` for nullable columns)
- [ ] New indexes are added for columns used in `WHERE` clauses of frequently-run queries
- [ ] `last_updated` is present on all mutable models with `onupdate=func.now()`
- [ ] Bulk operations use `pg_insert(...).on_conflict_do_update(...)` not a loop of individual upserts
- [ ] `await session.commit()` is not called inside a repository method — the caller (service or endpoint) owns the transaction boundary

---

### 5. Caching

- [ ] Cache keys use templates from `app/core/cache_config.py` — no hardcoded key strings in endpoint or service files
- [ ] Every `cache_service.set()` call uses `model_dump(mode='json')` to serialise — not `model_dump()` (breaks on `datetime`, `Enum`, `UUID`)
- [ ] Cache is **invalidated** after every create, update, and delete that affects the cached data
- [ ] New cache TTLs are defined in `core/config.py` as `Settings` fields — not hardcoded integers in call sites
- [ ] Read-through pattern is used (`get → miss → fetch → set`) not write-through only
- [ ] Admin-only queries are not cached (or are explicitly opted in with justification)

---

### 6. Worker Jobs

- [ ] Each job function is registered in `WorkerSettings.functions` in `services/worker/worker.py`
- [ ] Job functions catch exceptions per-item, update `item.status = "error"` and `item.last_error`, and commit — they do not propagate exceptions that abort the whole job
- [ ] `item.retry_count` is incremented on failure
- [ ] Concurrency is bounded with `asyncio.Semaphore` when the job fans out across many pages
- [ ] `log_json` is called at job start, completion, and on error — with relevant IDs as structured fields
- [ ] The job does not create a single session for the entire run — a new `async with async_session_factory()` is used per item
- [ ] Pipeline state (`status`, milestone field) is updated atomically with the work result in the same `commit()`

---

### 7. Error Handling & HTTP Status Codes

- [ ] `404` is raised when a requested resource does not exist — not `400`
- [ ] `400` is for invalid input (wrong type, validation failure, business rule violation) — not for missing resources
- [ ] `403` is for authorisation failures — auth deps raise this automatically; do not use `401` manually
- [ ] `409 Conflict` is used for duplicate-resource errors (not `400`)
- [ ] `429 Too Many Requests` is used for rate/usage limit errors
- [ ] All `HTTPException` `detail=` values use `t("errors.key")` — no hardcoded English strings visible to the client
- [ ] The global exception handler in `main.py` is not bypassed by catching `Exception` and returning a raw `Response` — re-raise or raise `HTTPException`
- [ ] `record_book_error(session, book_id, message)` is called for book-level pipeline failures

---

### 8. i18n

- [ ] Every `HTTPException(detail=...)` uses `t("errors.key")` from `app.core.i18n`
- [ ] New error keys are added to **both** `services/backend/locales/ug.json` and `services/backend/locales/en.json`
- [ ] No user-facing string literals are hardcoded in Python source files
- [ ] `t()` is not called at module import time (it reads a `ContextVar` — call it inside the request/job context only)

---

### 9. Pydantic Schemas

- [ ] All new request/response schemas use the camelCase config:
  ```python
  model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
  ```
- [ ] Response schemas use `from_attributes=True` so they work with `model_validate(orm_obj)` directly
- [ ] Optional fields in update schemas default to `None` and endpoints use `exclude_unset=True` — no accidental field erasure
- [ ] Schemas do not import from `services/backend/` — they live in `packages/backend-core/`
- [ ] No `Any` type in schemas unless wrapping a genuinely unknown external payload (flag for future typing)

---

### 10. Observability & Logging

- [ ] `log_json(logger, level, "message", key=value)` is used — not `logger.info(f"message {var}")`
- [ ] `print()` is not present in any backend or worker file
- [ ] Every worker job logs at start and end with the primary entity ID as a structured field
- [ ] Errors log `error=str(e)` and relevant context IDs — not just the exception string alone
- [ ] No sensitive data (tokens, passwords, full request bodies, PII) appears in any log call
- [ ] New loggers are created with `logging.getLogger(__name__)` — not a shared global logger

---

### 11. Performance

- [ ] N+1 queries are avoided — related data is loaded with `joinedload()` / `selectinload()` or a single aggregation query, not a loop of per-item fetches
- [ ] Paginated endpoints have `LIMIT` and `OFFSET` — never `result.scalars().all()` on an unbounded table
- [ ] Large file content (PDFs, full book text) is streamed — not loaded entirely into memory in one call
- [ ] `asyncio.gather()` is used for concurrent independent async calls — not sequential `await` in a loop when parallelism is safe
- [ ] Embeddings and LLM calls are batched (see `embed_batch_size` in config) — not one call per item

---

### 12. Testing

- [ ] New endpoints have at least a happy-path and a 404/403 test
- [ ] New service functions have unit tests with a mocked session
- [ ] Tests use `httpx.AsyncClient` with `ASGITransport(app=app)` — not `TestClient` (which is sync)
- [ ] Auth is overridden via `app.dependency_overrides[get_current_user]` — not by hardcoding tokens
- [ ] External services (Gemini, GCS, Redis) are mocked with `unittest.mock.patch` or `AsyncMock` — no real network calls in tests
- [ ] `app.dependency_overrides.clear()` is called in teardown (fixture `yield` or `autouse` cleanup)

---

## How to Report

For each issue:

1. **File and line** — e.g. `services/backend/api/endpoints/books.py:142`
2. **Severity** — `blocking` or `suggestion`
3. **What's wrong** — one sentence
4. **How to fix** — concrete change or minimal code snippet

Group by file. End with a verdict: **Approve**, **Approve with suggestions**, or **Request changes**.

---

## Saving the Report

After completing the review, write the report to:

```
docs/<branch-name>/code-review-api-<YYYY-MM-DD>.md
```

1. Get the branch name: `git branch --show-current`
2. Use today's date in `YYYY-MM-DD` format.
3. Create the file with this structure:

```markdown
# API Code Review — <YYYY-MM-DD>

**Branch:** <branch-name>
**Verdict:** Approve | Approve with suggestions | Request changes

## Issues

### `path/to/file.py`

- **[blocking]** Line 142 — What's wrong. How to fix.
- **[suggestion]** Line 201 — What's wrong. How to fix.

### `path/to/other.py`

- **[suggestion]** Line 12 — What's wrong. How to fix.

## Summary

<1–3 sentence summary of the overall state of the change.>
```

If no issues are found, the Issues section should say "No issues found."
