# LLM Spell-Correction Hardening & Data Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Resolve all 4 blocking issues and 11 suggestions from `code-review-api-2026-10-14.md` across database constraints, repository abstraction, data integrity, concurrency/lifecycle safety, and Gemini Batch API processing.

**Architecture:** 
1. Database schema updates enforce status enums with PostgreSQL `CHECK` constraints and add original text tracking for undo/diff capability.
2. Direct raw SQL in API routers and services is replaced by clean methods in `PagesRepository`.
3. LLM text apply paths invalidate stale `PageSpellIssue` rows, reset `spell_check_milestone`, normalize Uyghur characters, and guard against offset mismatches in dictionary splices.
4. Worker jobs decouple database connection lifetimes from long-running LLM API calls, safely catch and rollback failed transactions, use unique arq job IDs, and recover stuck `in_progress` pages in the stale watchdog.
5. The Gemini Batch poller scanner drains active batches regardless of feature flag toggles, executes SDK calls in worker threads without blocking the event loop, handles download failures accurately, and protects concurrent manual edits from overwrite.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 (asyncio), PostgreSQL, ARQ, Redis, Google GenAI SDK, Pytest.

## Global Constraints
- ALL LLM system prompts in code MUST remain in English (per repo `AGENTS.md`).
- Business logic lives in `packages/backend-core/app/`; router endpoints only orchestrate HTTP requests.
- All operational scripts and tests use `./venv/bin/pytest`.
- Docker Compose is used for local services; PostgreSQL runs on host `localhost:5432`.
- No destructive graph or volume resets.

---

### Task 1: Database Migration & Model Constraints (Category 5 & Category 2.3)

**Files:**
- Create: `packages/backend-core/migrations/092_add_llm_spell_check_constraints_and_diff.sql`
- Create: `packages/backend-core/migrations/092_rollback_add_llm_spell_check_constraints_and_diff.sql`
- Modify: `packages/backend-core/app/db/models.py:212-265, 467-515`

**Interfaces:**
- Produces: 
  - `pages.llm_spell_check_status_check` (`idle`, `in_progress`, `succeeded`, `failed`)
  - `batch_llm_spell_check_jobs.status_check` (`submitting`, `running`, `succeeded`, `failed`, `cancelled`, `expired`)
  - `pages.prev_text` (`TEXT NULL`)

- [x] **Step 1: Write migration and rollback SQL files**

Create `packages/backend-core/migrations/092_add_llm_spell_check_constraints_and_diff.sql`:
```sql
-- Migration: 092_add_llm_spell_check_constraints_and_diff.sql
-- Description: Add check constraints for llm_spell_check_status and batch job status,
--              plus prev_text column on pages for undo/diff tracking.
-- Author: Kitabim.AI
-- Date: 2026-10-14

BEGIN;

-- 1. Add column to store original text before LLM correction
ALTER TABLE public.pages
    ADD COLUMN IF NOT EXISTS prev_text TEXT NULL;

-- 2. Add CHECK constraint on pages.llm_spell_check_status
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pages_llm_spell_check_status_check'
    ) THEN
        ALTER TABLE public.pages
            ADD CONSTRAINT pages_llm_spell_check_status_check
            CHECK (llm_spell_check_status IN ('idle', 'in_progress', 'succeeded', 'failed'));
    END IF;
END $$;

-- 3. Add CHECK constraint on batch_llm_spell_check_jobs.status
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'batch_llm_spell_check_jobs_status_check'
    ) THEN
        ALTER TABLE public.batch_llm_spell_check_jobs
            ADD CONSTRAINT batch_llm_spell_check_jobs_status_check
            CHECK (status IN ('submitting', 'running', 'succeeded', 'failed', 'cancelled', 'expired'));
    END IF;
END $$;

COMMIT;
```

Create `packages/backend-core/migrations/092_rollback_add_llm_spell_check_constraints_and_diff.sql`:
```sql
-- Migration Rollback: 092_rollback_add_llm_spell_check_constraints_and_diff.sql
BEGIN;

ALTER TABLE public.pages
    DROP CONSTRAINT IF EXISTS pages_llm_spell_check_status_check;

ALTER TABLE public.batch_llm_spell_check_jobs
    DROP CONSTRAINT IF EXISTS batch_llm_spell_check_jobs_status_check;

ALTER TABLE public.pages
    DROP COLUMN IF EXISTS prev_text;

COMMIT;
```

- [x] **Step 2: Update SQLAlchemy models in `models.py`**

In `packages/backend-core/app/db/models.py`:
Add column `prev_text` to `Page`:
```python
    prev_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
```
Add `pages_llm_spell_check_status_check` to `Page.__table_args__`:
```python
    __table_args__ = (
        UniqueConstraint(
            "book_id", "page_number", name="pages_book_id_page_number_key"
        ),
        CheckConstraint(
            "status IN ('pending', 'ocr_processing', 'ocr_done', 'chunked', 'indexing', 'indexed', 'error')",
            name="pages_status_check",
        ),
        CheckConstraint(
            "llm_spell_check_status IN ('idle', 'in_progress', 'succeeded', 'failed')",
            name="pages_llm_spell_check_status_check",
        ),
    )
```
Add `batch_llm_spell_check_jobs_status_check` to `BatchLlmSpellCheckJob.__table_args__`:
```python
    __table_args__ = (
        CheckConstraint(
            "status IN ('submitting', 'running', 'succeeded', 'failed', 'cancelled', 'expired')",
            name="batch_llm_spell_check_jobs_status_check",
        ),
    )
```

- [x] **Step 3: Apply migration to local DB**

Run: `psql -h localhost -U kitabim -d kitabim -f packages/backend-core/migrations/092_add_llm_spell_check_constraints_and_diff.sql`
Verify: `psql -h localhost -U kitabim -d kitabim -c "\d pages"` and check constraint exists.

- [x] **Step 4: Commit**

```bash
git add packages/backend-core/migrations/092* packages/backend-core/app/db/models.py
git commit -m "feat(db): add check constraints and prev_text column for llm spell check"
```

---

### Task 2: Repository Layer Abstractions (Category 1.4 & Category 4.5)

**Files:**
- Modify: `packages/backend-core/app/db/repositories/pages_repository.py`
- Modify: `packages/backend-core/app/db/repositories/books_repository.py`
- Test: `packages/backend-core/tests/app/db/pages_repository_test.py`

**Interfaces:**
- Produces:
  - `PagesRepository.list_eligible_for_llm_spell_check(book_id: str, force: bool = False, stale_timeout_minutes: int = 60) -> List[int]`
  - `PagesRepository.bulk_set_llm_spell_check_status(page_ids: List[int], status: str) -> None`
  - `PagesRepository.get_pages_by_ids(page_ids: List[int]) -> List[Page]`
  - `PagesRepository.get_pages_by_book_id(book_id: str) -> List[Page]`

- [x] **Step 1: Write unit tests in `pages_repository_test.py`**

Add tests for:
1. `list_eligible_for_llm_spell_check` ignores empty/blank text pages.
2. `list_eligible_for_llm_spell_check` ignores `succeeded` pages when `force=False`.
3. `list_eligible_for_llm_spell_check` includes `succeeded` pages when `force=True`.
4. `list_eligible_for_llm_spell_check` includes stuck `in_progress` pages older than `stale_timeout_minutes`.
5. `bulk_set_llm_spell_check_status` sets the given status on all specified page IDs.

Run: `./venv/bin/pytest packages/backend-core/tests/app/db/pages_repository_test.py`
Expected: FAIL with missing methods on `PagesRepository`.

- [x] **Step 2: Implement repository methods in `pages_repository.py`**

In `packages/backend-core/app/db/repositories/pages_repository.py`:
```python
    async def list_eligible_for_llm_spell_check(
        self,
        book_id: str,
        force: bool = False,
        stale_timeout_minutes: int = 60,
    ) -> List[int]:
        """Finds page IDs in a book eligible for LLM spell check.
        Filters out null/empty text pages. If force is False, only includes
        idle/failed pages, or in_progress pages that exceeded stale_timeout_minutes.
        If force is True, includes all non-empty pages not currently active.
        """
        now = datetime.now(timezone.utc)
        stale_threshold = now - timedelta(minutes=stale_timeout_minutes)

        non_empty_cond = and_(
            Page.text.is_not(None),
            func.trim(Page.text) != "",
        )

        if force:
            status_cond = or_(
                Page.llm_spell_check_status != PAGE_MILESTONE_IN_PROGRESS,
                Page.last_updated < stale_threshold,
            )
        else:
            status_cond = or_(
                Page.llm_spell_check_status.in_([PAGE_MILESTONE_IDLE, PAGE_MILESTONE_FAILED]),
                and_(
                    Page.llm_spell_check_status == PAGE_MILESTONE_IN_PROGRESS,
                    Page.last_updated < stale_threshold,
                ),
            )

        stmt = (
            select(Page.id)
            .where(
                Page.book_id == book_id,
                non_empty_cond,
                status_cond,
            )
            .order_by(Page.page_number)
        )
        res = await self.session.execute(stmt)
        return [row[0] for row in res.fetchall()]

    async def bulk_set_llm_spell_check_status(
        self, page_ids: List[int], status: str
    ) -> None:
        if not page_ids:
            return
        stmt = (
            update(Page)
            .where(Page.id.in_(page_ids))
            .values(
                llm_spell_check_status=status,
                last_updated=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)

    async def get_pages_by_ids(self, page_ids: List[int]) -> List[Page]:
        if not page_ids:
            return []
        stmt = select(Page).where(Page.id.in_(page_ids)).order_by(Page.page_number)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_pages_by_book_id(self, book_id: str) -> List[Page]:
        stmt = select(Page).where(Page.book_id == book_id).order_by(Page.page_number)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
```

- [x] **Step 3: Run repository tests**

Run: `./venv/bin/pytest packages/backend-core/tests/app/db/pages_repository_test.py`
Expected: PASS.

- [x] **Step 4: Commit**

```bash
git add packages/backend-core/app/db/repositories/pages_repository.py packages/backend-core/tests/app/db/pages_repository_test.py
git commit -m "feat(repo): add pages repository helpers for llm spell check queries"
```

---

### Task 3: Data Integrity, Offset Invalidation, and Text Normalization (Category 2)

**Files:**
- Modify: `packages/backend-core/app/services/llm_spell_check_service.py`
- Modify: `services/backend/api/endpoints/spell_check_router.py:410-430`
- Modify: `packages/backend-core/app/services/auto_correct_service.py:130-155`
- Test: `packages/backend-core/tests/app/services/llm_spell_check_service_test.py`

**Interfaces:**
- Produces:
  - `apply_llm_page_correction(session: AsyncSession, page: Page, corrected_text: str) -> bool`
  - Safeguards in `spell_check_router.py` and `auto_correct_service.py` preventing invalid offset slicing.

- [x] **Step 1: Write unit tests for normalization and apply helper**

In `packages/backend-core/tests/app/services/llm_spell_check_service_test.py`:
- Test that `correct_page_text` applies `normalize_uyghur_chars` and `normalize_markdown` to the model output.
- Test that `apply_llm_page_correction`:
  1. Stores original text in `page.prev_text`.
  2. Updates `page.text`.
  3. Deletes `PageSpellIssue` rows for that page.
  4. Resets `page.spell_check_milestone = PAGE_MILESTONE_IDLE`.
  5. Sets `page.llm_spell_check_status = PAGE_MILESTONE_SUCCEEDED`.
  6. Sets `page.llm_spell_check_at`.

- [x] **Step 2: Implement text normalization and apply helper in `llm_spell_check_service.py`**

In `packages/backend-core/app/services/llm_spell_check_service.py`:
```python
from datetime import datetime, timezone
from sqlalchemy import delete
from app.core.pipeline import PAGE_MILESTONE_IDLE, PAGE_MILESTONE_SUCCEEDED
from app.db.models import Page, PageSpellIssue
from app.utils.text_normalization import normalize_markdown, normalize_uyghur_chars
```

Update `correct_page_text`:
```python
    corrected = await llm.ainvoke(
        prompt, config=types.GenerateContentConfig(temperature=0.0)
    )
    corrected = normalize_markdown(corrected.strip())
    corrected = normalize_uyghur_chars(corrected)
    _validate_correction(page_text, corrected)
    return corrected
```

Add `apply_llm_page_correction`:
```python
async def apply_llm_page_correction(
    session: AsyncSession,
    page: Page,
    corrected_text: str,
) -> bool:
    """Applies verified LLM correction to a page:
    - Normalizes markdown and Uyghur Unicode
    - Validates correction guardrail
    - Invalidate stale dictionary PageSpellIssue rows (offsets are invalid)
    - Resets spell_check_milestone to idle
    - Preserves pre-correction text in prev_text
    - Updates status and timestamps
    """
    cleaned = normalize_markdown(corrected_text.strip())
    cleaned = normalize_uyghur_chars(cleaned)
    _validate_correction(page.text or "", cleaned)

    text_changed = (page.text != cleaned)
    now = datetime.now(timezone.utc)

    if text_changed:
        page.prev_text = page.text
        page.text = cleaned
        # Invalidate stale dictionary spell check issues whose offsets are now wrong
        await session.execute(
            delete(PageSpellIssue).where(PageSpellIssue.page_id == page.id)
        )
        page.spell_check_milestone = PAGE_MILESTONE_IDLE

    page.llm_spell_check_status = PAGE_MILESTONE_SUCCEEDED
    page.llm_spell_check_at = now
    page.last_updated = now
    return text_changed
```

- [x] **Step 3: Add offset guards to `spell_check_router.py` and `auto_correct_service.py`**

In `services/backend/api/endpoints/spell_check_router.py`:
Before slicing at `page_text[:start] + corrected + page_text[end:]`:
```python
        # Safeguard: ensure target slice matches expected original issue word
        target_slice = page_text[start:end]
        if target_slice != issue.word:
            logger.warning(
                f"Skipping spell correction on page {page.id}: offset mismatch. "
                f"Expected '{issue.word}', found '{target_slice}' at [{start}:{end}]."
            )
            continue
```

In `packages/backend-core/app/services/auto_correct_service.py`:
Before line 144:
```python
        # Safeguard: verify that the text at offsets matches the issue word
        target_slice = page_text[start:end]
        if target_slice != issue.word:
            logger.warning(
                f"Skipping auto-correction on page {page_id}: offset mismatch. "
                f"Expected '{issue.word}', found '{target_slice}' at [{start}:{end}]."
            )
            continue
```

- [x] **Step 4: Run tests**

Run: `./venv/bin/pytest packages/backend-core/tests/app/services/llm_spell_check_service_test.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/llm_spell_check_service.py \
        packages/backend-core/tests/app/services/llm_spell_check_service_test.py \
        services/backend/api/endpoints/spell_check_router.py \
        packages/backend-core/app/services/auto_correct_service.py
git commit -m "fix(spell-check): invalidate stale offsets on llm apply, add text normalization and offset guards"
```

---

### Task 4: Worker Concurrency & Stuck Status Prevention (Category 1 & Category 3)

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py:2290-2450`
- Modify: `services/worker/jobs/llm_spell_check_job.py`
- Modify: `services/worker/scanners/stale_watchdog_scanner.py`
- Test: `services/backend/tests/api/endpoints/` and `services/worker/tests/` (or dedicated test)

**Interfaces:**
- Produces:
  - Unique `_job_id` per arq enqueue with explicit `None` handling.
  - Short-lived DB sessions in `llm_spell_check_job.py` around LLM calls.
  - Rollback on failure and `asyncio.gather(..., return_exceptions=True)`.
  - Stale watchdog resetting `llm_spell_check_status` from `in_progress` to `failed`.

- [x] **Step 1: Refactor `books_router.py` endpoints**

In `services/backend/api/endpoints/books_router.py`:
1. Use `pages_repo.list_eligible_for_llm_spell_check(book_id, force=force)` in `reprocess_llm_spell_check(book_id, force: bool = False, ...)`.
2. Generate unique job IDs:
   `job_id = f"llm_spell_check:book:{book_id}:{int(time.time())}"`
   `job_id = f"llm_spell_check:page:{page.id}:{int(time.time())}"`
3. Check `job = await redis_pool.enqueue_job(...)`:
   ```python
   job = await redis_pool.enqueue_job(...)
   if job is None:
       await pages_repo.bulk_set_llm_spell_check_status(page_ids, PAGE_MILESTONE_IDLE)
       await session.commit()
       raise HTTPException(
           status_code=409,
           detail=t("errors.llm_spell_check_enqueue_dropped"),
       )
   ```
4. Replace raw `session.execute(update(Page))` calls with `pages_repo.bulk_set_llm_spell_check_status`.
5. In `trigger_llm_spell_check_page`, validate:
   ```python
   if not page.text or not page.text.strip():
       raise HTTPException(status_code=400, detail=t("errors.page_text_empty"))
   ```

- [x] **Step 2: Refactor `llm_spell_check_job.py`**

In `services/worker/jobs/llm_spell_check_job.py`:
1. Split session into:
   - Read page & neighbors, then close session.
   - Run `correct_page_text` without active DB connection.
   - Open fresh session to run `apply_llm_page_correction` and commit.
2. In `except Exception as exc:`:
   `await session.rollback()` before marking `PAGE_MILESTONE_FAILED` and committing.
3. In `asyncio.gather`:
   `await asyncio.gather(*(process_page(pid) for pid in page_ids), return_exceptions=True)`

- [x] **Step 3: Update `stale_watchdog_scanner.py` to reset stuck LLM spell check pages**

In `services/worker/scanners/stale_watchdog_scanner.py`:
Add `Page.llm_spell_check_status == "in_progress"` to the stale check or as a distinct check:
If `Page.llm_spell_check_status == "in_progress"` and `Page.last_updated < max_duration_threshold`:
Reset `llm_spell_check_status = "failed"`, `last_updated = now`.

- [x] **Step 4: Run test suite**

Run: `./venv/bin/pytest packages/backend-core/tests/app/services/llm_spell_check_service_test.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add services/backend/api/endpoints/books_router.py \
        services/worker/jobs/llm_spell_check_job.py \
        services/worker/scanners/stale_watchdog_scanner.py
git commit -m "fix(worker): prevent stuck in_progress pages, release db connections during llm calls, add watchdog recovery"
```

---

### Task 5: Gemini Batch API Hardening & Poller Scanner (Category 4)

**Files:**
- Modify: `services/worker/scanners/batch_llm_spell_check_poller_scanner.py`
- Modify: `packages/backend-core/app/services/batch_llm_spell_check_service.py`
- Test: `packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py`

**Interfaces:**
- Produces:
  - Unconditional polling in `batch_llm_spell_check_poller_scanner.py`.
  - Non-blocking async wrappers around `genai.Client` calls.
  - Stored submitted-text fingerprint on `BatchLlmSpellCheckJob` to skip overwritten pages.
  - `job.status = "failed"` if result download fails.
  - Standardized structured logging via `log_json`.

- [x] **Step 1: Write tests for batch failure handling and non-blocking calls**

In `packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py`:
- Test that `poll_and_process_batch_llm_spell_check_jobs` sets `job.status = "failed"` if `result_bytes` cannot be retrieved.
- Test that batch ingestion uses `apply_llm_page_correction` to clear `PageSpellIssue` rows.
- Test that pages edited after batch submission are skipped with a warning rather than overwritten.

- [x] **Step 2: Update `batch_llm_spell_check_poller_scanner.py`**

Remove feature flag early return:
```python
async def run_batch_llm_spell_check_poller_scanner(ctx) -> None:
    log_json(logger, logging.INFO, "Batch LLM Spell Check poller scanner started")
    try:
        async with db_session.async_session_factory() as session:
            processed = await poll_and_process_batch_llm_spell_check_jobs(session)

        if processed:
            log_json(
                logger,
                logging.INFO,
                "Batch LLM Spell Check poller scanner completed",
                jobs_processed=processed,
            )
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "Error running Batch LLM Spell Check poller scanner",
            error=str(exc),
        )
```

- [x] **Step 3: Update `batch_llm_spell_check_service.py`**

1. Wrap sync SDK calls:
   `uploaded_file = await asyncio.to_thread(client.files.upload, ...)`
   `batch_job = await asyncio.to_thread(client.batches.create, ...)`
   `batch_info = await asyncio.to_thread(client.batches.get, name=job.gemini_batch_id)`
   `result_bytes = await asyncio.to_thread(client.files.download, file=output_file_name)`
2. Store `submitted_at` per batch, and before applying text:
   Check `if page.last_updated and page.last_updated > job.submitted_at: logger.warning("skipping page: edited since batch submission")`.
3. Ingestion apply uses `apply_llm_page_correction(session, page, text)`.
4. If download fails (`result_bytes is None`):
   Set `job.status = "failed"`, `job.error = "Failed to download batch results"`, mark pages failed, and log via `log_json`.
5. Replace direct repository queries with `PagesRepository` methods.
6. Replace raw `logger.warning`/`logger.error` with `log_json`.

- [x] **Step 4: Run batch service tests**

Run: `./venv/bin/pytest packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add services/worker/scanners/batch_llm_spell_check_poller_scanner.py \
        packages/backend-core/app/services/batch_llm_spell_check_service.py \
        packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py
git commit -m "fix(batch): make poller unconditional, non-blocking genai calls, and handle download failures"
```

---

### Task 6: End-to-End Verification & Documentation Update

**Files:**
- Test: Full backend-core and worker test suites
- Modify: `docs/feature/llm-spell-correction-v2/code-review-api-2026-10-14.md` (or verification summary)

- [x] **Step 1: Run complete test suite**

Run: `./venv/bin/pytest packages/backend-core/tests/`
Expected: All tests pass.

- [x] **Step 2: Verify local docker-compose rebuild if containers are running**

Run: `./deploy/local/rebuild-and-restart.sh worker` (if running locally).

- [x] **Step 3: Commit final plan resolution documentation**

```bash
git commit -m "docs: complete verification and resolution of code-review-api-2026-10-14"
```
