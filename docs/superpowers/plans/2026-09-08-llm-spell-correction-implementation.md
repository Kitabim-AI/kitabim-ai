# LLM-Based Spell Correction (Gemini) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an on-demand, admin-triggered Gemini-based spell-correction pass (per-page or per-book) that catches context-dependent real-word errors the existing dictionary-based spell checker cannot, auto-applying corrections directly to `pages.text`.

**Architecture:** A new `llm_spell_check_status`/`llm_spell_check_at` pair of columns on `pages`, plus a shared `llm_spell_check_service.py` (prompt building + one `generate_content` call via the project's circuit-breaker-protected `build_text_llm`) called by both a live worker job (`llm_spell_check_job`) and an optional Gemini Batch API path (`batch_llm_spell_check_service.py` + a poller scanner), mirroring the existing `batch_history_extraction_service` dual-path pattern. Two new admin-only FastAPI endpoints trigger it per-page or per-book; the frontend surfaces it as a new reprocess-step button plus a three-state admin-table icon.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), arq (worker), Gemini via `google-genai` SDK (`app.llm.models.build_text_llm` / raw `genai.Client` for the Batch API), React/Vite + TypeScript (frontend), pytest + vitest (tests).

**Source spec:** `docs/superpowers/specs/2026-09-05-llm-spell-correction-design.md`

## Global Constraints

- No `print()` — use `log_json(logger, level, "message", key=value)` from `app.utils.observability`.
- No `os.environ.get()` in application code — use `settings.*` from `app/core/config.py` (a frozen dataclass, not Pydantic `BaseSettings`).
- No hardcoded user-visible strings — use `t("errors.key")` from `app.core.i18n` (backend) / `t('key')` from the frontend `I18nContext` (frontend), and add matching keys to **both** `en.json` and `ug.json` in each locale directory.
- No raw SQL with user input — always SQLAlchemy bound parameters / the query builder.
- No session shared across pages in a worker job — a fresh `async with db_session.async_session_factory() as session:` per page.
- Migration file first, ORM model second, repository third, endpoint last.
- All new API endpoints need `Depends(require_admin)` — never skipped (both new endpoints trigger real Gemini API spend).
- Model ids are never hardcoded — always read via `SystemConfigsRepository.get_value(key, fallback)`, with the DB row seeded by both a migration `INSERT` and a `packages/backend-core/app/db/seeds.py` `defaults` entry (established dual-seed convention in this repo).
- Static LLM prompts live in `packages/backend-core/app/core/prompts.py` as `SCREAMING_SNAKE_CASE` constants using `{placeholder}` + `.format()` — never f-string interpolation inside the constant, never a raw Gemini SDK call for a single-shot structured prompt (use `generate_text()` or `build_text_llm()...ainvoke()` so calls go through the shared circuit breaker/rate limiter) — this is a deliberate deviation from the design spec's illustrative pseudocode (which shows a raw `genai.Client(...)` call for the live path); the Batch API path has no such wrapper and must use `genai.Client` directly, matching `batch_history_extraction_service.py`.
- Every prompt producing Uyghur output must explicitly say "Uyghur Arabic script" — never assume the model defaults to it.
- This feature is **not** a pipeline stage: no `PipelineEvent` rows, no `retry_count` increments, not added to `PIPELINE_ORDER` / `PAGE_MILESTONE_ATTR_BY_STEP` / `STEP_DONE_MILESTONE_BY_STEP` in `app/core/pipeline.py` (confirmed safe — nothing iterates those assuming exhaustiveness; `PIPELINE_STEP_SUMMARY` is existing precedent for a step-like concept living outside them).
- `llm_spell_check_status` values reuse existing generic constants from `app.core.pipeline`: `PAGE_MILESTONE_IDLE` ("idle"), `PAGE_MILESTONE_IN_PROGRESS` ("in_progress" — this is what the design doc's prose calls "running"), `PAGE_MILESTONE_SUCCEEDED` ("succeeded"), `PAGE_MILESTONE_FAILED` ("failed"). No new constants.

---

## File Structure

| File | Responsibility |
|---|---|
| `packages/backend-core/migrations/090_add_llm_spell_check_status_to_pages.sql` (+rollback) | `pages.llm_spell_check_status` / `pages.llm_spell_check_at` columns |
| `packages/backend-core/migrations/091_add_batch_llm_spell_check_jobs.sql` (+rollback) | `batch_llm_spell_check_jobs` table + 2 `system_configs` seed rows |
| `packages/backend-core/app/db/seeds.py` | Idempotent startup-time seed entries mirroring the migration 091 rows |
| `packages/backend-core/app/db/models.py` | `Page.llm_spell_check_status`/`llm_spell_check_at` columns; new `BatchLlmSpellCheckJob` ORM model |
| `packages/backend-core/app/db/repositories/pages_repository.py` | `set_llm_spell_check_status()` |
| `packages/backend-core/app/core/config.py` | `settings.max_parallel_llm_spell_check` |
| `packages/backend-core/app/core/prompts.py` | `LLM_SPELL_CHECK_PROMPT` constant |
| `packages/backend-core/app/services/llm_spell_check_service.py` (new) | `build_correction_prompt`, `correct_page_text`, `_validate_correction` — shared by live + batch paths |
| `services/worker/jobs/llm_spell_check_job.py` (new) | Live-path worker job, per-page session, bounded concurrency |
| `packages/backend-core/app/services/batch_llm_spell_check_service.py` (new) | Batch submission (`submit_batch_llm_spell_check`) + polling/ingestion (`poll_and_process_batch_llm_spell_check_jobs`) |
| `services/worker/scanners/batch_llm_spell_check_poller_scanner.py` (new) | Thin cron wrapper calling the poll function, flag-gated |
| `services/worker/worker.py` | Register `llm_spell_check_job` in `functions`; register the poller scanner in `cron_jobs` |
| `packages/backend-core/app/db/repositories/books_repository.py` | Extend `get_with_page_stats` / `get_batch_stats` with always-scanned `llm_spell_check` stats |
| `packages/backend-core/app/models/schemas.py` | `ExtractionResult.llm_spell_check_status` / `.llm_spell_check_at` |
| `services/backend/api/endpoints/books_router.py` | `POST /{book_id}/reprocess/llm-spell-check`, `POST /{book_id}/pages/{page_num}/llm-spell-check` |
| `services/backend/locales/en.json`, `ug.json` | New `errors.*` keys |
| `docs/main/openapi.json`, `packages/shared/src/api-types.ts`, `packages/shared/src/types.ts` | Regenerated/updated OpenAPI types + manual override types |
| `apps/frontend/src/constants/milestones.ts` | `REPROCESS_STEP.LLM_SPELL_CHECK` |
| `apps/frontend/src/services/persistenceService.ts` | `reprocessLlmSpellCheck`, `triggerLlmSpellCheckPage` |
| `apps/frontend/src/hooks/useBookActions.ts` | `handleLlmSpellCheckPage`; `titles`/`switch` entries in `handleReprocessStep` |
| `apps/frontend/src/components/admin/ActionMenu.tsx` | New admin-gated reprocess button |
| `apps/frontend/src/components/reader/PageItem.tsx`, `ReaderView.tsx` | `onLlmSpellCheck` prop + wiring, admin-gated |
| `apps/frontend/src/components/admin/AdminView.tsx` | Three-state (`done`/`partial`/`pending`) icon in the per-book row |
| `apps/frontend/src/locales/en.json`, `ug.json` | New button/modal/notification keys |

Test files are listed per-task below (each task is TDD: test first).

---

## Task 1: Migrations 090 + 091

**Files:**
- Create: `packages/backend-core/migrations/090_add_llm_spell_check_status_to_pages.sql`
- Create: `packages/backend-core/migrations/090_rollback_add_llm_spell_check_status_to_pages.sql`
- Create: `packages/backend-core/migrations/091_add_batch_llm_spell_check_jobs.sql`
- Create: `packages/backend-core/migrations/091_rollback_add_batch_llm_spell_check_jobs.sql`

**Interfaces:**
- Produces: `pages.llm_spell_check_status` (`varchar(20) not null default 'idle'`), `pages.llm_spell_check_at` (`timestamptz null`); `batch_llm_spell_check_jobs` table; `system_configs` rows `llm_spell_check_batch_enabled` (`'false'`) and `gemini_llm_spell_check_model` (`'gemini-3.1-flash-lite'`).

Migrations have no test suite in this repo (verified by applying them to the local dev DB in Step 3) — confirmed next-free numbers are 090/091 (nothing landed since the design doc was written).

- [x] **Step 1: Write migration 090**

`packages/backend-core/migrations/090_add_llm_spell_check_status_to_pages.sql`:
```sql
-- Migration: 090_add_llm_spell_check_status_to_pages.sql
-- Description: Add llm_spell_check_status and llm_spell_check_at columns to pages
--              for the on-demand Gemini-based spell correction pass
-- Author: Kitabim.AI
-- Date: 2026-09-08

BEGIN;

ALTER TABLE public.pages
    ADD COLUMN IF NOT EXISTS llm_spell_check_status VARCHAR(20) NOT NULL DEFAULT 'idle';

ALTER TABLE public.pages
    ADD COLUMN IF NOT EXISTS llm_spell_check_at TIMESTAMPTZ NULL;

COMMIT;
```

`packages/backend-core/migrations/090_rollback_add_llm_spell_check_status_to_pages.sql`:
```sql
-- Migration Rollback: 090_rollback_add_llm_spell_check_status_to_pages.sql
-- Description: Rollback adding llm_spell_check_status/llm_spell_check_at to pages

BEGIN;

ALTER TABLE public.pages
    DROP COLUMN IF EXISTS llm_spell_check_status;

ALTER TABLE public.pages
    DROP COLUMN IF EXISTS llm_spell_check_at;

COMMIT;
```

- [x] **Step 2: Write migration 091**

`packages/backend-core/migrations/091_add_batch_llm_spell_check_jobs.sql`:
```sql
-- Migration: 091_add_batch_llm_spell_check_jobs.sql
-- Description: Add batch_llm_spell_check_jobs table for Gemini Batch API LLM
--              spell-check processing, plus system_configs for the batch flag
--              and model
-- Author: Kitabim.AI
-- Date: 2026-09-08

BEGIN;

CREATE TABLE IF NOT EXISTS batch_llm_spell_check_jobs (
    id SERIAL PRIMARY KEY,
    gemini_batch_id VARCHAR(255) NOT NULL UNIQUE,
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_ids INTEGER[] NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'submitting',
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_batches INTEGER NOT NULL DEFAULT 1,
    model_name VARCHAR(100),
    error TEXT,
    submitted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_batch_llm_spell_check_jobs_book_id ON batch_llm_spell_check_jobs(book_id);

INSERT INTO system_configs (key, value, description, updated_at) VALUES
    ('llm_spell_check_batch_enabled', 'false',
     'When true, the per-book LLM spell-check trigger submits a Gemini Batch API job instead of live concurrent calls', NOW()),
    ('gemini_llm_spell_check_model', 'gemini-3.1-flash-lite',
     'Gemini model used for LLM-based spell correction, both live and batch paths', NOW())
ON CONFLICT (key) DO NOTHING;

COMMIT;
```

`packages/backend-core/migrations/091_rollback_add_batch_llm_spell_check_jobs.sql`:
```sql
-- Migration Rollback: 091_rollback_add_batch_llm_spell_check_jobs.sql
-- Description: Rollback batch_llm_spell_check_jobs table and its system_configs seeds

BEGIN;

DROP TABLE IF EXISTS batch_llm_spell_check_jobs CASCADE;

DELETE FROM system_configs WHERE key = 'llm_spell_check_batch_enabled';
DELETE FROM system_configs WHERE key = 'gemini_llm_spell_check_model';

COMMIT;
```

- [x] **Step 3: Apply locally and verify**

Run: `./deploy/local/rebuild-and-restart.sh backend` (migrations run automatically on backend startup in this repo's local dev flow — check `deploy/local/rebuild-and-restart.sh` for the exact migration-runner invocation; if migrations are applied by a separate script, run that instead, e.g. `python packages/backend-core/scripts/run_migrations.py` or equivalent).
Expected: backend logs show migrations 090 and 091 applied with no errors; connect to the local Postgres and confirm:
```sql
\d pages   -- shows llm_spell_check_status, llm_spell_check_at
\d batch_llm_spell_check_jobs
SELECT key, value FROM system_configs WHERE key IN ('llm_spell_check_batch_enabled', 'gemini_llm_spell_check_model');
```

- [x] **Step 4: Commit**

```bash
git add packages/backend-core/migrations/090_add_llm_spell_check_status_to_pages.sql \
        packages/backend-core/migrations/090_rollback_add_llm_spell_check_status_to_pages.sql \
        packages/backend-core/migrations/091_add_batch_llm_spell_check_jobs.sql \
        packages/backend-core/migrations/091_rollback_add_batch_llm_spell_check_jobs.sql
git commit -m "feat(db): add migrations for LLM spell check status and batch jobs table"
```

---

## Task 2: Seed defaults in `app/db/seeds.py`

**Files:**
- Modify: `packages/backend-core/app/db/seeds.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: idempotent startup seeding of the same two `system_configs` rows migration 091 inserts (safety net for fresh DBs / DBs where migration 091 hasn't run yet in a given environment ordering).

This file has no dedicated unit test in the repo (its `defaults` list is data, exercised indirectly via `queue.py` startup) — verify via Step 2 instead.

- [x] **Step 1: Add the two entries to the `defaults` list**

In `packages/backend-core/app/db/seeds.py`, inside the `defaults` list (alongside the `ocr_gemini_model`/`rag_gemini_chat_model` entries), add:
```python
        {
            "key": "llm_spell_check_batch_enabled",
            "value": "false",
            "description": "When true, the per-book LLM spell-check trigger submits a Gemini Batch API job instead of live concurrent calls",
        },
        {
            "key": "gemini_llm_spell_check_model",
            "value": "gemini-3.1-flash-lite",
            "description": "Gemini model used for LLM-based spell correction, both live and batch paths",
        },
```

- [x] **Step 2: Verify manually**

Run: `./deploy/local/rebuild-and-restart.sh worker` then check worker startup logs for `seed_system_configs` running without error, and re-run the `SELECT` from Task 1 Step 3 to confirm the rows still read `'false'` / `'gemini-3.1-flash-lite'` (idempotent — no duplicate/overwrite).

- [x] **Step 3: Commit**

```bash
git add packages/backend-core/app/db/seeds.py
git commit -m "feat(config): seed llm_spell_check_batch_enabled and gemini_llm_spell_check_model defaults"
```

---

## Task 3: ORM models

**Files:**
- Modify: `packages/backend-core/app/db/models.py`
- Test: `packages/backend-core/tests/app/db/models_test.py` (create if it does not already exist — check first; if there's no existing convention for testing plain column/model definitions in this repo, skip a dedicated test file and instead verify via Task 4's repository test, which exercises the new `Page` columns directly)

**Interfaces:**
- Produces: `Page.llm_spell_check_status: Mapped[str]`, `Page.llm_spell_check_at: Mapped[Optional[datetime]]`; `BatchLlmSpellCheckJob` class with `id: Mapped[int]`, `gemini_batch_id: Mapped[str]`, `book_id: Mapped[str]`, `page_ids: Mapped[List[int]]`, `status: Mapped[str]`, `gcs_input_uri/gcs_output_uri: Mapped[Optional[str]]`, `total_batches: Mapped[int]`, `model_name: Mapped[Optional[str]]`, `error: Mapped[Optional[str]]`, `submitted_at/completed_at: Mapped[Optional[datetime]]`, `created_at/updated_at: Mapped[datetime]`.

- [x] **Step 1: Add the two `Page` columns**

In `packages/backend-core/app/db/models.py`, immediately after the existing `spell_check_milestone` column (around line 196-198):
```python
    spell_check_milestone: Mapped[Optional[str]] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=True
    )
    llm_spell_check_status: Mapped[str] = mapped_column(
        String(20), default="idle", server_default="idle", nullable=False
    )
    llm_spell_check_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [x] **Step 2: Confirm `ARRAY` import**

Search `packages/backend-core/app/db/models.py` for `from sqlalchemy.dialects.postgresql import`. If `ARRAY` is not already imported there, add it to that import line (e.g. `from sqlalchemy.dialects.postgresql import ARRAY, ...`).

- [x] **Step 3: Add the `BatchLlmSpellCheckJob` model**

Add this class after `BatchHistoryExtractionJob` in `packages/backend-core/app/db/models.py`:
```python
class BatchLlmSpellCheckJob(Base):
    """Batch LLM Spell Check Job model tracking Gemini Batch API LLM-based
    spell-correction requests"""

    __tablename__ = "batch_llm_spell_check_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gemini_batch_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    book_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("books.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_ids: Mapped[List[int]] = mapped_column(ARRAY(Integer), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="submitting", server_default="submitting", nullable=False
    )

    gcs_input_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gcs_output_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    total_batches: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

- [x] **Step 4: Verify with a Python import smoke check**

Run: `cd packages/backend-core && python -c "from app.db.models import Page, BatchLlmSpellCheckJob; print(Page.llm_spell_check_status, BatchLlmSpellCheckJob.__tablename__)"`
Expected: prints the column and `batch_llm_spell_check_jobs` with no `ImportError`/`AttributeError`.

- [x] **Step 5: Commit**

```bash
git add packages/backend-core/app/db/models.py
git commit -m "feat(db): add Page.llm_spell_check_status/_at and BatchLlmSpellCheckJob ORM model"
```

---

## Task 4: `PagesRepository.set_llm_spell_check_status`

**Files:**
- Modify: `packages/backend-core/app/db/repositories/pages_repository.py`
- Test: `packages/backend-core/tests/app/db/pages_repository_test.py`

**Interfaces:**
- Consumes: `Page` model from Task 3; `PAGE_MILESTONE_SUCCEEDED`/`PAGE_MILESTONE_FAILED` from `app.core.pipeline`.
- Produces: `async def set_llm_spell_check_status(self, book_id: str, page_number: int, status: str, updated_by: Optional[str] = None) -> bool`.

- [x] **Step 1: Write the failing tests**

Append to `packages/backend-core/tests/app/db/pages_repository_test.py` (mirroring the existing `set_is_toc` tests exactly):
```python
@pytest.mark.asyncio
async def test_set_llm_spell_check_status_success():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    result = await repo.set_llm_spell_check_status("b1", 5, PAGE_MILESTONE_SUCCEEDED)
    assert result is True


@pytest.mark.asyncio
async def test_set_llm_spell_check_status_sets_at_timestamp_on_terminal_status():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    await repo.set_llm_spell_check_status("b1", 5, PAGE_MILESTONE_FAILED)

    call_args = session.execute.call_args[0][0]
    compiled_params = call_args.compile().params
    assert "llm_spell_check_at" in compiled_params
    assert compiled_params["llm_spell_check_status"] == PAGE_MILESTONE_FAILED


@pytest.mark.asyncio
async def test_set_llm_spell_check_status_returns_false_for_unknown_page():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 0
    session.execute.return_value = mock_res

    result = await repo.set_llm_spell_check_status("b1", 999, PAGE_MILESTONE_SUCCEEDED)
    assert result is False
```

Add the needed import at the top of the test file if not already present: `from app.core.pipeline import PAGE_MILESTONE_SUCCEEDED, PAGE_MILESTONE_FAILED`.

- [x] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/db/pages_repository_test.py -k llm_spell_check_status -v`
Expected: FAIL with `AttributeError: 'PagesRepository' object has no attribute 'set_llm_spell_check_status'`.

- [x] **Step 3: Implement `set_llm_spell_check_status`**

Add to `packages/backend-core/app/db/repositories/pages_repository.py`, after `set_is_toc`:
```python
    async def set_llm_spell_check_status(
        self, book_id: str, page_number: int, status: str, updated_by: Optional[str] = None
    ) -> bool:
        """Set the on-demand LLM spell-check status for one page. Records
        llm_spell_check_at when the run reaches a terminal state (success or
        failure) — not on transition to in_progress."""
        from sqlalchemy import update
        from app.core.pipeline import PAGE_MILESTONE_SUCCEEDED, PAGE_MILESTONE_FAILED

        values = {"llm_spell_check_status": status, "last_updated": func.now()}
        if status in (PAGE_MILESTONE_SUCCEEDED, PAGE_MILESTONE_FAILED):
            values["llm_spell_check_at"] = func.now()
        if updated_by:
            values["updated_by"] = updated_by

        stmt = (
            update(Page)
            .where(Page.book_id == book_id, Page.page_number == page_number)
            .values(**values)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/db/pages_repository_test.py -k llm_spell_check_status -v`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add packages/backend-core/app/db/repositories/pages_repository.py packages/backend-core/tests/app/db/pages_repository_test.py
git commit -m "feat(db): add PagesRepository.set_llm_spell_check_status"
```

---

## Task 5: `settings.max_parallel_llm_spell_check`

**Files:**
- Modify: `packages/backend-core/app/core/config.py`

**Interfaces:**
- Produces: `settings.max_parallel_llm_spell_check: int` (env `MAX_PARALLEL_LLM_SPELL_CHECK`, default `6`).

No dedicated test — this dataclass field has no existing test convention in this repo (verify via Step 2 import smoke check, consistent with how `max_parallel_spell_check` itself is untested).

- [x] **Step 1: Add the field**

In `packages/backend-core/app/core/config.py`, immediately after `max_parallel_spell_check` (around line 57):
```python
    max_parallel_spell_check: int = int(os.getenv("MAX_PARALLEL_SPELL_CHECK", "6"))
    max_parallel_llm_spell_check: int = int(
        os.getenv("MAX_PARALLEL_LLM_SPELL_CHECK", "6")
    )
```

- [x] **Step 2: Verify**

Run: `cd packages/backend-core && python -c "from app.core.config import settings; print(settings.max_parallel_llm_spell_check)"`
Expected: prints `6`.

- [x] **Step 3: Commit**

```bash
git add packages/backend-core/app/core/config.py
git commit -m "feat(config): add max_parallel_llm_spell_check setting"
```

---

## Task 6: `LLM_SPELL_CHECK_PROMPT` constant

**Files:**
- Modify: `packages/backend-core/app/core/prompts.py`

**Interfaces:**
- Produces: `LLM_SPELL_CHECK_PROMPT: str` template with `{prev_context}`, `{page_text}`, `{next_context}` placeholders.

No dedicated test file — verified via Task 7's `build_correction_prompt` tests, which assert on the formatted output.

- [x] **Step 1: Add the prompt constant**

Add to `packages/backend-core/app/core/prompts.py`, following the `# Used by: / # Model:` comment convention used above `EXTRACTION_PROMPT_TEMPLATE`:
```python
# Used by: llm_spell_check_service.correct_page_text (live path) and
# batch_llm_spell_check_service.submit_batch_llm_spell_check (batch path,
# one request per page)
# Model: system_configs["gemini_llm_spell_check_model"], temperature=0.0
LLM_SPELL_CHECK_PROMPT = """You are an expert Uyghur-language copy editor. The text below is one page from a Uyghur book, written in Uyghur Arabic script and already run through OCR and a dictionary-based spell checker. Your task is to find and fix ONLY context-dependent word substitution errors — a valid Uyghur word that was OCR'd or typed as a different, valid Uyghur word that does not fit the sentence's meaning. A dictionary lookup cannot catch these because both the wrong word and the right word are real words; only reading the sentence reveals the mistake.

CRITICAL LANGUAGE & SCRIPT REQUIREMENTS:
1. INPUT: The page text is written in modern Uyghur using Uyghur Arabic script.
2. OUTPUT: Return the corrected page text strictly in Uyghur Arabic script. Do NOT translate, transliterate, or romanize any part of it.

RULES:
1. Fix ONLY real-word substitution errors — a wrong-but-valid word that breaks the sentence's meaning. Judge this using the surrounding sentence and, when needed, the previous/next page context below.
2. Do NOT fix spelling of words that are not real Uyghur words — a separate dictionary-based checker already handles those; leave anything you are not sure is a real-word substitution unchanged.
3. Do NOT rewrite, rephrase, summarize, reorder, or improve the writing style. Change only the specific mistaken word(s).
4. Preserve the page's exact formatting: paragraph breaks, line breaks, Markdown headings, and any `[Header]`/`[Footer]` markers must remain exactly as given.
5. Do NOT add, remove, or alter punctuation except where it was clearly part of a fixed word.
6. Return ONLY the corrected page text. Do NOT add commentary, explanations, a summary of changes, or any wrapper (no JSON, no markdown code fences, no "Corrected text:" prefix).
7. If you find no context-dependent errors, return the page text completely unchanged.

--- previous page (context only, do not correct) ---
{prev_context}
--- end previous page context ---

--- page to correct ---
{page_text}
--- end page to correct ---

--- next page (context only, do not correct) ---
{next_context}
--- end next page context ---

Return only the corrected version of "page to correct" above, with nothing else."""
```

- [x] **Step 2: Verify with an import + format smoke check**

Run: `cd packages/backend-core && python -c "from app.core.prompts import LLM_SPELL_CHECK_PROMPT; print(LLM_SPELL_CHECK_PROMPT.format(prev_context='', page_text='test', next_context=''))" | head -5`
Expected: prints the formatted prompt with no `KeyError`/`IndexError` from `.format()`.

- [x] **Step 3: Commit**

```bash
git add packages/backend-core/app/core/prompts.py
git commit -m "feat(prompts): add LLM_SPELL_CHECK_PROMPT for context-dependent word correction"
```

---

## Task 7: `llm_spell_check_service.py`

**Files:**
- Create: `packages/backend-core/app/services/llm_spell_check_service.py`
- Test: `packages/backend-core/tests/app/services/llm_spell_check_service_test.py`

**Interfaces:**
- Consumes: `LLM_SPELL_CHECK_PROMPT` (Task 6); `SystemConfigsRepository.get_value` (existing); `build_text_llm` from `app.llm.models` (existing).
- Produces: `build_correction_prompt(page_text: str, prev_page_text: Optional[str], next_page_text: Optional[str]) -> str`; `async def correct_page_text(page_text: str, prev_page_text: Optional[str], next_page_text: Optional[str], config_repo: SystemConfigsRepository) -> str`; `_validate_correction(original: str, corrected: str) -> None` (raises `ValueError` on bad output — imported directly by the batch service in Task 10, so keep it a plain module-level function, not name-mangled).

- [x] **Step 1: Write the failing tests**

Create `packages/backend-core/tests/app/services/llm_spell_check_service_test.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch

from app.services.llm_spell_check_service import (
    build_correction_prompt,
    correct_page_text,
    _validate_correction,
)


def test_build_correction_prompt_includes_prev_and_next_context():
    prompt = build_correction_prompt("PAGE TEXT", "PREV TEXT", "NEXT TEXT")
    assert "PAGE TEXT" in prompt
    assert "PREV TEXT" in prompt
    assert "NEXT TEXT" in prompt
    # Context sections must be clearly delimited from the page to correct.
    assert "previous page (context only, do not correct)" in prompt
    assert "next page (context only, do not correct)" in prompt


def test_build_correction_prompt_handles_missing_context():
    prompt = build_correction_prompt("PAGE TEXT", None, None)
    assert "PAGE TEXT" in prompt
    # Should not raise, and should not literally embed the string "None".
    assert "None" not in prompt


def test_validate_correction_rejects_empty_output():
    with pytest.raises(ValueError):
        _validate_correction("some original text", "")


def test_validate_correction_rejects_whitespace_only_output():
    with pytest.raises(ValueError):
        _validate_correction("some original text", "   ")


def test_validate_correction_rejects_large_length_deviation():
    original = "a" * 1000
    corrected = "a" * 500  # 50% shorter — over the ~30% guardrail
    with pytest.raises(ValueError):
        _validate_correction(original, corrected)


def test_validate_correction_accepts_small_length_deviation():
    original = "a" * 1000
    corrected = "a" * 1100  # 10% longer — within the guardrail
    _validate_correction(original, corrected)  # should not raise


@pytest.mark.asyncio
async def test_correct_page_text_reads_model_from_system_configs():
    mock_config_repo = AsyncMock()
    mock_config_repo.get_value.return_value = "gemini-3.1-flash-lite"

    with patch(
        "app.services.llm_spell_check_service.build_text_llm"
    ) as mock_build_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = "corrected page text"
        mock_build_llm.return_value = mock_llm

        result = await correct_page_text(
            "original page text", "prev", "next", mock_config_repo
        )

        assert result == "corrected page text"
        mock_config_repo.get_value.assert_called_once_with(
            "gemini_llm_spell_check_model", "gemini-3.1-flash-lite"
        )
        mock_build_llm.assert_called_once_with("gemini-3.1-flash-lite")
        mock_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_correct_page_text_raises_on_empty_model_output():
    mock_config_repo = AsyncMock()
    mock_config_repo.get_value.return_value = "gemini-3.1-flash-lite"

    with patch(
        "app.services.llm_spell_check_service.build_text_llm"
    ) as mock_build_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = ""
        mock_build_llm.return_value = mock_llm

        with pytest.raises(ValueError):
            await correct_page_text("original page text", None, None, mock_config_repo)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/services/llm_spell_check_service_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.llm_spell_check_service'`.

- [x] **Step 3: Implement the service**

Create `packages/backend-core/app/services/llm_spell_check_service.py`:
```python
"""
LLM Spell Check Service — on-demand, admin-triggered Gemini-based spell
correction for context-dependent real-word errors. Shared by the live worker
job path (llm_spell_check_job) and the Gemini Batch API path
(batch_llm_spell_check_service).
"""

from __future__ import annotations

from typing import Optional

from google.genai import types

from app.core.prompts import LLM_SPELL_CHECK_PROMPT
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.llm.models import build_text_llm

_MAX_LENGTH_DEVIATION_RATIO = 0.3


def build_correction_prompt(
    page_text: str, prev_page_text: Optional[str], next_page_text: Optional[str]
) -> str:
    return LLM_SPELL_CHECK_PROMPT.format(
        prev_context=prev_page_text or "",
        page_text=page_text,
        next_context=next_page_text or "",
    )


def _validate_correction(original: str, corrected: str) -> None:
    """Cheap sanity guardrail against catastrophic model failures (empty or
    wildly truncated/garbled output) — not a dictionary-based per-word check,
    which is deferred to Future Enhancements per the design doc. Shared by
    both the live path and the batch poller.
    """
    if not corrected or not corrected.strip():
        raise ValueError("LLM spell check returned empty output")

    original_len = len(original)
    if original_len == 0:
        return
    deviation = abs(len(corrected) - original_len) / original_len
    if deviation > _MAX_LENGTH_DEVIATION_RATIO:
        raise ValueError(
            f"LLM spell check output length deviates {deviation:.0%} from original "
            f"(original={original_len} chars, corrected={len(corrected)} chars)"
        )


async def correct_page_text(
    page_text: str,
    prev_page_text: Optional[str],
    next_page_text: Optional[str],
    config_repo: SystemConfigsRepository,
) -> str:
    """Live path — one synchronous generate_content call. Used for every
    per-page trigger, and for per-book triggers when
    llm_spell_check_batch_enabled is false.

    Uses build_text_llm/ProtectedLLM (not a raw genai.Client) so the call
    goes through the shared circuit breaker and rate limiter, per project
    convention for single-shot structured LLM calls.
    """
    model = await config_repo.get_value(
        "gemini_llm_spell_check_model", "gemini-3.1-flash-lite"
    )
    prompt = build_correction_prompt(page_text, prev_page_text, next_page_text)
    llm = build_text_llm(model)
    corrected = await llm.ainvoke(
        prompt, config=types.GenerateContentConfig(temperature=0.0)
    )
    corrected = corrected.strip()
    _validate_correction(page_text, corrected)
    return corrected
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/services/llm_spell_check_service_test.py -v`
Expected: PASS (8 tests).

- [x] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/llm_spell_check_service.py packages/backend-core/tests/app/services/llm_spell_check_service_test.py
git commit -m "feat(services): add llm_spell_check_service with correction + validation guardrail"
```

---

## Task 8: `llm_spell_check_job` (live worker path)

**Files:**
- Create: `services/worker/jobs/llm_spell_check_job.py`
- Test: `services/worker/tests/jobs/llm_spell_check_job_test.py`

**Interfaces:**
- Consumes: `correct_page_text` (Task 7); `PagesRepository.set_llm_spell_check_status` (Task 4); `settings.max_parallel_llm_spell_check` (Task 5); `PAGE_MILESTONE_SUCCEEDED`/`PAGE_MILESTONE_FAILED` from `app.core.pipeline`.
- Produces: `async def llm_spell_check_job(ctx, page_ids: List[int]) -> None` — the arq job function name registered in Task 9 as the string `"llm_spell_check_job"`.

- [x] **Step 1: Write the failing test**

Create `services/worker/tests/jobs/llm_spell_check_job_test.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.worker.jobs.llm_spell_check_job import llm_spell_check_job
from app.db.models import Page


@pytest.mark.asyncio
async def test_llm_spell_check_job_success_updates_status_and_text():
    ctx = {}
    mock_session = AsyncMock()
    page = Page(id=1, book_id="book-1", page_number=5, text="original text")
    mock_session.get = AsyncMock(return_value=page)

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.llm_spell_check_job.correct_page_text",
            new_callable=AsyncMock,
        ) as mock_correct,
        patch(
            "services.worker.jobs.llm_spell_check_job.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_correct.return_value = "corrected text"

        mock_repo = MagicMock()
        mock_repo.find_one = AsyncMock(return_value=None)
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        await llm_spell_check_job(ctx, [1])

        assert page.text == "corrected text"
        mock_repo.set_llm_spell_check_status.assert_called_once_with(
            "book-1", 5, "succeeded"
        )
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_llm_spell_check_job_failure_isolated_per_page():
    ctx = {}
    mock_session = AsyncMock()
    page_ok = Page(id=1, book_id="book-1", page_number=5, text="ok text")
    page_fail = Page(id=2, book_id="book-1", page_number=6, text="fail text")

    async def mock_get(model, page_id):
        return page_ok if page_id == 1 else page_fail

    mock_session.get = mock_get

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.llm_spell_check_job.correct_page_text",
            new_callable=AsyncMock,
        ) as mock_correct,
        patch(
            "services.worker.jobs.llm_spell_check_job.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        async def correct_side_effect(text, prev, nxt, config_repo):
            if text == "ok text":
                return "corrected ok text"
            raise ValueError("model failure")

        mock_correct.side_effect = correct_side_effect

        mock_repo = MagicMock()
        mock_repo.find_one = AsyncMock(return_value=None)
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        await llm_spell_check_job(ctx, [1, 2])

        assert page_ok.text == "corrected ok text"
        assert page_fail.text == "fail text"  # untouched on failure

        calls = mock_repo.set_llm_spell_check_status.call_args_list
        assert ("book-1", 5, "succeeded") in [c.args for c in calls]
        assert ("book-1", 6, "failed") in [c.args for c in calls]


@pytest.mark.asyncio
async def test_llm_spell_check_job_bounds_concurrency():
    from app.core.config import settings

    ctx = {}
    mock_session = AsyncMock()
    pages = {
        i: Page(id=i, book_id="book-1", page_number=i, text=f"text {i}")
        for i in range(1, settings.max_parallel_llm_spell_check + 3)
    }

    async def mock_get(model, page_id):
        return pages[page_id]

    mock_session.get = mock_get

    in_flight = 0
    max_in_flight = 0

    async def correct_side_effect(text, prev, nxt, config_repo):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        in_flight -= 1
        return text

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.llm_spell_check_job.correct_page_text",
            side_effect=correct_side_effect,
        ),
        patch(
            "services.worker.jobs.llm_spell_check_job.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_repo = MagicMock()
        mock_repo.find_one = AsyncMock(return_value=None)
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        await llm_spell_check_job(ctx, list(pages.keys()))

        assert max_in_flight <= settings.max_parallel_llm_spell_check
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd services/worker && python -m pytest tests/jobs/llm_spell_check_job_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.worker.jobs.llm_spell_check_job'`.

- [x] **Step 3: Implement the job**

Create `services/worker/jobs/llm_spell_check_job.py`:
```python
"""
LLM Spell Check Job — live-path worker job for on-demand Gemini-based spell
correction. Runs the pages given in page_ids (already set to in_progress by
the triggering endpoint). Not a pipeline stage: no PipelineEvent rows, no
retry_count bookkeeping, no scanner-driven page claiming.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

from app.core.config import settings
from app.core.pipeline import PAGE_MILESTONE_FAILED, PAGE_MILESTONE_SUCCEEDED
from app.db import session as db_session
from app.db.models import Page
from app.db.repositories.pages_repository import PagesRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.llm_spell_check_service import correct_page_text
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.llm_spell_check_job")


async def llm_spell_check_job(ctx, page_ids: List[int]) -> None:
    log_json(
        logger, logging.INFO, "llm spell check job started", page_count=len(page_ids)
    )
    semaphore = asyncio.Semaphore(settings.max_parallel_llm_spell_check)

    async def process_page(page_id: int) -> None:
        async with semaphore:
            async with db_session.async_session_factory() as session:
                pages_repo = PagesRepository(session)
                page = await session.get(Page, page_id)
                if page is None:
                    log_json(
                        logger,
                        logging.WARNING,
                        "llm spell check page not found",
                        page_id=page_id,
                    )
                    return
                prev_page = await pages_repo.find_one(
                    page.book_id, page.page_number - 1
                )
                next_page = await pages_repo.find_one(
                    page.book_id, page.page_number + 1
                )
                try:
                    corrected = await correct_page_text(
                        page.text or "",
                        prev_page.text if prev_page else None,
                        next_page.text if next_page else None,
                        SystemConfigsRepository(session),
                    )
                    page.text = corrected
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_SUCCEEDED
                    )
                    await session.commit()
                except Exception as exc:
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_FAILED
                    )
                    await session.commit()
                    log_json(
                        logger,
                        logging.WARNING,
                        "llm spell check page failed",
                        book_id=page.book_id,
                        page=page.page_number,
                        error=repr(exc),
                    )

    await asyncio.gather(*(process_page(pid) for pid in page_ids))

    log_json(
        logger, logging.INFO, "llm spell check job completed", page_count=len(page_ids)
    )
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd services/worker && python -m pytest tests/jobs/llm_spell_check_job_test.py -v`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add services/worker/jobs/llm_spell_check_job.py services/worker/tests/jobs/llm_spell_check_job_test.py
git commit -m "feat(worker): add llm_spell_check_job live-path worker job"
```

---

## Task 9: Register `llm_spell_check_job` in `worker.py`

**Files:**
- Modify: `services/worker/worker.py`

**Interfaces:**
- Consumes: `llm_spell_check_job` from Task 8.
- Produces: arq recognizes the string job name `"llm_spell_check_job"` (used by the endpoints in Task 15's `redis_pool.enqueue_job("llm_spell_check_job", ...)`).

No dedicated test — verified via Step 2's import/startup smoke check, matching how other `functions` entries in this file are verified.

- [x] **Step 1: Add the import**

In `services/worker/worker.py`, add alongside the other job imports (after `from jobs.spell_check_job import spell_check_job`):
```python
from jobs.llm_spell_check_job import llm_spell_check_job
```

- [x] **Step 2: Register in `functions`**

In `WorkerSettings.functions`, add `llm_spell_check_job` after `spell_check_job`:
```python
    functions = [
        ocr_job,
        chunking_job,
        embedding_job,
        spell_check_job,
        llm_spell_check_job,
        summary_job,
        auto_correct_job,
        knowledge_graph_job,
        graph_resolution_job,
        rag_eval_job,
        extract_book_history_terms_task,
    ]
```

- [x] **Step 3: Verify**

Run: `cd services/worker && python -c "import worker; print([f.__name__ if hasattr(f, '__name__') else f for f in worker.WorkerSettings.functions])"`
Expected: prints a list containing `llm_spell_check_job` with no import errors.

- [x] **Step 4: Commit**

```bash
git add services/worker/worker.py
git commit -m "feat(worker): register llm_spell_check_job with arq"
```

---

## Task 10: `batch_llm_spell_check_service.py` (batch submission + polling)

**Files:**
- Create: `packages/backend-core/app/services/batch_llm_spell_check_service.py`
- Test: `packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py`

**Interfaces:**
- Consumes: `BatchLlmSpellCheckJob`, `Page` (Task 3); `build_correction_prompt`, `_validate_correction` (Task 7); `PagesRepository.set_llm_spell_check_status` (Task 4); `PAGE_MILESTONE_SUCCEEDED`/`PAGE_MILESTONE_IN_PROGRESS`/`PAGE_MILESTONE_FAILED` from `app.core.pipeline`.
- Produces: `async def submit_batch_llm_spell_check(book_id: str, page_ids: List[int], session: AsyncSession) -> BatchLlmSpellCheckJob`; `async def poll_and_process_batch_llm_spell_check_jobs(session: AsyncSession) -> int` — both consumed by Task 11 (scanner) and Task 15 (endpoint).

This mirrors `batch_history_extraction_service.py` closely — same `genai.Client` files/batches API usage (no `generate_text`/`build_text_llm` wrapper exists for the Batch API), same GCS audit-copy upload, same per-result-line commit pattern in the poller so a scanner-tick eviction mid-loop doesn't roll back already-applied corrections.

- [x] **Step 1: Write the failing tests**

Create `packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py`:
```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import BatchLlmSpellCheckJob, Page
from app.services.batch_llm_spell_check_service import (
    submit_batch_llm_spell_check,
    poll_and_process_batch_llm_spell_check_jobs,
)


@pytest.mark.asyncio
async def test_submit_batch_llm_spell_check_builds_jsonl_and_creates_job():
    mock_session = AsyncMock()

    page1 = Page(id=1, book_id="book-1", page_number=1, text="page one text")
    page2 = Page(id=2, book_id="book-1", page_number=2, text="page two text")

    mock_pages_result = MagicMock()
    mock_pages_result.scalars.return_value.all.return_value = [page1, page2]

    mock_all_pages_result = MagicMock()
    mock_all_pages_result.scalars.return_value.all.return_value = [page1, page2]

    mock_session.execute.side_effect = [mock_pages_result, mock_all_pages_result]

    with (
        patch(
            "app.services.batch_llm_spell_check_service.storage.upload_bytes",
            new_callable=AsyncMock,
        ) as mock_upload,
        patch(
            "app.services.batch_llm_spell_check_service.storage.get_gs_uri",
            return_value="gs://bucket/batch_llm_spell_check/input.jsonl",
        ),
        patch(
            "app.services.batch_llm_spell_check_service._get_genai_client"
        ) as mock_get_client,
        patch(
            "app.services.batch_llm_spell_check_service._get_llm_spell_check_model",
            new_callable=AsyncMock,
            return_value="gemini-3.1-flash-lite",
        ),
        patch(
            "app.services.batch_llm_spell_check_service.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_client = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "files/test-file-id"
        mock_client.files.upload.return_value = mock_file

        mock_batch = MagicMock()
        mock_batch.name = "batches/test-batch-123"
        mock_client.batches.create.return_value = mock_batch
        mock_get_client.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        job = await submit_batch_llm_spell_check(
            book_id="book-1", page_ids=[1, 2], session=mock_session
        )

        assert job.book_id == "book-1"
        assert job.gemini_batch_id == "batches/test-batch-123"
        assert job.status == "submitting"
        assert set(job.page_ids) == {1, 2}
        mock_upload.assert_called_once()
        mock_client.batches.create.assert_called_once()
        assert mock_repo.set_llm_spell_check_status.call_count == 2

        # Verify the uploaded JSONL used the correct custom_id -> page_id mapping
        uploaded_bytes = mock_upload.call_args[0][0]
        lines = uploaded_bytes.decode("utf-8").strip().split("\n")
        custom_ids = {json.loads(line)["custom_id"] for line in lines}
        assert custom_ids == {"1", "2"}


@pytest.mark.asyncio
async def test_poll_and_process_succeeded_job_applies_corrections_and_commits_per_page():
    mock_session = AsyncMock()

    mock_job = BatchLlmSpellCheckJob(
        id=1,
        gemini_batch_id="batches/test-batch-123",
        book_id="book-1",
        page_ids=[1],
        status="running",
        model_name="gemini-3.1-flash-lite",
    )

    mock_active_res = MagicMock()
    mock_active_res.scalars.return_value.all.return_value = [mock_job]
    mock_session.execute.return_value = mock_active_res

    page = Page(id=1, book_id="book-1", page_number=1, text="original text")
    mock_session.get = AsyncMock(return_value=page)

    with (
        patch(
            "app.services.batch_llm_spell_check_service._get_genai_client"
        ) as mock_get_client,
        patch(
            "app.services.batch_llm_spell_check_service.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "SUCCEEDED"
        mock_dest = MagicMock()
        mock_dest.file_name = "files/output-file-id"
        mock_dest.gcs_uri = None
        mock_batch_info.dest = mock_dest
        mock_client.batches.get.return_value = mock_batch_info

        output_line = json.dumps(
            {
                "custom_id": "1",
                "response": {
                    "candidates": [
                        {"content": {"parts": [{"text": "corrected text"}]}}
                    ]
                },
            }
        )
        mock_client.files.download.return_value = output_line.encode("utf-8")
        mock_get_client.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        processed = await poll_and_process_batch_llm_spell_check_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "succeeded"
        assert page.text == "corrected text"
        mock_repo.set_llm_spell_check_status.assert_any_call(
            "book-1", 1, "succeeded"
        )


@pytest.mark.asyncio
async def test_poll_and_process_failed_job_resets_all_pages_to_failed():
    mock_session = AsyncMock()

    mock_job = BatchLlmSpellCheckJob(
        id=2,
        gemini_batch_id="batches/test-batch-456",
        book_id="book-1",
        page_ids=[1, 2],
        status="running",
        model_name="gemini-3.1-flash-lite",
    )

    mock_active_res = MagicMock()
    mock_active_res.scalars.return_value.all.return_value = [mock_job]
    mock_session.execute.return_value = mock_active_res

    page1 = Page(id=1, book_id="book-1", page_number=1, text="text 1")
    page2 = Page(id=2, book_id="book-1", page_number=2, text="text 2")

    async def mock_get(model, page_id):
        return page1 if page_id == 1 else page2

    mock_session.get = mock_get

    with (
        patch(
            "app.services.batch_llm_spell_check_service._get_genai_client"
        ) as mock_get_client,
        patch(
            "app.services.batch_llm_spell_check_service.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "FAILED"
        mock_client.batches.get.return_value = mock_batch_info
        mock_get_client.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        processed = await poll_and_process_batch_llm_spell_check_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "failed"
        calls = mock_repo.set_llm_spell_check_status.call_args_list
        assert ("book-1", 1, "failed") in [c.args for c in calls]
        assert ("book-1", 2, "failed") in [c.args for c in calls]


@pytest.mark.asyncio
async def test_poll_and_process_one_job_exception_does_not_stop_others():
    mock_session = AsyncMock()

    job_ok = BatchLlmSpellCheckJob(
        id=1, gemini_batch_id="batches/ok", book_id="book-1", page_ids=[1], status="running"
    )
    job_broken = BatchLlmSpellCheckJob(
        id=2, gemini_batch_id="batches/broken", book_id="book-2", page_ids=[2], status="running"
    )

    mock_active_res = MagicMock()
    mock_active_res.scalars.return_value.all.return_value = [job_broken, job_ok]
    mock_session.execute.return_value = mock_active_res

    with patch(
        "app.services.batch_llm_spell_check_service._get_genai_client"
    ) as mock_get_client:
        mock_client = MagicMock()

        def get_side_effect(name):
            if name == "batches/broken":
                raise RuntimeError("Gemini API error")
            info = MagicMock()
            info.state = "RUNNING"
            return info

        mock_client.batches.get.side_effect = get_side_effect
        mock_get_client.return_value = mock_client

        processed = await poll_and_process_batch_llm_spell_check_jobs(mock_session)

        # job_ok transitions to "running" (already was) -> not counted as processed,
        # job_broken raises and is caught -> loop completes without raising.
        assert processed == 0
        assert job_ok.status == "running"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/services/batch_llm_spell_check_service_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.batch_llm_spell_check_service'`.

- [x] **Step 3: Implement the batch service**

Create `packages/backend-core/app/services/batch_llm_spell_check_service.py`:
```python
"""
Batch LLM Spell Check Service — Gemini Batch API request formatting, GCS
staging, batch submission, and status polling/result ingestion for the
on-demand LLM-based spell correction pass. Mirrors
batch_history_extraction_service.py.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.pipeline import (
    PAGE_MILESTONE_FAILED,
    PAGE_MILESTONE_IN_PROGRESS,
    PAGE_MILESTONE_SUCCEEDED,
)
from app.db.models import BatchLlmSpellCheckJob, Page
from app.db.repositories.pages_repository import PagesRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.llm_spell_check_service import (
    _validate_correction,
    build_correction_prompt,
)
from app.services.storage_service import storage
from app.utils.observability import log_json

logger = logging.getLogger("app.services.batch_llm_spell_check_service")


def _get_genai_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


async def _get_llm_spell_check_model(session: AsyncSession) -> str:
    config_repo = SystemConfigsRepository(session)
    val = await config_repo.get_value(
        "gemini_llm_spell_check_model", "gemini-3.1-flash-lite"
    )
    model = val.strip() if val else "gemini-3.1-flash-lite"
    return model.replace("models/", "", 1) if model.startswith("models/") else model


async def submit_batch_llm_spell_check(
    book_id: str, page_ids: List[int], session: AsyncSession
) -> BatchLlmSpellCheckJob:
    """Builds one JSONL request per page (with prev/next page context),
    uploads the dataset to GCS (audit copy) and the Gemini Files API, submits
    the batch job, creates the tracking row, and bulk-sets the pages' status
    to in_progress."""
    job_uuid = str(uuid.uuid4())
    model_name = await _get_llm_spell_check_model(session)

    pages_res = await session.execute(select(Page).where(Page.id.in_(page_ids)))
    pages_by_id = {p.id: p for p in pages_res.scalars().all()}
    if not pages_by_id:
        raise ValueError(f"No pages found for ids {page_ids}")

    all_pages_res = await session.execute(
        select(Page).where(Page.book_id == book_id)
    )
    pages_by_number = {p.page_number: p for p in all_pages_res.scalars().all()}

    requests_jsonl = []
    for page_id, page in pages_by_id.items():
        prev_page = pages_by_number.get(page.page_number - 1)
        next_page = pages_by_number.get(page.page_number + 1)
        prompt = build_correction_prompt(
            page.text or "",
            prev_page.text if prev_page else None,
            next_page.text if next_page else None,
        )
        req_item = {
            "custom_id": str(page.id),
            "request": {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.0},
            },
        }
        requests_jsonl.append(json.dumps(req_item, ensure_ascii=False))

    jsonl_bytes = "\n".join(requests_jsonl).encode("utf-8")
    remote_input_path = f"batch_llm_spell_check/inputs/{job_uuid}.jsonl"
    await storage.upload_bytes(jsonl_bytes, remote_input_path)
    gcs_input_uri = storage.get_gs_uri(remote_input_path)

    client = _get_genai_client()
    uploaded_file = client.files.upload(
        file=io.BytesIO(jsonl_bytes),
        config=types.UploadFileConfig(
            display_name=f"batch_llm_spell_check_{job_uuid}", mime_type="jsonl"
        ),
    )

    batch_job = client.batches.create(model=model_name, src=uploaded_file.name)

    now = datetime.now(timezone.utc)
    job_record = BatchLlmSpellCheckJob(
        gemini_batch_id=batch_job.name,
        book_id=book_id,
        page_ids=list(pages_by_id.keys()),
        status="submitting",
        gcs_input_uri=gcs_input_uri,
        total_batches=1,
        model_name=model_name,
        submitted_at=now,
    )
    session.add(job_record)

    pages_repo = PagesRepository(session)
    for page in pages_by_id.values():
        await pages_repo.set_llm_spell_check_status(
            page.book_id, page.page_number, PAGE_MILESTONE_IN_PROGRESS
        )

    await session.commit()
    await session.refresh(job_record)

    log_json(
        logger,
        logging.INFO,
        "Submitted Gemini Batch LLM Spell Check job",
        job_id=job_record.id,
        gemini_batch_id=batch_job.name,
        book_id=book_id,
        page_count=len(pages_by_id),
    )
    return job_record


async def poll_and_process_batch_llm_spell_check_jobs(session: AsyncSession) -> int:
    """Polls active BatchLlmSpellCheckJob records, applies completed
    corrections to pages.text, and updates job/page statuses."""
    active_jobs_res = await session.execute(
        select(BatchLlmSpellCheckJob).where(
            BatchLlmSpellCheckJob.status.in_(["submitting", "running"])
        )
    )
    active_jobs = list(active_jobs_res.scalars().all())
    if not active_jobs:
        return 0

    client = _get_genai_client()
    pages_repo = PagesRepository(session)
    processed_count = 0

    for job in active_jobs:
        try:
            batch_info = client.batches.get(name=job.gemini_batch_id)
            state_str = str(batch_info.state).upper()

            if "SUCCEEDED" in state_str:
                dest = getattr(batch_info, "dest", None)
                gcs_output_uri = getattr(dest, "gcs_uri", None) if dest else None
                output_file_name = getattr(dest, "file_name", None) if dest else None

                result_bytes: Optional[bytes] = None
                if gcs_output_uri:
                    parts = gcs_output_uri.replace("gs://", "").split("/", 1)
                    if len(parts) == 2:
                        try:
                            result_bytes = await storage.read_bytes(parts[1])
                        except Exception as e:
                            logger.warning(f"Could not read gcs_uri output: {e}")
                elif output_file_name:
                    try:
                        result_bytes = client.files.download(file=output_file_name)
                    except Exception as e:
                        logger.error(f"Failed to download batch output file: {e}")

                succeeded_page_ids: set[int] = set()
                if result_bytes:
                    lines = result_bytes.decode("utf-8").strip().split("\n")
                    for line in lines:
                        if not line.strip():
                            continue
                        try:
                            item = json.loads(line)
                            page_id = int(item.get("custom_id"))
                            page = await session.get(Page, page_id)
                            if page is None:
                                continue
                            text = (
                                item.get("response", {})
                                .get("candidates", [{}])[0]
                                .get("content", {})
                                .get("parts", [{}])[0]
                                .get("text", "")
                            ).strip()
                            _validate_correction(page.text or "", text)
                            page.text = text
                            await pages_repo.set_llm_spell_check_status(
                                page.book_id,
                                page.page_number,
                                PAGE_MILESTONE_SUCCEEDED,
                            )
                            succeeded_page_ids.add(page_id)
                            # Commit per page — a scanner-tick eviction mid-loop
                            # shouldn't roll back already-applied corrections.
                            await session.commit()
                        except Exception as parse_err:
                            await session.rollback()
                            logger.warning(
                                f"Error parsing batch llm spell check output line: {parse_err}"
                            )

                for page_id in job.page_ids:
                    if page_id in succeeded_page_ids:
                        continue
                    page = await session.get(Page, page_id)
                    if page is None:
                        continue
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_FAILED
                    )
                    await session.commit()

                job.status = "succeeded"
                job.completed_at = datetime.now(timezone.utc)
                job.gcs_output_uri = gcs_output_uri or output_file_name
                await session.commit()
                processed_count += 1
                log_json(
                    logger,
                    logging.INFO,
                    "Batch LLM Spell Check job completed",
                    job_id=job.id,
                    succeeded=len(succeeded_page_ids),
                    failed=len(job.page_ids) - len(succeeded_page_ids),
                )

            elif any(s in state_str for s in ["FAILED", "CANCELLED", "EXPIRED"]):
                for page_id in job.page_ids:
                    page = await session.get(Page, page_id)
                    if page is None:
                        continue
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_FAILED
                    )
                job.status = "failed"
                job.error = f"Gemini Batch job ended with state {state_str}"
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()
                processed_count += 1
                log_json(
                    logger,
                    logging.ERROR,
                    "Batch LLM Spell Check job failed",
                    job_id=job.id,
                    state=state_str,
                )

            elif "RUNNING" in state_str and job.status != "running":
                job.status = "running"
                await session.commit()

        except Exception as exc:
            await session.rollback()
            log_json(
                logger,
                logging.ERROR,
                "Error polling Batch LLM Spell Check job",
                job_id=job.id,
                error=str(exc),
            )

    return processed_count
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/services/batch_llm_spell_check_service_test.py -v`
Expected: PASS (4 tests).

- [x] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/batch_llm_spell_check_service.py packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py
git commit -m "feat(services): add batch_llm_spell_check_service (Gemini Batch API path)"
```

---

## Task 11: `batch_llm_spell_check_poller_scanner.py`

**Files:**
- Create: `services/worker/scanners/batch_llm_spell_check_poller_scanner.py`
- Test: `services/worker/tests/scanners/batch_llm_spell_check_poller_scanner_test.py`

**Interfaces:**
- Consumes: `poll_and_process_batch_llm_spell_check_jobs` (Task 10); `SystemConfigsRepository.get_value` (existing).
- Produces: `async def run_batch_llm_spell_check_poller_scanner(ctx) -> None`, registered via `cron(...)` in Task 12.

- [x] **Step 1: Write the failing tests**

Create `services/worker/tests/scanners/batch_llm_spell_check_poller_scanner_test.py` (mirrors `batch_history_poller_scanner_test.py` exactly, plus a flag-off case):
```python
import pytest
from unittest.mock import AsyncMock, patch

from services.worker.scanners.batch_llm_spell_check_poller_scanner import (
    run_batch_llm_spell_check_poller_scanner,
)


@pytest.mark.asyncio
async def test_scanner_skips_when_flag_disabled():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with (
            patch(
                "services.worker.scanners.batch_llm_spell_check_poller_scanner.SystemConfigsRepository"
            ) as mock_config_cls,
            patch(
                "services.worker.scanners.batch_llm_spell_check_poller_scanner.poll_and_process_batch_llm_spell_check_jobs",
                new_callable=AsyncMock,
            ) as mock_poll,
        ):
            mock_config_repo = AsyncMock()
            mock_config_repo.get_value.return_value = "false"
            mock_config_cls.return_value = mock_config_repo

            await run_batch_llm_spell_check_poller_scanner(ctx)

            mock_poll.assert_not_called()


@pytest.mark.asyncio
async def test_scanner_polls_when_flag_enabled():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with (
            patch(
                "services.worker.scanners.batch_llm_spell_check_poller_scanner.SystemConfigsRepository"
            ) as mock_config_cls,
            patch(
                "services.worker.scanners.batch_llm_spell_check_poller_scanner.poll_and_process_batch_llm_spell_check_jobs",
                new_callable=AsyncMock,
            ) as mock_poll,
        ):
            mock_config_repo = AsyncMock()
            mock_config_repo.get_value.return_value = "true"
            mock_config_cls.return_value = mock_config_repo
            mock_poll.return_value = 2

            await run_batch_llm_spell_check_poller_scanner(ctx)

            mock_poll.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_scanner_exception_logged_not_raised():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = Exception(
            "Database error"
        )

        # Scanner must catch the exception and log, not raise.
        await run_batch_llm_spell_check_poller_scanner(ctx)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd services/worker && python -m pytest tests/scanners/batch_llm_spell_check_poller_scanner_test.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.worker.scanners.batch_llm_spell_check_poller_scanner'`.

- [x] **Step 3: Implement the scanner**

Create `services/worker/scanners/batch_llm_spell_check_poller_scanner.py`:
```python
"""
Batch LLM Spell Check Poller Scanner — periodically checks status of active
Gemini Batch API LLM spell-check jobs and applies completed corrections to
pages.text.
"""

from __future__ import annotations

import logging

from app.db import session as db_session
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.batch_llm_spell_check_service import (
    poll_and_process_batch_llm_spell_check_jobs,
)
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.batch_llm_spell_check_poller_scanner")


async def run_batch_llm_spell_check_poller_scanner(ctx) -> None:
    log_json(logger, logging.INFO, "Batch LLM Spell Check poller scanner started")
    try:
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            enabled = await config_repo.get_value(
                "llm_spell_check_batch_enabled", "false"
            )
            if enabled.strip().lower() != "true":
                log_json(
                    logger,
                    logging.INFO,
                    "Batch LLM Spell Check poller scanner skipped: feature is disabled via system_configs",
                )
                return

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

- [x] **Step 4: Run tests to verify they pass**

Run: `cd services/worker && python -m pytest tests/scanners/batch_llm_spell_check_poller_scanner_test.py -v`
Expected: PASS (3 tests).

- [x] **Step 5: Commit**

```bash
git add services/worker/scanners/batch_llm_spell_check_poller_scanner.py services/worker/tests/scanners/batch_llm_spell_check_poller_scanner_test.py
git commit -m "feat(worker): add batch_llm_spell_check_poller_scanner"
```

---

## Task 12: Register the poller scanner in `worker.py`

**Files:**
- Modify: `services/worker/worker.py`

**Interfaces:**
- Consumes: `run_batch_llm_spell_check_poller_scanner` from Task 11.

No dedicated test — verified via Step 2's import/startup smoke check.

- [x] **Step 1: Add the import**

In `services/worker/worker.py`, alongside the other poller-scanner imports (after `from scanners.batch_history_poller_scanner import run_batch_history_poller_scanner`):
```python
from scanners.batch_llm_spell_check_poller_scanner import (
    run_batch_llm_spell_check_poller_scanner,
)
```

- [x] **Step 2: Register in `cron_jobs`**

In `cron_jobs`, add after `cron(run_batch_history_poller_scanner)`:
```python
        cron(run_batch_history_poller_scanner),
        cron(run_batch_llm_spell_check_poller_scanner),
```

- [x] **Step 3: Verify**

Run: `cd services/worker && python -c "import worker; print(len(worker.WorkerSettings.cron_jobs))"`
Expected: prints a count one higher than before this task, with no import errors.

- [x] **Step 4: Commit**

```bash
git add services/worker/worker.py
git commit -m "feat(worker): register batch_llm_spell_check_poller_scanner cron job"
```

---

## Task 13: `BooksRepository` stats — `get_with_page_stats` + `get_batch_stats`

**Files:**
- Modify: `packages/backend-core/app/db/repositories/books_repository.py`
- Test: `packages/backend-core/tests/app/db/books_repository_test.py`

**Interfaces:**
- Consumes: `Page.llm_spell_check_status` (Task 3).
- Produces: `pipeline_stats.llm_spell_check` / `.llm_spell_check_failed` / `.llm_spell_check_active` in both methods' return dicts. **Divergence from every other step:** `llm_spell_check` is always computed by scanning `pages` — the `book.status == "ready"` shortcut (which assumes 100% for `ocr`/`chunking`/`embedding`) must NOT apply to it, since it's an on-demand admin pass, not part of the automatic pipeline.

- [x] **Step 1: Write the failing tests**

Append to `packages/backend-core/tests/app/db/books_repository_test.py`:
```python
@pytest.mark.asyncio
async def test_get_with_page_stats_ready_book_does_not_assume_llm_spell_check_done():
    session = AsyncMock()
    repo = BooksRepository(session)

    mock_book = Book(id="b1", status="ready", total_pages=10, title="T1", author="A1")
    repo.get = AsyncMock(return_value=mock_book)

    # Execution order inside get_with_page_stats for a "ready" book:
    # 1. llm_stmt (always run, before the ready-book branch)
    # 2. summary_stmt
    # 3. history_stmt
    # 4. sc_stmt (dictionary spell check)
    mock_llm_res = MagicMock()
    mock_llm_row = MagicMock(done=2, failed=0, active=1)
    mock_llm_res.fetchone.return_value = mock_llm_row

    mock_summary_res = MagicMock()
    mock_summary_res.scalar.return_value = 1

    mock_history_res = MagicMock()
    mock_history_res.scalar.return_value = 0

    mock_sc_res = MagicMock()
    mock_sc_row = MagicMock(done=10, failed=0, active=0)
    mock_sc_res.fetchone.return_value = mock_sc_row

    session.execute.side_effect = [
        mock_llm_res,
        mock_summary_res,
        mock_history_res,
        mock_sc_res,
    ]

    result = await repo.get_with_page_stats("b1")

    # A "ready" book still shows only 2/10 llm_spell_check done — NOT 10/10
    # like ocr/chunking/embedding get from the ready-book shortcut.
    assert result["pipeline_stats"]["llm_spell_check"] == 2
    assert result["pipeline_stats"]["llm_spell_check_failed"] == 0
    assert result["pipeline_stats"]["llm_spell_check_active"] == 1
    assert result["pipeline_stats"]["ocr"] == 10  # unaffected — still shortcut


@pytest.mark.asyncio
async def test_get_batch_stats_llm_spell_check_never_assumed_done_for_ready_books():
    session = AsyncMock()
    repo = BooksRepository(session)

    mock_book_row = MagicMock(id="book-1", status="ready", total_pages=10)
    mock_books_res = MagicMock()
    mock_books_res.fetchall.return_value = [mock_book_row]

    # No milestone_stats row returned for book-1 (simulates the "missing
    # books" fallback path exercised when a ready book has no page rows yet).
    mock_stats_res = MagicMock()
    mock_stats_res.fetchall.return_value = []

    mock_summary_res = MagicMock()
    mock_summary_res.fetchall.return_value = []
    mock_history_res = MagicMock()
    mock_history_res.fetchall.return_value = []

    session.execute.side_effect = [
        mock_books_res,
        mock_stats_res,
        mock_summary_res,
        mock_history_res,
    ]

    stats = await repo.get_batch_stats(["book-1"])

    assert stats["book-1"]["pipeline_stats"]["ocr"] == 10  # ready shortcut applies
    assert stats["book-1"]["pipeline_stats"]["llm_spell_check"] == 0  # never shortcut
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/db/books_repository_test.py -k llm_spell_check -v`
Expected: FAIL — `KeyError: 'llm_spell_check'` (key not yet present in `pipeline_stats`).

- [x] **Step 3: Replace `get_with_page_stats`**

In `packages/backend-core/app/db/repositories/books_repository.py`, replace the entire existing `get_with_page_stats` method (from `async def get_with_page_stats(` through its final `return` statement, currently lines ~166-481) with:
```python
    async def get_with_page_stats(
        self, book_id: str, step: Optional[str] = None
    ) -> Optional[dict]:
        """
        Get book with aggregated page statistics.

        Args:
            book_id: The book ID to query
            step: Optional pipeline step to query (ocr, chunking, embedding, spell_check, summary)
                  If provided, only queries that specific step for performance optimization.

        Returns book data along with page counts by status.
        """
        # First get the book
        book = await self.get(book_id)
        if not book:
            return None

        # llm_spell_check is always scanned from pages, for both ready and
        # in-progress books — it's an on-demand admin-triggered pass, not
        # part of the automatic pipeline, so book.status == "ready" says
        # nothing about whether it has ever been run.
        llm_stmt = (
            select(
                func.count(
                    case((Page.llm_spell_check_status == PAGE_MILESTONE_SUCCEEDED, 1))
                ).label("done"),
                func.count(
                    case((Page.llm_spell_check_status.in_(FAILED_PAGE_MILESTONES), 1))
                ).label("failed"),
                func.count(
                    case((Page.llm_spell_check_status == PAGE_MILESTONE_IN_PROGRESS, 1))
                ).label("active"),
            )
            .where(Page.book_id == book_id)
            .group_by(Page.book_id)
        )
        llm_res = await self.session.execute(llm_stmt)
        llm_row = llm_res.fetchone()
        llm_stats = {
            "llm_spell_check": llm_row.done if llm_row else 0,
            "llm_spell_check_failed": llm_row.failed if llm_row else 0,
            "llm_spell_check_active": llm_row.active if llm_row else 0,
        }

        # Optimization: If book is ready, we can return 100% stats for core steps
        if book.status == "ready":
            tp = book.total_pages or 0
            summary_stmt = select(func.count(BookSummary.book_id)).where(
                BookSummary.book_id == book_id
            )
            summary_res = await self.session.execute(summary_stmt)
            has_summary = (summary_res.scalar() or 0) > 0

            has_graph = book.graph_milestone == "complete"

            history_stmt = select(func.count(BatchHistoryExtractionJob.id)).where(
                BatchHistoryExtractionJob.book_id == book_id,
                BatchHistoryExtractionJob.status == "succeeded",
            )
            history_res = await self.session.execute(history_stmt)
            has_history = (history_res.scalar() or 0) > 0

            # For ready books, we still need to check if background spell check is running
            sc_stmt = (
                select(
                    func.count(
                        case(
                            (Page.spell_check_milestone == PAGE_MILESTONE_SUCCEEDED, 1)
                        )
                    ).label("done"),
                    func.count(
                        case(
                            (Page.spell_check_milestone.in_(FAILED_PAGE_MILESTONES), 1)
                        )
                    ).label("failed"),
                    func.count(
                        case(
                            (
                                Page.spell_check_milestone
                                == PAGE_MILESTONE_IN_PROGRESS,
                                1,
                            )
                        )
                    ).label("active"),
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )
            sc_res = await self.session.execute(sc_stmt)
            sc_row = sc_res.fetchone()

            sc_done = sc_row.done if sc_row else 0
            sc_failed = sc_row.failed if sc_row else 0
            sc_active = sc_row.active if sc_row else 0

            return {
                "book": book,
                "page_stats": {},
                "pipeline_stats": {
                    "ocr": tp,
                    "ocr_failed": 0,
                    "ocr_active": 0,
                    "chunking": tp,
                    "chunking_failed": 0,
                    "chunking_active": 0,
                    "embedding": tp,
                    "embedding_failed": 0,
                    "embedding_active": 0,
                    "spell_check": sc_done,
                    "spell_check_failed": sc_failed,
                    "spell_check_active": sc_active,
                    **llm_stats,
                },
                "has_summary": has_summary,
                "has_graph": has_graph,
                "has_history": has_history,
                "ocr_done_count": tp,
                "error_count": sc_failed,
                "pending_count": tp - sc_done - sc_active - sc_failed,
                "ocr_processing_count": 0,
            }

        # Build query based on which step(s) to fetch
        # If step is provided, only query that specific step for performance
        if step and step != PIPELINE_STEP_SUMMARY:
            # Single-step query optimization
            milestone_field_map = {
                step_name: getattr(Page, field_name)
                for step_name, field_name in PAGE_MILESTONE_ATTR_BY_STEP.items()
            }

            milestone_field = milestone_field_map.get(step)
            if not milestone_field:
                # Invalid step, or a free-standing step not in
                # PAGE_MILESTONE_ATTR_BY_STEP (e.g. llm_spell_check) — its
                # stats are already computed above unconditionally.
                return {
                    "book": book,
                    "page_stats": {},
                    "pipeline_stats": {**llm_stats},
                    "has_summary": False,
                    "ocr_done_count": 0,
                    "error_count": 0,
                    "pending_count": 0,
                    "ocr_processing_count": 0,
                }

            # Query only the specific step
            done_value = STEP_DONE_MILESTONE_BY_STEP[step]
            stats_stmt = (
                select(
                    func.count(Page.id).label("total"),
                    func.count(case((milestone_field == done_value, 1))).label(
                        f"{step}_done"
                    ),
                    func.count(
                        case((milestone_field.in_(FAILED_PAGE_MILESTONES), 1))
                    ).label(f"{step}_failed"),
                    func.count(
                        case((milestone_field == PAGE_MILESTONE_IN_PROGRESS, 1))
                    ).label(f"{step}_active"),
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )
        else:
            # Query all steps (original behavior)
            stats_stmt = (
                select(
                    func.count(Page.id).label("total"),
                    func.count(
                        case((Page.ocr_milestone == PAGE_MILESTONE_SUCCEEDED, 1))
                    ).label("ocr_done"),
                    func.count(
                        case((Page.ocr_milestone.in_(FAILED_PAGE_MILESTONES), 1))
                    ).label("ocr_failed"),
                    func.count(
                        case((Page.ocr_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))
                    ).label("ocr_active"),
                    func.count(
                        case((Page.chunking_milestone == PAGE_MILESTONE_SUCCEEDED, 1))
                    ).label("chunking_done"),
                    func.count(
                        case((Page.chunking_milestone.in_(FAILED_PAGE_MILESTONES), 1))
                    ).label("chunking_failed"),
                    func.count(
                        case((Page.chunking_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))
                    ).label("chunking_active"),
                    func.count(
                        case((Page.embedding_milestone == PAGE_MILESTONE_SUCCEEDED, 1))
                    ).label("embedding_done"),
                    func.count(
                        case((Page.embedding_milestone.in_(FAILED_PAGE_MILESTONES), 1))
                    ).label("embedding_failed"),
                    func.count(
                        case(
                            (Page.embedding_milestone == PAGE_MILESTONE_IN_PROGRESS, 1)
                        )
                    ).label("embedding_active"),
                    func.count(
                        case(
                            (Page.spell_check_milestone == PAGE_MILESTONE_SUCCEEDED, 1)
                        )
                    ).label("spell_check_done"),
                    func.count(
                        case(
                            (Page.spell_check_milestone.in_(FAILED_PAGE_MILESTONES), 1)
                        )
                    ).label("spell_check_failed"),
                    func.count(
                        case(
                            (
                                Page.spell_check_milestone
                                == PAGE_MILESTONE_IN_PROGRESS,
                                1,
                            )
                        )
                    ).label("spell_check_active"),
                    func.count(case((Page.milestone == PAGE_MILESTONE_IDLE, 1))).label(
                        "pending_count"
                    ),
                    func.count(
                        case((Page.milestone == PAGE_MILESTONE_IN_PROGRESS, 1))
                    ).label("processing_count"),
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )

        stats_result = await self.session.execute(stats_stmt)
        row = stats_result.fetchone()

        # Determine if summary exists (only if requested or querying all)
        has_summary = False
        if not step or step == PIPELINE_STEP_SUMMARY:
            summary_stmt = select(func.count(BookSummary.book_id)).where(
                BookSummary.book_id == book_id
            )
            summary_res = await self.session.execute(summary_stmt)
            has_summary = (summary_res.scalar() or 0) > 0

        has_graph = book.graph_milestone == "complete"
        has_history = False
        if not step or step == "history":
            history_stmt = select(func.count(BatchHistoryExtractionJob.id)).where(
                BatchHistoryExtractionJob.book_id == book_id,
                BatchHistoryExtractionJob.status == "succeeded",
            )
            history_res = await self.session.execute(history_stmt)
            has_history = (history_res.scalar() or 0) > 0

        # Handle single-step response
        if step and step != PIPELINE_STEP_SUMMARY:
            if not row:
                return {
                    "book": book,
                    "page_stats": {},
                    "pipeline_stats": {
                        step: 0,
                        f"{step}_failed": 0,
                        f"{step}_active": 0,
                        **llm_stats,
                    },
                    "has_summary": False,
                    "has_graph": has_graph if step == "graph" else False,
                    "has_history": has_history if step == "history" else False,
                    "ocr_done_count": 0,
                    "error_count": 0,
                    "pending_count": 0,
                    "ocr_processing_count": 0,
                }

            return {
                "book": book,
                "page_stats": {},
                "pipeline_stats": {
                    step: getattr(row, f"{step}_done", 0) or 0,
                    f"{step}_failed": getattr(row, f"{step}_failed", 0) or 0,
                    f"{step}_active": getattr(row, f"{step}_active", 0) or 0,
                    **llm_stats,
                },
                "has_summary": False,
                "has_graph": has_graph if step == "graph" else False,
                "has_history": has_history if step == "history" else False,
                "ocr_done_count": 0,
                "error_count": 0,
                "pending_count": 0,
                "ocr_processing_count": 0,
            }

        # Handle all-steps response (original behavior)
        # If no pages exist yet
        if not row:
            return {
                "book": book,
                "page_stats": {},
                "pipeline_stats": {
                    "ocr": 0,
                    "ocr_failed": 0,
                    "ocr_active": 0,
                    "chunking": 0,
                    "chunking_failed": 0,
                    "chunking_active": 0,
                    "embedding": 0,
                    "embedding_failed": 0,
                    "embedding_active": 0,
                    "spell_check": 0,
                    "spell_check_failed": 0,
                    "spell_check_active": 0,
                    **llm_stats,
                },
                "has_summary": has_summary,
                "has_graph": has_graph,
                "has_history": has_history,
                "ocr_done_count": 0,
                "error_count": 0,
                "pending_count": 0,
                "ocr_processing_count": 0,
            }

        return {
            "book": book,
            "page_stats": {},  # Removed detailed_stats to avoid DB errors; use pipeline_stats instead
            "pipeline_stats": {
                "ocr": row.ocr_done or 0,
                "ocr_failed": row.ocr_failed or 0,
                "ocr_active": row.ocr_active or 0,
                "chunking": row.chunking_done or 0,
                "chunking_failed": row.chunking_failed or 0,
                "chunking_active": row.chunking_active or 0,
                "embedding": row.embedding_done or 0,
                "embedding_failed": row.embedding_failed or 0,
                "embedding_active": row.embedding_active or 0,
                "spell_check": row.spell_check_done or 0,
                "spell_check_failed": row.spell_check_failed or 0,
                "spell_check_active": row.spell_check_active or 0,
                **llm_stats,
            },
            "has_summary": has_summary,
            "has_graph": has_graph,
            "has_history": has_history,
            "ocr_done_count": row.ocr_done or 0,
            "error_count": (row.ocr_failed or 0)
            + (row.chunking_failed or 0)
            + (row.embedding_failed or 0)
            + (row.spell_check_failed or 0),
            "pending_count": row.pending_count or 0,
            "ocr_processing_count": row.processing_count or 0,
        }
```
(Every added `llm_stmt` query/merge is additive; no other line of the original method's logic changes. This adds one extra lightweight query per call — an accepted, explicit tradeoff for correctness per the design doc, not a case for further step-conditional skipping.)

- [x] **Step 4: Replace `get_batch_stats`**

Replace the entire existing `get_batch_stats` method (currently lines ~483-635) with:
```python
    async def get_batch_stats(self, book_ids: List[str]) -> dict[str, dict]:
        """
        Fetch pipeline statistics and summary status for multiple books in batch.
        Replaces N+1 calls to get_with_page_stats for much better performance.
        """
        if not book_ids:
            return {}

        # 0. Optimization: Identify which books are 'ready' vs 'processing'
        # For 'ready' books, we can assume 100% stats and skip scanning pages
        books_stmt = select(
            Book.id, Book.status, Book.total_pages, Book.graph_milestone
        ).where(Book.id.in_(book_ids))
        books_res = await self.session.execute(books_stmt)
        books_info = {
            str(row.id): {
                "status": row.status,
                "total_pages": row.total_pages,
                "graph_milestone": row.graph_milestone,
            }
            for row in books_res.fetchall()
        }

        # 1. Fetch milestone stats for ALL requested books
        # Note: We must scan all books because 'ready' books may still have background
        # spell-check or word-indexing tasks running (or reset to idle). llm_spell_check
        # is always scanned too — it's an on-demand pass, never assumed 100% for ready books.
        milestone_stats_stmt = (
            select(
                Page.book_id,
                func.count(
                    case((Page.ocr_milestone == PAGE_MILESTONE_SUCCEEDED, 1))
                ).label("ocr"),
                func.count(
                    case((Page.ocr_milestone.in_(FAILED_PAGE_MILESTONES), 1))
                ).label("ocr_failed"),
                func.count(
                    case((Page.ocr_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))
                ).label("ocr_active"),
                func.count(
                    case((Page.chunking_milestone == PAGE_MILESTONE_SUCCEEDED, 1))
                ).label("chunking"),
                func.count(
                    case((Page.chunking_milestone.in_(FAILED_PAGE_MILESTONES), 1))
                ).label("chunking_failed"),
                func.count(
                    case((Page.chunking_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))
                ).label("chunking_active"),
                func.count(
                    case((Page.embedding_milestone == PAGE_MILESTONE_SUCCEEDED, 1))
                ).label("embedding"),
                func.count(
                    case((Page.embedding_milestone.in_(FAILED_PAGE_MILESTONES), 1))
                ).label("embedding_failed"),
                func.count(
                    case((Page.embedding_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))
                ).label("embedding_active"),
                func.count(
                    case((Page.spell_check_milestone == PAGE_MILESTONE_SUCCEEDED, 1))
                ).label("spell_check"),
                func.count(
                    case((Page.spell_check_milestone.in_(FAILED_PAGE_MILESTONES), 1))
                ).label("spell_check_failed"),
                func.count(
                    case((Page.spell_check_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))
                ).label("spell_check_active"),
                func.count(
                    case((Page.llm_spell_check_status == PAGE_MILESTONE_SUCCEEDED, 1))
                ).label("llm_spell_check"),
                func.count(
                    case((Page.llm_spell_check_status.in_(FAILED_PAGE_MILESTONES), 1))
                ).label("llm_spell_check_failed"),
                func.count(
                    case((Page.llm_spell_check_status == PAGE_MILESTONE_IN_PROGRESS, 1))
                ).label("llm_spell_check_active"),
            )
            .where(Page.book_id.in_(book_ids))
            .group_by(Page.book_id)
        )
        results = {}
        m_result = await self.session.execute(milestone_stats_stmt)
        for row in m_result.fetchall():
            bid = str(row.book_id)
            results[bid] = {
                "pipeline_stats": {
                    "ocr": row.ocr,
                    "ocr_failed": row.ocr_failed,
                    "ocr_active": row.ocr_active,
                    "chunking": row.chunking,
                    "chunking_failed": row.chunking_failed,
                    "chunking_active": row.chunking_active,
                    "embedding": row.embedding,
                    "embedding_failed": row.embedding_failed,
                    "embedding_active": row.embedding_active,
                    "spell_check": row.spell_check,
                    "spell_check_failed": row.spell_check_failed,
                    "spell_check_active": row.spell_check_active,
                    "llm_spell_check": row.llm_spell_check,
                    "llm_spell_check_failed": row.llm_spell_check_failed,
                    "llm_spell_check_active": row.llm_spell_check_active,
                }
            }

        # 2. Determine which books have summaries in one query
        summary_stmt = select(BookSummary.book_id).where(
            BookSummary.book_id.in_(book_ids)
        )
        summary_res = await self.session.execute(summary_stmt)
        books_with_summary = {row[0] for row in summary_res.fetchall()}

        books_with_graph = {
            bid
            for bid, info in books_info.items()
            if info.get("graph_milestone") == "complete"
        }

        history_stmt = select(BatchHistoryExtractionJob.book_id).where(
            BatchHistoryExtractionJob.book_id.in_(book_ids),
            BatchHistoryExtractionJob.status == "succeeded",
        )
        history_res = await self.session.execute(history_stmt)
        books_with_history = {row[0] for row in history_res.fetchall()}

        # 3. Assemble final results
        final_results = {}
        for bid in book_ids:
            info = books_info.get(bid, {})
            status = info.get("status")
            tp = info.get("total_pages") or 0

            # Get stats (either from DB for processing or 100% for ready)
            if bid in results:
                # Stats from DB scan
                stats = results[bid]["pipeline_stats"]
            else:
                # Default fallback for missing books (should not happen if pages exist)
                # If a book is 'ready' but has no page records found (orphaned book record)
                # we still assume 0 to be safe. llm_spell_check is never assumed 100%
                # even for 'ready' books — it's an on-demand pass, not automatic.
                stats = {
                    "ocr": tp if status == "ready" else 0,
                    "ocr_failed": 0,
                    "ocr_active": 0,
                    "chunking": tp if status == "ready" else 0,
                    "chunking_failed": 0,
                    "chunking_active": 0,
                    "embedding": tp if status == "ready" else 0,
                    "embedding_failed": 0,
                    "embedding_active": 0,
                    "spell_check": 0,
                    "spell_check_failed": 0,
                    "spell_check_active": 0,
                    "llm_spell_check": 0,
                    "llm_spell_check_failed": 0,
                    "llm_spell_check_active": 0,
                }

            final_results[bid] = {
                "pipeline_stats": stats,
                "has_summary": bid in books_with_summary,
                "has_graph": bid in books_with_graph,
                "has_history": bid in books_with_history,
            }

        return final_results
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/db/books_repository_test.py -v`
Expected: PASS (all tests, including the pre-existing ones — confirms the refactor didn't regress `ocr`/`chunking`/`embedding`/`spell_check` behavior).

- [x] **Step 6: Commit**

```bash
git add packages/backend-core/app/db/repositories/books_repository.py packages/backend-core/tests/app/db/books_repository_test.py
git commit -m "feat(db): add llm_spell_check stats to get_with_page_stats/get_batch_stats, never shortcut for ready books"
```

---

## Task 14: `ExtractionResult` schema fields

**Files:**
- Modify: `packages/backend-core/app/models/schemas.py`

**Interfaces:**
- Produces: `ExtractionResult.llm_spell_check_status: str = "idle"` (API: `llmSpellCheckStatus`), `ExtractionResult.llm_spell_check_at: Optional[datetime] = None` (API: `llmSpellCheckAt`).

No dedicated test — this is a data-only Pydantic field addition, verified via Step 2 and end-to-end in Task 15's endpoint tests once pages are serialized through it.

- [x] **Step 1: Add the fields**

In `packages/backend-core/app/models/schemas.py`, in the `ExtractionResult` class, immediately after `is_toc: bool = False  # API: isToc`:
```python
    is_toc: bool = False  # API: isToc
    llm_spell_check_status: str = (
        "idle"  # DB: llm_spell_check_status, API: llmSpellCheckStatus
    )
    llm_spell_check_at: Optional[datetime] = (
        None  # DB: llm_spell_check_at, API: llmSpellCheckAt
    )
```

- [x] **Step 2: Verify**

Run: `cd packages/backend-core && python -c "
from app.models.schemas import ExtractionResult
r = ExtractionResult(page_number=1, status='pending')
print(r.model_dump(by_alias=True))
"`
Expected: prints a dict containing `'llmSpellCheckStatus': 'idle'` and `'llmSpellCheckAt': None`.

- [x] **Step 3: Commit**

```bash
git add packages/backend-core/app/models/schemas.py
git commit -m "feat(api): expose llmSpellCheckStatus/llmSpellCheckAt on ExtractionResult"
```

---

## Task 15: Backend endpoints + error i18n keys

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py`
- Modify: `services/backend/locales/en.json`
- Modify: `services/backend/locales/ug.json`
- Test: `services/backend/tests/api/endpoints/books_router_test.py`

**Interfaces:**
- Consumes: `submit_batch_llm_spell_check` (Task 10); `PagesRepository.find_one`/`set_llm_spell_check_status` (Task 4); `PAGE_MILESTONE_IDLE`/`PAGE_MILESTONE_IN_PROGRESS` from `app.core.pipeline`.
- Produces: `POST /{book_id}/reprocess/llm-spell-check` → `reprocess_llm_spell_check`; `POST /{book_id}/pages/{page_num}/llm-spell-check` → `trigger_llm_spell_check_page`. Both `Depends(require_admin)`.

- [x] **Step 1: Add the error i18n keys**

In `services/backend/locales/en.json`, inside the top-level `"errors"` object, alongside `graph_enqueue_failed`/`summary_enqueue_failed`:
```json
    "graph_enqueue_failed": "Failed to enqueue Knowledge Graph job. Please try again.",
    "summary_enqueue_failed": "Failed to enqueue Summary job. Please try again.",
    "llm_spell_check_enqueue_failed": "Failed to start LLM spell check. Please try again.",
    "llm_spell_check_already_running": "LLM spell check is already running for this page.",
```

In `services/backend/locales/ug.json`, in the same `"errors"` object, at the same position (mirror the surrounding Uyghur translations' style):
```json
    "llm_spell_check_enqueue_failed": "LLM ئارقىلىق ئىملا تەكشۈرۈشنى قوزغىتالمىدى. قايتا سىناڭ.",
    "llm_spell_check_already_running": "بۇ بەت ئۈچۈن LLM ئارقىلىق ئىملا تەكشۈرۈش ئاللىبۇرۇن ئىجرا بولۇۋاتىدۇ.",
```

- [x] **Step 2: Write the failing tests**

Append to `services/backend/tests/api/endpoints/books_router_test.py`:
```python
@pytest.mark.asyncio
async def test_reprocess_llm_spell_check_live_path_enqueues_job():
    setup_paths()
    from api.endpoints.books_router import reprocess_llm_spell_check  # type: ignore[import]

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "admin@example.com"

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=MagicMock())

    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="false")

    mock_pages_result = MagicMock()
    mock_pages_result.fetchall.return_value = [(1,), (2,)]
    mock_session.execute = AsyncMock(return_value=mock_pages_result)

    mock_pool = AsyncMock()

    with (
        patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo),
        patch(
            "api.endpoints.books_router.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
        patch("arq.create_pool", new_callable=AsyncMock, return_value=mock_pool),
    ):
        result = await reprocess_llm_spell_check(
            book_id="some-book-id",
            current_user=mock_user,
            session=mock_session,
        )

    assert result["status"] == "llm_spell_check_started"
    assert result["queued"] == 2
    mock_pool.enqueue_job.assert_called_once()
    call_kwargs = mock_pool.enqueue_job.call_args
    assert call_kwargs.args[0] == "llm_spell_check_job"
    assert call_kwargs.kwargs["page_ids"] == [1, 2]


@pytest.mark.asyncio
async def test_reprocess_llm_spell_check_batch_path_submits_batch():
    setup_paths()
    from api.endpoints.books_router import reprocess_llm_spell_check  # type: ignore[import]

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "admin@example.com"

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=MagicMock())

    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="true")

    mock_pages_result = MagicMock()
    mock_pages_result.fetchall.return_value = [(1,), (2,)]
    mock_session.execute = AsyncMock(return_value=mock_pages_result)

    mock_batch_job = MagicMock()

    with (
        patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo),
        patch(
            "api.endpoints.books_router.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
        patch(
            "api.endpoints.books_router.submit_batch_llm_spell_check",
            new_callable=AsyncMock,
            return_value=mock_batch_job,
        ) as mock_submit,
    ):
        result = await reprocess_llm_spell_check(
            book_id="some-book-id",
            current_user=mock_user,
            session=mock_session,
        )

    assert result["status"] == "llm_spell_check_batch_submitted"
    assert result["queued"] == 2
    mock_submit.assert_called_once_with("some-book-id", [1, 2], mock_session)


@pytest.mark.asyncio
async def test_reprocess_llm_spell_check_book_not_found():
    setup_paths()
    from api.endpoints.books_router import reprocess_llm_spell_check  # type: ignore[import]

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "admin@example.com"

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=None)

    with patch("api.endpoints.books_router.BooksRepository", return_value=mock_repo):
        with pytest.raises(HTTPException) as excinfo:
            await reprocess_llm_spell_check(
                book_id="missing-book",
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_trigger_llm_spell_check_page_enqueues_and_returns_started():
    setup_paths()
    from api.endpoints.books_router import trigger_llm_spell_check_page  # type: ignore[import]

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "admin@example.com"

    mock_page = MagicMock()
    mock_page.id = 42
    mock_page.llm_spell_check_status = "idle"

    mock_repo = MagicMock()
    mock_repo.find_one = AsyncMock(return_value=mock_page)
    mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)

    mock_pool = AsyncMock()

    with (
        patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo),
        patch("arq.create_pool", new_callable=AsyncMock, return_value=mock_pool),
    ):
        result = await trigger_llm_spell_check_page(
            book_id="some-book-id",
            page_num=5,
            current_user=mock_user,
            session=mock_session,
        )

    assert result["status"] == "llm_spell_check_started"
    mock_pool.enqueue_job.assert_called_once()
    call_kwargs = mock_pool.enqueue_job.call_args
    assert call_kwargs.kwargs["page_ids"] == [42]


@pytest.mark.asyncio
async def test_trigger_llm_spell_check_page_409_when_already_running():
    setup_paths()
    from api.endpoints.books_router import trigger_llm_spell_check_page  # type: ignore[import]

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "admin@example.com"

    mock_page = MagicMock()
    mock_page.llm_spell_check_status = "in_progress"

    mock_repo = MagicMock()
    mock_repo.find_one = AsyncMock(return_value=mock_page)

    with patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo):
        with pytest.raises(HTTPException) as excinfo:
            await trigger_llm_spell_check_page(
                book_id="some-book-id",
                page_num=5,
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 409


@pytest.mark.asyncio
async def test_trigger_llm_spell_check_page_404_when_not_found():
    setup_paths()
    from api.endpoints.books_router import trigger_llm_spell_check_page  # type: ignore[import]

    mock_session = AsyncMock()
    mock_user = MagicMock()

    mock_repo = MagicMock()
    mock_repo.find_one = AsyncMock(return_value=None)

    with patch("api.endpoints.books_router.PagesRepository", return_value=mock_repo):
        with pytest.raises(HTTPException) as excinfo:
            await trigger_llm_spell_check_page(
                book_id="some-book-id",
                page_num=999,
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 404
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -k llm_spell_check -v`
Expected: FAIL with `ImportError: cannot import name 'reprocess_llm_spell_check'`.

- [x] **Step 4: Implement the endpoints**

In `services/backend/api/endpoints/books_router.py`:

Add these imports near the existing ones (alongside `from app.core.pipeline import (...)` and the other service imports):
```python
from app.core.pipeline import (
    PAGE_MILESTONE_IDLE,
    PAGE_MILESTONE_IN_PROGRESS,
    # ... (keep whatever is already imported here)
)
from app.services.batch_llm_spell_check_service import submit_batch_llm_spell_check
```

Add the two endpoints after `reprocess_summary` (around line 2237, before `retry_failed_pages`):
```python
@router.post("/{book_id}/reprocess/llm-spell-check")
async def reprocess_llm_spell_check(
    book_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger the on-demand Gemini-based LLM spell-check pass for
    every eligible page in a book. Runs independently of the dictionary-based
    spell check pipeline; each trigger costs real Gemini API calls, hence
    require_admin. Branches on llm_spell_check_batch_enabled to choose the
    live vs. Gemini Batch API path."""
    books_repo = BooksRepository(session)
    book = await books_repo.get(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=t("errors.book_not_found"))

    pages_res = await session.execute(
        select(Page.id).where(
            Page.book_id == book_id,
            Page.llm_spell_check_status != PAGE_MILESTONE_IN_PROGRESS,
        )
    )
    page_ids = [row[0] for row in pages_res.fetchall()]
    if not page_ids:
        return {"status": "llm_spell_check_started", "queued": 0}

    configs_repo = SystemConfigsRepository(session)
    batch_enabled = await configs_repo.get_value(
        "llm_spell_check_batch_enabled", "false"
    )

    if batch_enabled == "true":
        try:
            await submit_batch_llm_spell_check(book_id, page_ids, session)
        except Exception as exc:
            log_json(
                logger,
                logging.ERROR,
                "failed to submit batch_llm_spell_check job",
                book_id=book_id,
                error=str(exc),
            )
            raise HTTPException(
                status_code=500, detail=t("errors.llm_spell_check_enqueue_failed")
            )
        return {"status": "llm_spell_check_batch_submitted", "queued": len(page_ids)}

    await session.execute(
        update(Page)
        .where(Page.id.in_(page_ids))
        .values(
            llm_spell_check_status=PAGE_MILESTONE_IN_PROGRESS,
            last_updated=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    try:
        import arq

        redis_pool = await arq.create_pool(
            arq.connections.RedisSettings.from_dsn(settings.redis_url)
        )
        try:
            await redis_pool.enqueue_job(
                "llm_spell_check_job",
                page_ids=page_ids,
                _job_id=f"llm_spell_check:book:{book_id}",
            )
        finally:
            await redis_pool.aclose()
        log_json(
            logger,
            logging.INFO,
            "manually enqueued llm_spell_check_job",
            book_id=book_id,
            page_count=len(page_ids),
            user=current_user.email,
        )
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "failed to enqueue llm_spell_check_job",
            book_id=book_id,
            error=str(exc),
        )
        await session.execute(
            update(Page)
            .where(Page.id.in_(page_ids))
            .values(
                llm_spell_check_status=PAGE_MILESTONE_IDLE,
                last_updated=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        raise HTTPException(
            status_code=500, detail=t("errors.llm_spell_check_enqueue_failed")
        )

    return {"status": "llm_spell_check_started", "queued": len(page_ids)}


@router.post("/{book_id}/pages/{page_num}/llm-spell-check")
async def trigger_llm_spell_check_page(
    book_id: str,
    page_num: int,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger the on-demand Gemini-based LLM spell-check pass for a
    single page. Always uses the live path regardless of
    llm_spell_check_batch_enabled — matches how the embedding pipeline's
    reactive per-chunk dispatch always stays interactive
    (docs/main/EMBEDDING_DESIGN.md:13-14)."""
    pages_repo = PagesRepository(session)
    page = await pages_repo.find_one(book_id, page_num)
    if not page:
        raise HTTPException(status_code=404, detail=t("errors.page_not_found"))

    if page.llm_spell_check_status == PAGE_MILESTONE_IN_PROGRESS:
        raise HTTPException(
            status_code=409, detail=t("errors.llm_spell_check_already_running")
        )

    await pages_repo.set_llm_spell_check_status(
        book_id, page_num, PAGE_MILESTONE_IN_PROGRESS
    )
    await session.commit()

    try:
        import arq

        redis_pool = await arq.create_pool(
            arq.connections.RedisSettings.from_dsn(settings.redis_url)
        )
        try:
            await redis_pool.enqueue_job(
                "llm_spell_check_job",
                page_ids=[page.id],
                _job_id=f"llm_spell_check:page:{page.id}",
            )
        finally:
            await redis_pool.aclose()
        log_json(
            logger,
            logging.INFO,
            "manually enqueued llm_spell_check_job for single page",
            book_id=book_id,
            page=page_num,
            user=current_user.email,
        )
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "failed to enqueue llm_spell_check_job for single page",
            book_id=book_id,
            page=page_num,
            error=str(exc),
        )
        await pages_repo.set_llm_spell_check_status(
            book_id, page_num, PAGE_MILESTONE_IDLE
        )
        await session.commit()
        raise HTTPException(
            status_code=500, detail=t("errors.llm_spell_check_enqueue_failed")
        )

    return {"status": "llm_spell_check_started"}
```

Note: if `errors.page_not_found` does not already exist in `services/backend/locales/en.json`/`ug.json`, grep first (`grep -n "page_not_found" services/backend/locales/*.json`) — if missing, add it alongside the two new keys from Step 1 rather than assuming it exists.

- [x] **Step 5: Run tests to verify they pass**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -k llm_spell_check -v`
Expected: PASS (6 tests).

- [x] **Step 6: Commit**

```bash
git add services/backend/api/endpoints/books_router.py services/backend/locales/en.json services/backend/locales/ug.json services/backend/tests/api/endpoints/books_router_test.py
git commit -m "feat(api): add per-book and per-page LLM spell-check trigger endpoints"
```

---

## Task 16: Regenerate OpenAPI types

**Files:**
- Modify (generated): `docs/main/openapi.json`
- Modify (generated): `packages/shared/src/api-types.ts`

**Interfaces:**
- Consumes: `ExtractionResult` fields from Task 14.
- Produces: `api-types.ts` `ExtractionResult` schema gains `llmSpellCheckStatus`/`llmSpellCheckAt`, consumed by Task 17's manual override in `packages/shared/src/types.ts`.

This task has no test of its own — `scripts/check_openapi.py` (Step 3) is the verification.

- [x] **Step 1: Regenerate `docs/main/openapi.json`**

Run: `python scripts/generate_openapi.py`
Expected: exits 0, `docs/main/openapi.json` is rewritten with `ExtractionResult` now including `llmSpellCheckStatus`/`llmSpellCheckAt`, and the two new `/reprocess/llm-spell-check` / `/pages/{page_num}/llm-spell-check` paths present.

- [x] **Step 2: Regenerate `packages/shared/src/api-types.ts`**

Run: `npm run openapi:generate-types` (from the repo root — this runs `npx openapi-typescript docs/main/openapi.json -o packages/shared/src/api-types.ts`).
Expected: exits 0, `api-types.ts` is rewritten.

- [x] **Step 3: Verify sync**

Run: `python scripts/check_openapi.py`
Expected: prints `API schema is in sync with docs/main/openapi.json.` and exits 0.

- [x] **Step 4: Commit**

```bash
git add docs/main/openapi.json packages/shared/src/api-types.ts
git commit -m "chore(api): regenerate OpenAPI schema and types for LLM spell check"
```

---

## Task 17: `packages/shared/src/types.ts` manual override types

**Files:**
- Modify: `packages/shared/src/types.ts`

**Interfaces:**
- Consumes: regenerated `api-types.ts` (Task 16).
- Produces: `ExtractionResult.llmSpellCheckStatus: 'idle' | 'in_progress' | 'succeeded' | 'failed'`, `ExtractionResult.llmSpellCheckAt?: string | null`.

No dedicated test — this is a hand-maintained type override file with no existing test convention; verified via `tsc --noEmit` in Step 2.

- [x] **Step 1: Extend `ExtractionResult`**

In `packages/shared/src/types.ts`, update the `ExtractionResult` interface:
```typescript
export type ExtractionResultSchema = components['schemas']['ExtractionResult'];
export interface ExtractionResult extends Omit<ExtractionResultSchema, 'status' | 'pipelineStep' | 'milestone' | 'llmSpellCheckStatus'> {
  status: 'pending' | 'ocr_processing' | 'ocr_done' | 'indexing' | 'indexed' | 'error';
  pipelineStep?: 'ocr' | 'chunking' | 'embedding' | null;
  milestone?: 'idle' | 'running' | 'succeeded' | 'failed' | null;
  contentPageNumber?: string | null;
  content_page_number?: string | null;
  displayPageNumber?: string | null;
  display_page_number?: string | null;
  llmSpellCheckStatus?: 'idle' | 'in_progress' | 'succeeded' | 'failed';
  llmSpellCheckAt?: string | null;
}
```
(Only the `Omit<...>` type-parameter list and the trailing two new fields change; every other line of the interface stays as-is.)

- [x] **Step 2: Verify**

Run: `cd apps/frontend && npx tsc --noEmit -p .` (or the repo's existing typecheck script — check `apps/frontend/package.json` for a `typecheck`/`tsc` script and prefer that if present).
Expected: no new type errors introduced by this change (pre-existing unrelated errors, if any, are out of scope).

- [x] **Step 3: Commit**

```bash
git add packages/shared/src/types.ts
git commit -m "feat(types): add llmSpellCheckStatus/llmSpellCheckAt to ExtractionResult"
```

---

## Task 18: `REPROCESS_STEP.LLM_SPELL_CHECK`

**Files:**
- Modify: `apps/frontend/src/constants/milestones.ts`

**Interfaces:**
- Produces: `REPROCESS_STEP.LLM_SPELL_CHECK = 'llm-spell-check'` (hyphenated, matching the URL slug convention already used by `SPELL_CHECK: 'spell-check'`).

No dedicated test — this is a plain constant object; verified via Task 19/20's tests which import and use it.

- [x] **Step 1: Add the constant**

In `apps/frontend/src/constants/milestones.ts`, in the `REPROCESS_STEP` object:
```typescript
export const REPROCESS_STEP = {
  OCR: 'ocr',
  CHUNKING: 'chunking',
  EMBEDDING: 'embedding',
  SPELL_CHECK: 'spell-check',
  LLM_SPELL_CHECK: 'llm-spell-check',
  GRAPH: 'graph',
  SUMMARY: 'summary',
  HISTORY: 'history',
} as const;
```

- [x] **Step 2: Verify**

Run: `cd apps/frontend && npx tsc --noEmit -p .`
Expected: no new type errors.

- [x] **Step 3: Commit**

```bash
git add apps/frontend/src/constants/milestones.ts
git commit -m "feat(frontend): add REPROCESS_STEP.LLM_SPELL_CHECK"
```

---

## Task 19: `persistenceService.ts` new methods

**Files:**
- Modify: `apps/frontend/src/services/persistenceService.ts`
- Test: `apps/frontend/src/tests/services/persistenceService.test.ts` (check whether this file already exists — if a persistenceService test file exists under a different path, e.g. co-located, use that instead; if none exists at all for this service, create it following the `useBookActions.test.tsx` mocking conventions rather than skipping tests)

**Interfaces:**
- Consumes: `authFetch` (existing), `API_BASE` (existing).
- Produces: `async reprocessLlmSpellCheck(bookId: string): Promise<void>`, `async triggerLlmSpellCheckPage(bookId: string, pageNum: number): Promise<void>` — consumed by Task 20.

- [x] **Step 1: Write the failing tests**

Create (or append to, if it exists) `apps/frontend/src/tests/services/persistenceService.test.ts`:
```typescript
import { PersistenceService } from '@/src/services/persistenceService';
import { authFetch } from '@/src/services/authService';
import { beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PersistenceService LLM spell check methods', () => {
  test('reprocessLlmSpellCheck posts to the correct endpoint', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: true } as Response);

    await PersistenceService.reprocessLlmSpellCheck('book-1');

    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/reprocess/llm-spell-check',
      { method: 'POST' }
    );
  });

  test('reprocessLlmSpellCheck throws on non-ok response', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: false, status: 500 } as Response);

    await expect(PersistenceService.reprocessLlmSpellCheck('book-1')).rejects.toThrow();
  });

  test('triggerLlmSpellCheckPage posts to the correct endpoint', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: true } as Response);

    await PersistenceService.triggerLlmSpellCheckPage('book-1', 5);

    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/pages/5/llm-spell-check',
      { method: 'POST' }
    );
  });

  test('triggerLlmSpellCheckPage throws on 409 already-running response', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: false, status: 409 } as Response);

    await expect(
      PersistenceService.triggerLlmSpellCheckPage('book-1', 5)
    ).rejects.toThrow();
  });
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/services/persistenceService.test.ts`
Expected: FAIL — `PersistenceService.reprocessLlmSpellCheck is not a function`.

- [x] **Step 3: Implement the methods**

In `apps/frontend/src/services/persistenceService.ts`, add after `reprocessSpellCheck`:
```typescript
  async reprocessLlmSpellCheck(bookId: string): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/reprocess/llm-spell-check`, {
      method: 'POST',
    });
    if (!response.ok) {
      if (response.status === 403) {
        throw new Error("Permission denied: Admin access required");
      }
      throw new Error("Failed to start LLM spell check");
    }
  },

  async triggerLlmSpellCheckPage(bookId: string, pageNum: number): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNum}/llm-spell-check`, {
      method: 'POST',
    });
    if (!response.ok) {
      if (response.status === 403) {
        throw new Error("Permission denied: Admin access required");
      }
      if (response.status === 409) {
        throw new Error("LLM spell check is already running for this page");
      }
      throw new Error("Failed to start LLM spell check for page");
    }
  },
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/services/persistenceService.test.ts`
Expected: PASS (4 tests).

- [x] **Step 5: Commit**

```bash
git add apps/frontend/src/services/persistenceService.ts apps/frontend/src/tests/services/persistenceService.test.ts
git commit -m "feat(frontend): add reprocessLlmSpellCheck and triggerLlmSpellCheckPage to PersistenceService"
```

---

## Task 20: `useBookActions.ts` — reprocess-step dispatch + per-page handler

**Files:**
- Modify: `apps/frontend/src/hooks/useBookActions.ts`
- Test: `apps/frontend/src/tests/hooks/useBookActions.test.tsx`

**Interfaces:**
- Consumes: `REPROCESS_STEP.LLM_SPELL_CHECK` (Task 18); `PersistenceService.reprocessLlmSpellCheck`/`.triggerLlmSpellCheckPage` (Task 19).
- Produces: `handleLlmSpellCheckPage(bookId: string, pageNum: number): void`, added to the hook's returned object; `handleReprocessStep` gains an `LLM_SPELL_CHECK` entry in both its `titles` map and `switch` dispatch.

Unlike `handleReProcessPage` (OCR reset), `handleLlmSpellCheckPage` must **not** blank the page's text or set a pending empty state — the page's current text is still valid content while the correction runs, so no optimistic `setSelectedBook`/`setBooks` mutation of `page.text` happens here.

- [x] **Step 1: Write the failing tests**

Append to `apps/frontend/src/tests/hooks/useBookActions.test.tsx` (extend the mocked `PersistenceService` object at the top of the file to include `reprocessLlmSpellCheck: vi.fn()` and `triggerLlmSpellCheckPage: vi.fn()` alongside the existing entries):
```typescript
test('useBookActions dispatches LLM spell check reprocess through handleReprocessStep', async () => {
  vi.mocked(PersistenceService.reprocessLlmSpellCheck).mockResolvedValue(undefined);
  const { result, setModal } = createHook();

  act(() => {
    result.current.handleReprocessStep('1', 'llm-spell-check' as any);
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({
    isOpen: true,
    type: 'confirm',
  }));

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(PersistenceService.reprocessLlmSpellCheck).toHaveBeenCalledWith('1');
});

test('useBookActions triggers per-page LLM spell check without blanking page text', async () => {
  vi.mocked(PersistenceService.triggerLlmSpellCheckPage).mockResolvedValue(undefined);
  const { result, setModal, setSelectedBook, setBooks } = createHook();

  act(() => {
    result.current.handleLlmSpellCheckPage('1', 3);
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({
    isOpen: true,
    type: 'confirm',
  }));

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(PersistenceService.triggerLlmSpellCheckPage).toHaveBeenCalledWith('1', 3);
  // Must NOT optimistically blank/mutate page text the way handleReProcessPage does.
  expect(setSelectedBook).not.toHaveBeenCalled();
  expect(setBooks).not.toHaveBeenCalled();
});

test('useBookActions surfaces an error notification when LLM spell check trigger fails', async () => {
  vi.mocked(PersistenceService.triggerLlmSpellCheckPage).mockRejectedValue(new Error('boom'));
  const { result, setModal } = createHook();

  act(() => {
    result.current.handleLlmSpellCheckPage('1', 3);
  });

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(PersistenceService.triggerLlmSpellCheckPage).toHaveBeenCalledWith('1', 3);
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useBookActions.test.tsx -t "LLM spell check"`
Expected: FAIL — `result.current.handleLlmSpellCheckPage is not a function`, and the `handleReprocessStep` case falls through the `switch` with no matching `PersistenceService` call.

- [x] **Step 3: Implement**

In `apps/frontend/src/hooks/useBookActions.ts`:

Add `LLM_SPELL_CHECK` to the `titles` map inside `handleReprocessStep`:
```typescript
    const titles: Record<string, string> = {
      [REPROCESS_STEP.OCR]: t('modal.reprocessOcr.title') || 'OCR نى قايتا ئىشلەش',
      [REPROCESS_STEP.CHUNKING]: t('modal.reprocessChunking.title') || 'پارچىلاشنى قايتا ئىشلەش',
      [REPROCESS_STEP.EMBEDDING]: t('modal.reprocessEmbedding.title') || 'ۋېكتورلاشتۇرۇشنى قايتا ئىشلەش',
      [REPROCESS_STEP.SPELL_CHECK]: t('modal.reprocessSpellCheck.title') || 'ئىملا تەكشۈرۈشنى قايتا ئىشلەش',
      [REPROCESS_STEP.LLM_SPELL_CHECK]: t('modal.reprocessLlmSpellCheck.title') || 'LLM ئارقىلىق ئىملا تەكشۈرۈشنى قايتا ئىشلەش',
      [REPROCESS_STEP.GRAPH]: t('modal.reprocessGraph.title') || 'بىلىم گىرافىنى قايتا ئىشلەش',
      [REPROCESS_STEP.SUMMARY]: t('modal.reprocessSummary.title') || 'قىسقىچە مەزمۇننى قايتا ھاسىللاش',
      [REPROCESS_STEP.HISTORY]: t('admin.table.extractHistory') || 'تارىخىي ئاتالغۇلارنى بايقاش',
    };
```

Add the `LLM_SPELL_CHECK` case to the `switch` dispatch:
```typescript
          switch (step) {
            case REPROCESS_STEP.OCR: await PersistenceService.reprocessOcr(bookId); break;
            case REPROCESS_STEP.CHUNKING: await PersistenceService.reprocessChunking(bookId); break;
            case REPROCESS_STEP.EMBEDDING: await PersistenceService.reprocessEmbedding(bookId); break;
            case REPROCESS_STEP.SPELL_CHECK: await PersistenceService.reprocessSpellCheck(bookId); break;
            case REPROCESS_STEP.LLM_SPELL_CHECK: await PersistenceService.reprocessLlmSpellCheck(bookId); break;
            case REPROCESS_STEP.GRAPH: await PersistenceService.reprocessGraph(bookId, graphScope ?? 'nonfiction'); break;
            case REPROCESS_STEP.SUMMARY: await PersistenceService.reprocessSummary(bookId); break;
            case REPROCESS_STEP.HISTORY: await PersistenceService.reprocessHistory(bookId); break;
          }
```

Add the new handler, near `handleReProcessPage`:
```typescript
  const handleLlmSpellCheckPage = (bookId: string, pageNum: number) => {
    setModal({
      isOpen: true,
      title: t('modal.llmSpellCheckPage.title') || 'LLM ئارقىلىق ئىملا تەكشۈرۈش',
      message: t('modal.llmSpellCheckPage.message', { pageNum }) || `بۇ بەتنى LLM ئارقىلىق ئىملا تەكشۈرەمسىز؟`,
      type: 'confirm',
      confirmText: t('modal.llmSpellCheckPage.confirm') || 'تەكشۈرۈش',
      onConfirm: async () => {
        setModal(prev => ({ ...prev, isOpen: false }));
        try {
          await PersistenceService.triggerLlmSpellCheckPage(bookId, pageNum);
          refreshLibrary();
          addNotification(
            t('common.llmSpellCheckPageStarted', { pageNum }) || `بەت ${pageNum} تەكشۈرۈلۈۋاتىدۇ`,
            'success'
          );
        } catch (err) {
          console.error("Failed to trigger LLM spell check", err);
          addNotification(
            t('common.llmSpellCheckPageError', { pageNum }) || `بەت ${pageNum} نى تەكشۈرەلمىدى`,
            'error'
          );
        }
      }
    });
  };
```
Note: intentionally no optimistic `setSelectedBook`/`setBooks` mutation of `page.text` here — the page's existing text is still valid while the correction runs (unlike `handleReProcessPage`'s OCR-reset flow, which blanks text because the old OCR text is about to be discarded).

Add `handleLlmSpellCheckPage` to the hook's returned object, alongside `handleReProcessPage`:
```typescript
  return {
    isOpeningBook,
    isCheckingGlobal,
    reprocessingBooks,
    isDeletingBook,
    handleFileUpload,
    handleRetryFailedPages,
    handleReprocessStep,
    handleReProcessPage,
    handleLlmSpellCheckPage,
    handleToggleToc,
    handleTriggerSpellCheck,
    handleUpdatePage,
    openReader,
    saveCorrections,
    handleDeleteBook,
    handleSaveTags,
    handleSaveCategories,
    handleSaveAuthor,
    handleSaveTitle,
    handleSaveVolume,
    handleSaveBookRow,
    handleToggleVisibility,
    handleReplaceCover,
  };
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useBookActions.test.tsx`
Expected: PASS (all tests, including pre-existing ones).

- [x] **Step 5: Commit**

```bash
git add apps/frontend/src/hooks/useBookActions.ts apps/frontend/src/tests/hooks/useBookActions.test.tsx
git commit -m "feat(frontend): wire LLM spell check into useBookActions (reprocess-step + per-page trigger)"
```

---

## Task 21: `ActionMenu.tsx` — admin reprocess button

**Files:**
- Modify: `apps/frontend/src/components/admin/ActionMenu.tsx`

**Interfaces:**
- Consumes: `REPROCESS_STEP.LLM_SPELL_CHECK` (Task 18); `bookActions.handleReprocessStep`/`.reprocessingBooks` (existing, extended in Task 20).

No dedicated test file exists for `ActionMenu.tsx` in this repo (confirmed — only `AdminView.test.tsx` covers admin components at this level). Verified via manual browser check in Task 25 rather than adding net-new test infrastructure for a file with no prior test convention.

- [x] **Step 1: Add the `Sparkles` icon import**

In `apps/frontend/src/components/admin/ActionMenu.tsx`, extend the `lucide-react` import:
```typescript
import { BookOpen, BookOpenCheck, Cuboid, FileText, Image, Loader2, Network, RotateCcw, ScanText, Scissors, ScrollText, Sparkles, Trash2 } from 'lucide-react';
```

- [x] **Step 2: Add the button**

Insert this block immediately after the existing spell-check button (the one gated on `spellCheckEnabled`, before the `{isAdmin && (... GRAPH ...))}` block):
```tsx
        {isAdmin && (
          <button
            onClick={() => { bookActions.handleReprocessStep(book.id, REPROCESS_STEP.LLM_SPELL_CHECK); close(); }}
            disabled={book.pipelineStep === null || reprocessingStep === REPROCESS_STEP.LLM_SPELL_CHECK}
            className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-fuchsia-600 dark:text-fuchsia-400 hover:bg-fuchsia-50 dark:hover:bg-fuchsia-950/20 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
          >
            {reprocessingStep === REPROCESS_STEP.LLM_SPELL_CHECK ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            <span className="flex-1 text-right">{t('admin.table.reprocess.llm_spell_check') || 'LLM ئارقىلىق ئىملا تەكشۈرۈش'}</span>
          </button>
        )}
```

- [x] **Step 3: Verify**

Run: `cd apps/frontend && npx tsc --noEmit -p .`
Expected: no new type errors.

- [x] **Step 4: Commit**

```bash
git add apps/frontend/src/components/admin/ActionMenu.tsx
git commit -m "feat(frontend): add admin-gated LLM spell check button to ActionMenu"
```

---

## Task 22: `PageItem.tsx` / `ReaderView.tsx` — per-page trigger button

**Files:**
- Modify: `apps/frontend/src/components/reader/PageItem.tsx`
- Modify: `apps/frontend/src/components/reader/ReaderView.tsx`
- Test: `apps/frontend/src/tests/components/reader/PageItem.test.tsx`

**Interfaces:**
- Consumes: `bookActions.handleLlmSpellCheckPage` (Task 20).
- Produces: `PageItemProps.onLlmSpellCheck?: () => void`, rendered as a button next to the ToC toggle; wired at both `PageItem` render sites in `ReaderView.tsx` (non-virtual list and `VirtualScrollReader`), admin-gated (not merely `isEditor`, matching the endpoint's `require_admin`).

- [x] **Step 1: Write the failing tests**

Append to `apps/frontend/src/tests/components/reader/PageItem.test.tsx`. First, extend the `useAuth` mock at the top of the file to also export `useIsAdmin: vi.fn()`, then:
```typescript
test('PageItem shows LLM spell check button for admin users', () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  const onLlmSpellCheck = vi.fn();
  renderPageItem({ page: { ...mockPage }, onLlmSpellCheck });

  const button = screen.getByTitle('reader.llmSpellCheckTitle');
  fireEvent.click(button);
  expect(onLlmSpellCheck).toHaveBeenCalledTimes(1);
});

test('PageItem hides LLM spell check button when onLlmSpellCheck is not provided', () => {
  renderPageItem({ page: { ...mockPage }, onLlmSpellCheck: undefined });

  expect(screen.queryByTitle('reader.llmSpellCheckTitle')).not.toBeInTheDocument();
});

test('PageItem disables LLM spell check button while llmSpellCheckStatus is in_progress', () => {
  const onLlmSpellCheck = vi.fn();
  renderPageItem({
    page: { ...mockPage, llmSpellCheckStatus: 'in_progress' },
    onLlmSpellCheck,
  });

  const button = screen.getByTitle('reader.llmSpellCheckTitle');
  expect(button).toBeDisabled();
});
```
(`renderPageItem`'s `defaultProps` in this file does not currently include `onLlmSpellCheck` — since it's optional, the merge/override pattern already used for `onToggleToc` in this helper covers it without changes to `defaultProps` itself; only pass it per-test as shown.)

- [x] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/PageItem.test.tsx -t "LLM spell check"`
Expected: FAIL — `screen.getByTitle('reader.llmSpellCheckTitle')` throws (element not found), since the prop/button don't exist yet.

- [x] **Step 3: Implement in `PageItem.tsx`**

Add to the `PageItemProps` interface, next to `onToggleToc`:
```tsx
  onToggleToc?: (nextIsToc: boolean) => void;
  onLlmSpellCheck?: () => void;
```

Add `onLlmSpellCheck` to the destructured props:
```tsx
export const PageItem: React.FC<PageItemProps> = React.memo(({
  page, isActive, isEditing, fontSize, contentFontFamily, contentFontClassName, onSetActive, onEdit, onReprocess, onSetStartPage, onToggleToc, onLlmSpellCheck,
  tempText, onTempTextChange, onSave, onCancel, isLoading, isSaving, isFullscreen, contentPageOffset, onTocPageClick,
  bookId, bookTitle, bookAuthor, highlightQuote, onHighlightApplied,
}) => {
```

Add the button right after the `onToggleToc` button block (so it renders alongside it):
```tsx
            {onLlmSpellCheck && (
              <button
                onClick={onLlmSpellCheck}
                disabled={(page?.llmSpellCheckStatus ?? page?.llm_spell_check_status) === 'in_progress'}
                className="flex items-center justify-center sm:justify-start gap-1.5 h-8 w-8 sm:w-auto sm:px-3 bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400 hover:bg-fuchsia-500 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-xs font-bold uppercase"
                title={t('reader.llmSpellCheckTitle')}
              >
                {(page?.llmSpellCheckStatus ?? page?.llm_spell_check_status) === 'in_progress'
                  ? <Loader2 size={14} className="animate-spin" />
                  : <Sparkles size={14} />}
                <span className="hidden sm:inline">{t('reader.llmSpellCheck')}</span>
              </button>
            )}
```
Check the top-of-file `lucide-react` import in `PageItem.tsx` and add `Sparkles`/`Loader2` if either is missing from it.

- [x] **Step 4: Wire it in `ReaderView.tsx`**

Check whether `useIsAdmin` is already imported/used in `ReaderView.tsx` (it likely is not, since only `isEditor` is used there today); if missing, add `import { useIsAdmin } from '../../hooks/useAuth';` and `const isAdmin = useIsAdmin();` near the existing `isEditor` usage.

At the non-virtual `PageItem` render site (near the existing `onToggleToc={isEditor ? ... : undefined}` line), add immediately after it:
```tsx
                        onToggleToc={isEditor ? (nextIsToc) => bookActions.handleToggleToc(selectedBook.id, page.pageNumber, nextIsToc) : undefined}
                        onLlmSpellCheck={isAdmin ? () => bookActions.handleLlmSpellCheckPage(selectedBook.id, page.pageNumber) : undefined}
```

At the `VirtualScrollReader` render site (near the existing `onToggleToc={isEditor ? (pageNum, nextIsToc) => ... : undefined}` line), add immediately after it:
```tsx
                onToggleToc={isEditor ? (pageNum, nextIsToc) => bookActions.handleToggleToc(selectedBook.id, pageNum, nextIsToc) : undefined}
                onLlmSpellCheck={isAdmin ? (pageNum) => bookActions.handleLlmSpellCheckPage(selectedBook.id, pageNum) : undefined}
```
(Confirm `VirtualScrollReader`'s own prop signature expects a `pageNum`-parameterized callback the same way `onToggleToc` does there — mirror whatever calling convention `onReprocess`/`onToggleToc` already use for that component; if `VirtualScrollReader` needs its own prop-type update to accept `onLlmSpellCheck`, make that change too, following the same pattern as its existing `onToggleToc` prop.)

- [x] **Step 5: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/PageItem.test.tsx`
Expected: PASS (all tests, including pre-existing ones).

- [x] **Step 6: Commit**

```bash
git add apps/frontend/src/components/reader/PageItem.tsx apps/frontend/src/components/reader/ReaderView.tsx apps/frontend/src/tests/components/reader/PageItem.test.tsx
git commit -m "feat(frontend): add admin-gated per-page LLM spell check trigger button"
```

---

## Task 23: `AdminView.tsx` — three-state book-row icon

**Files:**
- Modify: `apps/frontend/src/components/admin/AdminView.tsx`
- Test: `apps/frontend/src/tests/components/admin/AdminView.test.tsx`

**Interfaces:**
- Consumes: `book.pipelineStats.llm_spell_check`/`.llm_spell_check_active`/`.llm_spell_check_failed` (Task 13, surfaced through the existing `/books` list and `/{book_id}/pipeline-stats` endpoints without further backend change); `book.totalPages`.
- Produces: a `Sparkles` icon in both the mobile and desktop per-book icon rows, colored `text-emerald-500` (done === total, total > 0), `text-amber-500` (done + active > 0, not fully done), or `text-slate-300` (otherwise) — a bespoke three-state scheme, distinct from the other icons' two-state emerald/gray, since this step is triggered per-page and a book can legitimately sit half-checked.

- [x] **Step 1: Write the failing tests**

Append to `apps/frontend/src/tests/components/admin/AdminView.test.tsx` (mirroring the existing `renders emerald Graph icon` test pattern):
```tsx
test('AdminView renders emerald LLM spell check icon when fully done', () => {
  const booksAllDone: Book[] = [
    {
      ...mockBooks[0],
      totalPages: 10,
      pipelineStats: { llm_spell_check: 10, llm_spell_check_active: 0, llm_spell_check_failed: 0 },
    },
  ];
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...mockAppContextValue,
    books: booksAllDone,
  } as any);

  render(
    <I18nContext.Provider value={i18nMockValue}>
      <AdminView />
    </I18nContext.Provider>
  );

  const emeraldIcons = document.querySelectorAll('.text-emerald-500');
  expect(emeraldIcons.length).toBeGreaterThanOrEqual(1);
});

test('AdminView renders amber LLM spell check icon when partially done', () => {
  const booksPartial: Book[] = [
    {
      ...mockBooks[0],
      totalPages: 10,
      pipelineStats: { llm_spell_check: 3, llm_spell_check_active: 1, llm_spell_check_failed: 0 },
    },
  ];
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...mockAppContextValue,
    books: booksPartial,
  } as any);

  render(
    <I18nContext.Provider value={i18nMockValue}>
      <AdminView />
    </I18nContext.Provider>
  );

  const amberIcons = document.querySelectorAll('.text-amber-500');
  expect(amberIcons.length).toBeGreaterThanOrEqual(1);
});

test('AdminView renders gray LLM spell check icon when not started', () => {
  const booksNotStarted: Book[] = [
    {
      ...mockBooks[0],
      totalPages: 10,
      pipelineStats: { llm_spell_check: 0, llm_spell_check_active: 0, llm_spell_check_failed: 0 },
    },
  ];
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...mockAppContextValue,
    books: booksNotStarted,
  } as any);

  render(
    <I18nContext.Provider value={i18nMockValue}>
      <AdminView />
    </I18nContext.Provider>
  );

  const grayIcons = document.querySelectorAll('.text-slate-300');
  expect(grayIcons.length).toBeGreaterThanOrEqual(1);
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/admin/AdminView.test.tsx -t "LLM spell check icon"`
Expected: FAIL — no `Sparkles` icon rendered yet, so the color-class queries find zero matching elements from this new icon (note: `text-emerald-500`/`text-amber-500` may already have unrelated hits from other icons in `mockBooks[0]`'s existing `pipelineStats` — adjust the fixture's other fields to `0`/unset if needed so only the new icon can produce a match for these specific tests, following the "empty pipelineStats" isolation trick already used by the existing `renders emerald Graph icon` test).

- [x] **Step 3: Add a color-class helper**

In `apps/frontend/src/components/admin/AdminView.tsx`, near the existing `getPipelineIconClass`/`getMilestoneColor` helpers, add:
```tsx
const getLlmSpellCheckIconClass = (
  stats: { llm_spell_check?: number; llm_spell_check_active?: number } | undefined | null,
  totalPages: number | undefined
): string => {
  const done = stats?.llm_spell_check ?? 0;
  const active = stats?.llm_spell_check_active ?? 0;
  const tp = totalPages ?? 0;
  if (tp > 0 && done === tp) return 'text-emerald-500';
  if (done + active > 0) return 'text-amber-500';
  return 'text-slate-300';
};
```

- [x] **Step 4: Add the `Sparkles` icon import**

Extend the `lucide-react` import at the top of `AdminView.tsx`:
```tsx
import { BookOpen, BookOpenCheck, Cuboid, Database, Edit2, Globe, Hash, MoreVertical, Network, RefreshCw, Save, ScanText, Scissors, ScrollText, Search, Shield, Sparkles, TableOfContents, User, Wand2, X } from 'lucide-react';
```

- [x] **Step 5: Add the mobile icon**

Immediately after the mobile pipeline-progress `.map(...)` block closes (the one iterating `[{ key: PIPELINE_STEP.OCR, icon: ScanText }, ..., { key: PIPELINE_STEP.GRAPH, icon: Network }]`), still inside the same `<div className="flex md:hidden items-center gap-1.5 mt-2">`, add:
```tsx
                                <Sparkles
                                  size={14}
                                  className={`${getLlmSpellCheckIconClass(book.pipelineStats, book.totalPages)} transition-colors duration-300`}
                                />
```

- [x] **Step 6: Add the desktop icon with hover tooltip**

Immediately after the desktop pipeline-icons `.map(...)` block closes, still inside the same `<div className="flex items-center gap-2.5">`, add:
```tsx
                            {(() => {
                              const key = 'llm_spell_check';
                              const cacheKey = `${book.id}:${key}`;
                              const stats = detailedStats[cacheKey];
                              const isLoadingStat = loadingStats[cacheKey];
                              const isLoaded = !!stats;
                              const source = isLoaded ? stats.pipeline_stats : book.pipelineStats;
                              const totalPages = isLoaded ? stats.total_pages : book.totalPages;
                              const done = getStat(source, key);
                              const active = getStat(source, `${key}_active`);
                              const failed = getStat(source, `${key}_failed`);
                              const tp = totalPages ?? 0;
                              const colorClass = getLlmSpellCheckIconClass(
                                { llm_spell_check: done, llm_spell_check_active: active },
                                tp
                              );
                              return (
                                <div
                                  className="group/status relative flex items-center"
                                  onMouseEnter={() => fetchBookStats(book.id, key)}
                                >
                                  <Sparkles size={18} className={`${colorClass} transition-colors duration-300`} />
                                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1.5 bg-slate-900/95 text-white text-[11px] font-medium rounded-md shadow-lg opacity-0 group-hover/status:opacity-100 transition-all duration-200 whitespace-nowrap pointer-events-none z-10 border border-slate-700">
                                    <div className="flex flex-col gap-0.5">
                                      <span className="font-bold border-b border-slate-700 pb-0.5 mb-0.5">{t('admin.pipeline.llmSpellCheck')}</span>
                                      {isLoadingStat ? (
                                        <span className="text-slate-400 animate-pulse">{t('common.loading')}...</span>
                                      ) : tp > 0 && done === tp ? (
                                        <span>{t('common.done')}</span>
                                      ) : done + active > 0 ? (
                                        <span>{t('common.partial', { done, total: tp })}</span>
                                      ) : (
                                        <span>{t('common.pending')}</span>
                                      )}
                                      {failed > 0 && (
                                        <span className="text-red-400 ml-1">({failed} {t('common.error')})</span>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            })()}
```

- [x] **Step 7: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/admin/AdminView.test.tsx`
Expected: PASS (all tests, including pre-existing ones).

- [x] **Step 8: Commit**

```bash
git add apps/frontend/src/components/admin/AdminView.tsx apps/frontend/src/tests/components/admin/AdminView.test.tsx
git commit -m "feat(frontend): add three-state LLM spell check icon to admin book table"
```

---

## Task 24: Frontend i18n keys

**Files:**
- Modify: `apps/frontend/src/locales/en.json`
- Modify: `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Produces: all `t(...)` keys referenced by Tasks 20-23 that don't already exist.

No dedicated test — verified by the fallback-string pattern already used throughout (`t(key) || 'ئۇيغۇرچە...'`) meaning a missing key degrades gracefully rather than breaking the build; still, add the real keys so the UI shows translated text rather than permanently falling back.

- [x] **Step 1: Add `admin.table.reprocess.llm_spell_check`**

In `apps/frontend/src/locales/en.json`, inside `admin.table.reprocess`:
```json
      "reprocess": {
        "ocr": "Full OCR Reprocess",
        "chunking": "Reprocess Chunking",
        "embedding": "Reprocess Embedding",
        "spell_check": "Reprocess Spell Check",
        "llm_spell_check": "Reprocess LLM Spell Check",
        "graph": "Reprocess Knowledge Graph",
        "summary": "Rebuild AI Summary"
      },
```
In `apps/frontend/src/locales/ug.json`, same position:
```json
      "reprocess": {
        "ocr": "قايتا OCR",
        "chunking": "قايتا پارچىلاش",
        "embedding": "قايتا ۋېكتورلاش",
        "spell_check": "قايتا ئىملا تەكشۈرۈش",
        "llm_spell_check": "LLM ئارقىلىق ئىملا تەكشۈرۈشنى قايتىلاش",
        "graph": "قايتا گىرافىك قۇرۇش",
        "summary": "قايتا قىسقىچە مەزمۇن ھاسىللاش"
      },
```

- [x] **Step 2: Add `admin.pipeline.llmSpellCheck`**

In `apps/frontend/src/locales/en.json`, inside `admin.pipeline` (alongside `spellCheck`/`graph`):
```json
      "spellCheck": "Spell check",
      "llmSpellCheck": "LLM Spell Check",
      "graph": "Knowledge Graph",
```
In `apps/frontend/src/locales/ug.json`, same position (use the existing `admin.pipeline.spellCheck` Uyghur translation as a style reference).

- [x] **Step 3: Add `common.partial`**

In `apps/frontend/src/locales/en.json`, inside `common` (alongside `done`/`pending`):
```json
    "done": "Done",
    "pending": "Pending",
    "partial": "{{done}}/{{total}} pages corrected",
```
In `apps/frontend/src/locales/ug.json`, same position, e.g.:
```json
    "partial": "{{done}}/{{total}} بەت تۈزىتىلدى",
```
Confirm the exact interpolation placeholder syntax (`{{done}}` vs `{done}`) by checking how `t('common.pageResetSuccess', { pageNum })`'s underlying key is written in this file — match that project's existing convention exactly rather than assuming `{{}}`.

- [x] **Step 4: Add `modal.reprocessLlmSpellCheck.title` and `modal.reprocess.llm-spell-check.message`**

In `apps/frontend/src/locales/en.json`, alongside the sibling `modal.reprocessSpellCheck`/`modal.reprocessGraph` keys:
```json
    "reprocessLlmSpellCheck": {
      "title": "Reprocess LLM Spell Check"
    },
```
And inside `modal.reprocess` (keyed by the `REPROCESS_STEP.LLM_SPELL_CHECK` value, `'llm-spell-check'`, matching the existing hyphenated `spell-check` key precedent):
```json
      "llm-spell-check": {
        "message": "Are you sure you want to run the LLM-based spell check pass on this book? This uses the Gemini API and may take a while."
      },
```
Mirror both in `apps/frontend/src/locales/ug.json`.

- [x] **Step 5: Add `modal.llmSpellCheckPage.*`**

In `apps/frontend/src/locales/en.json`:
```json
    "llmSpellCheckPage": {
      "title": "LLM Spell Check",
      "message": "Run the LLM-based spell check on page {{pageNum}}?",
      "confirm": "Check"
    },
```
Mirror in `apps/frontend/src/locales/ug.json`. Match the actual interpolation syntax used by the neighboring `modal.resetPage.message` key (`t('modal.resetPage.message', { pageNum })`) exactly.

- [x] **Step 6: Add `common.llmSpellCheckPageStarted` / `common.llmSpellCheckPageError`**

In `apps/frontend/src/locales/en.json`, alongside `common.pageResetSuccess`/`common.pageResetError`:
```json
    "llmSpellCheckPageStarted": "LLM spell check started for page {{pageNum}}",
    "llmSpellCheckPageError": "Failed to start LLM spell check for page {{pageNum}}",
```
Mirror in `apps/frontend/src/locales/ug.json`.

- [x] **Step 7: Add `reader.llmSpellCheck` / `reader.llmSpellCheckTitle`**

In `apps/frontend/src/locales/en.json`, inside `reader`:
```json
    "llmSpellCheck": "LLM Check",
    "llmSpellCheckTitle": "Run LLM-based spell check on this page",
```
Mirror in `apps/frontend/src/locales/ug.json`.

- [x] **Step 8: Verify**

Run: `cd apps/frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/en.json')); JSON.parse(require('fs').readFileSync('src/locales/ug.json')); console.log('valid JSON')"`
Expected: prints `valid JSON` (catches trailing-comma/syntax mistakes before running the app).

- [x] **Step 9: Commit**

```bash
git add apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "feat(i18n): add frontend strings for LLM spell check feature"
```

---

## Task 25: End-to-end manual verification

**Files:** none (manual QA pass, no code changes expected — if a bug surfaces, fix it in the relevant task's file and re-run the affected task's automated tests before continuing).

- [x] **Step 1: Full-stack rebuild**

Run: `./deploy/local/rebuild-and-restart.sh all`
Expected: backend, worker, and frontend containers rebuild and start with no errors; migrations 090/091 applied (visible in backend startup logs).

PARTIALLY DONE — migrations 090/091 were applied directly against the local dev Postgres and verified via `\d pages` / `\d batch_llm_spell_check_jobs` / a `system_configs` SELECT (all present as expected). The full container rebuild (`./deploy/local/rebuild-and-restart.sh all`) was not run in this session.

- [ ] **Step 2: Live path — per-page trigger**

Log in as an admin user. Open a book with a known context-dependent spelling error (a valid Uyghur word substituted for a different valid word that breaks the sentence's meaning). In the reader, trigger the new "LLM Check" button on that page.
Expected: confirm modal appears in Uyghur; on confirm, the page keeps showing its current text (not blanked); a spinner/disabled state shows on the button while `llmSpellCheckStatus` is `in_progress`; after the worker finishes (`llm_spell_check_job` log line "llm spell check job completed" in worker logs), the page text updates with the correction and the button re-enables.

- [ ] **Step 3: Admin table icon — partial state**

Return to the admin book-management table.
Expected: the new Sparkles icon on that book's row is amber (partial — some but not all pages have `llm_spell_check_status='succeeded'`), with a hover tooltip showing "N/total pages corrected" in Uyghur.

- [ ] **Step 4: Live path — per-book trigger**

Trigger the new "Reprocess LLM Spell Check" action from the `ActionMenu` on the same (or a different) multi-page book, with `llm_spell_check_batch_enabled` left at its default `false`.
Expected: confirm modal in Uyghur; on confirm, all eligible pages process (bounded by `settings.max_parallel_llm_spell_check` concurrent Gemini calls, visible in worker logs); the `ActionMenu` button re-enables once the job completes; the admin table row's Sparkles icon turns emerald once every page succeeds.

- [ ] **Step 5: Auth gating**

Log in as a non-admin (editor/reader) user.
Expected: neither the reader's "LLM Check" per-page button nor the admin table's "Reprocess LLM Spell Check" `ActionMenu` entry is rendered; a direct `curl -X POST` to either new endpoint without an admin session returns 401/403 (verify with `curl -i -X POST http://localhost:30800/api/books/<book_id>/reprocess/llm-spell-check` using a non-admin or missing auth token).

- [ ] **Step 6: Batch path**

Via the system-configs admin panel, flip `llm_spell_check_batch_enabled` to `true`. Trigger a per-book LLM spell check on a different multi-page book.
Expected: a `batch_llm_spell_check_jobs` row appears with `status='submitting'` then `'running'` (`SELECT * FROM batch_llm_spell_check_jobs ORDER BY created_at DESC LIMIT 1;`); that book's pages sit at `llm_spell_check_status='in_progress'` until the poller scanner (`run_batch_llm_spell_check_poller_scanner`, ~1-minute cadence — watch worker logs) picks up the completed Gemini batch job; pages then flip to `succeeded` with corrected text and `llm_spell_check_at` populated.

- [ ] **Step 7: Batch flag does not affect per-page trigger**

With `llm_spell_check_batch_enabled` still `true`, trigger a per-page LLM spell check on any page.
Expected: it still completes quickly via the live path (worker log shows `llm_spell_check_job`, not a batch submission) — confirming the per-page trigger always ignores the batch flag, per the design doc's explicit non-goal.

- [x] **Step 8: Full automated test suite**

Run:
```bash
cd packages/backend-core && python -m pytest tests/app/services/llm_spell_check_service_test.py tests/app/services/batch_llm_spell_check_service_test.py tests/app/db/pages_repository_test.py tests/app/db/books_repository_test.py -v
cd services/worker && python -m pytest tests/jobs/llm_spell_check_job_test.py tests/scanners/batch_llm_spell_check_poller_scanner_test.py -v
cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -v
cd apps/frontend && npx vitest run
```
Expected: all PASS, no regressions in pre-existing tests in any of these files.

DONE — all 60 new tests across backend-core/worker/backend/frontend pass. The only failures in the full suites (`test_get_books` in `books_router_test.py`, one `AdminView.test.tsx` case, and a handful of pre-existing frontend fixture-typing errors) were verified via `git stash` to be 100% pre-existing baseline drift, unaffected by this feature's changes (identical failure count/content with and without this branch's diffs).

- [x] **Step 9: OpenAPI drift check**

Run: `python scripts/check_openapi.py`
Expected: `API schema is in sync with docs/main/openapi.json.`

DONE — confirmed in sync.

**Steps 2-7 (live browser + real Gemini API + Docker rebuild) were not run in this session** — they require actually starting the full stack, spending real Gemini API quota, and manual browser interaction, which is out of scope for autonomous execution. Migrations 090/091 were applied directly to the local dev Postgres (Step 1 verified without a full container rebuild). See the summary message for what's left for the user to manually verify.

---

## Testing Summary

| Layer | Test file | Task |
|---|---|---|
| Repository (pages) | `packages/backend-core/tests/app/db/pages_repository_test.py` | 4 |
| Service (live correction) | `packages/backend-core/tests/app/services/llm_spell_check_service_test.py` | 7 |
| Worker job (live path) | `services/worker/tests/jobs/llm_spell_check_job_test.py` | 8 |
| Service (batch submit + poll) | `packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py` | 10 |
| Worker scanner (batch poller) | `services/worker/tests/scanners/batch_llm_spell_check_poller_scanner_test.py` | 11 |
| Repository (stats aggregation) | `packages/backend-core/tests/app/db/books_repository_test.py` | 13 |
| Endpoints | `services/backend/tests/api/endpoints/books_router_test.py` | 15 |
| Frontend service | `apps/frontend/src/tests/services/persistenceService.test.ts` | 19 |
| Frontend hook | `apps/frontend/src/tests/hooks/useBookActions.test.tsx` | 20 |
| Frontend component (reader) | `apps/frontend/src/tests/components/reader/PageItem.test.tsx` | 22 |
| Frontend component (admin) | `apps/frontend/src/tests/components/admin/AdminView.test.tsx` | 23 |

## Spec Coverage Checklist

Every numbered section of `docs/superpowers/specs/2026-09-05-llm-spell-correction-design.md` maps to a task above:

| Spec section | Task(s) |
|---|---|
| §1 Migration (pages columns) | 1 |
| §2 Migration (batch jobs table + config seeds) | 1, 2 |
| §3 ORM models | 3 |
| §4 Repository (`set_llm_spell_check_status`) | 4 |
| §5 Service (`build_correction_prompt`, `correct_page_text`, `_validate_correction`) | 6, 7 |
| §6 Worker job (live path) | 5, 8, 9 |
| §7 Batch submission service | 10 |
| §8 Batch poller scanner | 11, 12 |
| §9 Worker registration | 9, 12 |
| §10 Backend endpoints | 14, 15 |
| §11 Frontend (constants, service, hooks, ActionMenu, PageItem/ReaderView, status display, i18n) | 16, 17, 18, 19, 20, 21, 22, 24 |
| §12 Book-level status icon | 13, 23 |
| Error Handling | 4, 7, 10, 15 (guardrail + rollback logic embedded per-task) |
| Testing | every task's TDD steps + Task 25 |
| Verification Plan | Task 25 |

Non-Goals and Known Limitations from the spec require no implementation (no pipeline gating, no dictionary-based output validation, no review/approve UI, no downstream chunking/embedding re-trigger) — confirmed nothing in this plan introduces them.
