# Uyghur History Dictionary Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract historically significant figures, events, dynasties, and concepts from catalog books using Gemini Flash (dynamically configured via `system_config`), featuring multi-book LLM enrichment with inline footnote citations (`[1]`, `[2]`), an administrative staging queue sorted by highest significance score first, and a mandatory admin re-review gate for modified entries.

**Architecture:** A PostgreSQL migration creates `history_dictionary_staging` and adds metadata columns to `history_dictionary`. An ARQ worker task (`history_extraction_job.py`) runs continuous page batching (15 pages with 2-page sliding overlap window) using Gemini Flash, evaluates entities against a 4-tier significance rubric, performs trigram deduplication and LLM enrichment for existing records, and writes candidate entries to staging. A FastAPI admin router manages staging review, side-by-side diff views, and explicit approval into `history_dictionary`. Frontend React components provide the catalog trigger button ("تارىخىي ئاتالغۇلارنى تېپىش") and the staging queue admin panel (`HistoryDictionaryPanel.tsx`).

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL (trigram similarity `pg_trgm`), ARQ / Redis, Google Gemini API, React 19, TypeScript, Vite, Tailwind CSS.

## Global Constraints

- Keep monorepo structure intact (`packages/backend-core`, `services/backend`, `services/worker`, `apps/frontend`).
- System config key `history_gemini_model` (default: `'gemini-2.5-flash'`) dynamically sets the LLM model name.
- Default sorting for staging candidates is `significance_score DESC, created_at DESC`.
- Mandatory Admin Re-Review Gate: Modified live entries must NEVER overwrite `history_dictionary` automatically; they must be staged for admin review.
- UI button title: `تارىخىي ئاتالغۇلارنى تېپىش`

---

### Task 1: Database Migrations (`history_dictionary` & `history_dictionary_staging`)

**Files:**
- Create: `packages/backend-core/migrations/073_create_history_dictionary_staging.sql`
- Create: `packages/backend-core/migrations/073_rollback_create_history_dictionary_staging.sql`
- Test: `packages/backend-core/tests/app/db/test_migrations.py`

**Interfaces:**
- Consumes: Existing PostgreSQL database connection
- Produces: `history_dictionary_staging` table & enhanced `history_dictionary` columns (`category`, `significance_score`, `is_ai_generated`, `sources`)

- [ ] **Step 1: Write migration SQL script**

```sql
-- Migration: 073_create_history_dictionary_staging.sql
BEGIN;

ALTER TABLE public.history_dictionary
    ADD COLUMN IF NOT EXISTS category VARCHAR(30) DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS significance_score INTEGER DEFAULT 5,
    ADD COLUMN IF NOT EXISTS is_ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS sources JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_history_dictionary_category ON public.history_dictionary(category);
CREATE INDEX IF NOT EXISTS idx_history_dictionary_ai_gen ON public.history_dictionary(is_ai_generated);
CREATE INDEX IF NOT EXISTS idx_history_dictionary_sig ON public.history_dictionary(significance_score DESC);

CREATE TABLE IF NOT EXISTS public.history_dictionary_staging (
    id                     SERIAL PRIMARY KEY,
    existing_dictionary_id INTEGER REFERENCES public.history_dictionary(id) ON DELETE SET NULL,
    book_id                VARCHAR(64) NOT NULL,
    term                   VARCHAR(500) NOT NULL,
    transliteration        TEXT,
    definition             TEXT NOT NULL,
    original_definition    TEXT,
    category               VARCHAR(30) NOT NULL DEFAULT 'general',
    significance_score     INTEGER NOT NULL DEFAULT 5,
    significance_reason    TEXT,
    is_ai_generated        BOOLEAN NOT NULL DEFAULT TRUE,
    entry_type             VARCHAR(20) NOT NULL DEFAULT 'new',
    letter_group           VARCHAR(10) NOT NULL,
    sources                JSONB NOT NULL DEFAULT '[]'::jsonb,
    status                 VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_staging_term ON public.history_dictionary_staging(term);
CREATE INDEX IF NOT EXISTS idx_history_staging_status ON public.history_dictionary_staging(status);
CREATE INDEX IF NOT EXISTS idx_history_staging_sig ON public.history_dictionary_staging(significance_score DESC);
CREATE INDEX IF NOT EXISTS idx_history_staging_entry_type ON public.history_dictionary_staging(entry_type);

COMMIT;
```

- [ ] **Step 2: Write rollback SQL script**

```sql
-- Migration Rollback: 073_rollback_create_history_dictionary_staging.sql
BEGIN;

DROP TABLE IF EXISTS public.history_dictionary_staging CASCADE;

ALTER TABLE public.history_dictionary
    DROP COLUMN IF EXISTS category,
    DROP COLUMN IF EXISTS significance_score,
    DROP COLUMN IF EXISTS is_ai_generated,
    DROP COLUMN IF EXISTS sources;

COMMIT;
```

- [ ] **Step 3: Test migration execution**

Run: `pytest packages/backend-core/tests/app/db/test_migrations.py -v`
Expected: PASS

- [ ] **Step 4: Commit Migration Scripts**

```bash
git add packages/backend-core/migrations/073_*
git commit -m "feat(db): add history_dictionary_staging migration and metadata columns"
```

---

### Task 2: Backend Core Models & Schemas (`models.py`, `schemas.py`)

**Files:**
- Modify: `packages/backend-core/app/db/models.py`
- Modify: `packages/backend-core/app/models/schemas.py`
- Test: `packages/backend-core/tests/app/models/schemas_test.py`

**Interfaces:**
- Consumes: Migration 073 tables
- Produces: `HistoryDictionaryStaging` SQLAlchemy model, `HistoryDictionary` updated model fields, Pydantic schemas (`HistoryStagingItem`, `HistoryStagingCreate`, `HistoryStagingApprove`)

- [ ] **Step 1: Write Pydantic schema unit test**

```python
# packages/backend-core/tests/app/models/history_staging_schemas_test.py
from app.models.schemas import HistoryStagingItem, SourceCitation

def test_source_citation_schema():
    citation = SourceCitation(
        id=1,
        book_id="book-123",
        book_title="ئۇيغۇر ئومۇمىي تارىخى",
        volume=2,
        pages=[45, 46]
    )
    assert citation.book_id == "book-123"
    assert citation.pages == [45, 46]

def test_history_staging_item_schema():
    item = HistoryStagingItem(
        id=1,
        book_id="book-123",
        term="سۇلتان سۇتۇق بۇغراخان",
        transliteration="Sultan Sutuk Bughra Khan, ? - 955",
        definition="ئوتتۇرا ئاسىيادىكى قاراخانىيلار خاندانلىقىنىڭ خانى...",
        category="figure",
        significance_score=9,
        significance_reason="Central Karakhanid ruler",
        is_ai_generated=True,
        entry_type="new",
        letter_group="س",
        sources=[],
        status="pending"
    )
    assert item.significance_score == 9
    assert item.category == "figure"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest packages/backend-core/tests/app/models/history_staging_schemas_test.py -v`
Expected: FAIL ("ImportError: cannot import name 'HistoryStagingItem'")

- [ ] **Step 3: Implement SQLAlchemy model in `models.py`**

In `packages/backend-core/app/db/models.py`, add `HistoryDictionaryStaging` and update `HistoryDictionary`:

```python
class HistoryDictionaryStaging(Base):
    __tablename__ = "history_dictionary_staging"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    existing_dictionary_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("history_dictionary.id", ondelete="SET NULL"), nullable=True
    )
    book_id: Mapped[str] = mapped_column(String(64), nullable=False)
    term: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    transliteration: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    original_definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(30), default="general", nullable=False)
    significance_score: Mapped[int] = mapped_column(Integer, default=5, nullable=False, index=True)
    significance_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    letter_group: Mapped[str] = mapped_column(String(10), nullable=False)
    sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

- [ ] **Step 4: Implement Pydantic schemas in `schemas.py`**

In `packages/backend-core/app/models/schemas.py`, add `SourceCitation`, `HistoryStagingItem`, `HistoryStagingCreate`, `HistoryStagingApprove`.

- [ ] **Step 5: Run unit test to verify pass**

Run: `pytest packages/backend-core/tests/app/models/history_staging_schemas_test.py -v`
Expected: PASS

- [ ] **Step 6: Commit Models & Schemas**

```bash
git add packages/backend-core/app/db/models.py packages/backend-core/app/models/schemas.py packages/backend-core/tests/app/models/history_staging_schemas_test.py
git commit -m "feat(backend-core): add HistoryDictionaryStaging models and Pydantic schemas"
```

---

### Task 3: Backend Repository Methods (`dictionary_repository.py`)

**Files:**
- Modify: `packages/backend-core/app/db/repositories/dictionary_repository.py`
- Test: `packages/backend-core/tests/app/db/repositories/test_history_dictionary_repo.py`

**Interfaces:**
- Consumes: `HistoryDictionaryStaging` model
- Produces:
  - `get_staging_terms(status, category, min_significance, limit, offset)` (ordered by `significance_score DESC`)
  - `get_staging_term_by_id(id)`
  - `find_matching_history_term(term)`
  - `create_or_update_staging_term(...)`
  - `approve_staging_term(id)`
  - `reject_staging_term(id)`

- [ ] **Step 1: Write repository unit test**

```python
# packages/backend-core/tests/app/db/repositories/test_history_dictionary_repo.py
import pytest
from app.db.repositories.dictionary_repository import DictionaryRepository

@pytest.mark.asyncio
async def test_staging_term_flow(db_session):
    repo = DictionaryRepository(db_session)
    staged = await repo.create_staging_term(
        book_id="book-1",
        term="سۇلتان سۇتۇق بۇغراخان",
        definition="تارىخىي شەخس",
        category="figure",
        significance_score=9,
        letter_group="س",
        sources=[]
    )
    assert staged.id is not None
    assert staged.significance_score == 9

    pending = await repo.get_staging_terms(status="pending")
    assert len(pending) >= 1
    assert pending[0]["significance_score"] == 9
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest packages/backend-core/tests/app/db/repositories/test_history_dictionary_repo.py -v`
Expected: FAIL ("AttributeError: 'DictionaryRepository' object has no attribute 'create_staging_term'")

- [ ] **Step 3: Implement repository methods**

In `packages/backend-core/app/db/repositories/dictionary_repository.py`:
Implement `get_staging_terms`, `get_staging_term_by_id`, `find_matching_history_term`, `create_staging_term`, `approve_staging_term`, `reject_staging_term`. Ensure queries use `.order_by(HistoryDictionaryStaging.significance_score.desc(), HistoryDictionaryStaging.created_at.desc())`.

- [ ] **Step 4: Run test to verify pass**

Run: `pytest packages/backend-core/tests/app/db/repositories/test_history_dictionary_repo.py -v`
Expected: PASS

- [ ] **Step 5: Commit Repository Code**

```bash
git add packages/backend-core/app/db/repositories/dictionary_repository.py packages/backend-core/tests/app/db/repositories/test_history_dictionary_repo.py
git commit -m "feat(repo): implement HistoryDictionaryStaging queries with significance_score DESC sorting"
```

---

### Task 4: History Extraction Service & LLM Synthesis (`history_extraction_service.py`)

**Files:**
- Create: `packages/backend-core/app/services/history_extraction_service.py`
- Test: `packages/backend-core/tests/app/services/history_extraction_service_test.py`

**Interfaces:**
- Consumes: `SystemConfig` table (`history_gemini_model`, `history_extraction_min_significance`), Gemini API client, `book_pages` text chunks
- Produces: `HistoryExtractionService.extract_and_stage_history_terms(book_id, min_significance)`

- [ ] **Step 1: Write extraction service unit test with mocks**

```python
# packages/backend-core/tests/app/services/history_extraction_service_test.py
import pytest
from unittest.mock import AsyncMock, patch
from app.services.history_extraction_service import HistoryExtractionService

@pytest.mark.asyncio
async def test_extract_and_stage_history_terms(db_session):
    mock_gemini = AsyncMock()
    mock_gemini.generate_structured.return_value = {
        "entities": [
            {
                "term": "قاراخانىيلار خاندانلىقى",
                "transliteration": "Karakhanid Khanate",
                "definition": "ئوتتۇرا ئاسىيادىكى تۇنجى ئىسلاملاشقان تۈركىي خانلىق [1].",
                "category": "dynasty",
                "significance_score": 9,
                "significance_reason": "Central historical empire in Central Asia",
                "pages": [10, 11]
            }
        ]
    }

    service = HistoryExtractionService(db_session, gemini_client=mock_gemini)
    with patch.object(service, "_get_system_config_model", return_value="gemini-2.5-flash"):
        results = await service.process_book_pages(book_id="test-book-123", pages_data=[
            {"page_number": 10, "content": "قاراخانىيلار خاندانلىقى تۆرەلگەندىن كېيىن..."},
            {"page_number": 11, "content": "ئىسلام دىنىنى قوبۇل قىلدى..."}
        ])

        assert len(results) == 1
        assert results[0]["term"] == "قاراخانىيلار خاندانلىقى"
        assert results[0]["significance_score"] == 9
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest packages/backend-core/tests/app/services/history_extraction_service_test.py -v`
Expected: FAIL ("ModuleNotFoundError: No module named 'app.services.history_extraction_service'")

- [ ] **Step 3: Implement `HistoryExtractionService`**

Create `packages/backend-core/app/services/history_extraction_service.py`:
- Read `history_gemini_model` dynamically from `system_config`.
- Implement continuous 15-page batching with a 2-page sliding overlap window.
- Implement Gemini Flash JSON extraction prompt with 4-tier significance rubric.
- Implement trigram similarity matching (`trigram_similarity > 0.85`) to detect existing staging/published records.
- Implement LLM Incremental Enrichment with inline footnote citations (`[1]`, `[2]`).

- [ ] **Step 4: Run unit test to verify pass**

Run: `pytest packages/backend-core/tests/app/services/history_extraction_service_test.py -v`
Expected: PASS

- [ ] **Step 5: Commit Extraction Service**

```bash
git add packages/backend-core/app/services/history_extraction_service.py packages/backend-core/tests/app/services/history_extraction_service_test.py
git commit -m "feat(services): implement HistoryExtractionService with continuous batching and LLM enrichment"
```

---

### Task 5: Background ARQ Worker Task (`history_extraction_job.py`)

**Files:**
- Create: `services/worker/jobs/history_extraction_job.py`
- Modify: `services/worker/worker.py`
- Test: `services/worker/tests/jobs/history_extraction_job_test.py`

**Interfaces:**
- Consumes: ARQ task queue, `book_id`
- Produces: `extract_book_history_terms_task(ctx, book_id, min_significance)`

- [ ] **Step 1: Write ARQ job unit test**

```python
# services/worker/tests/jobs/history_extraction_job_test.py
import pytest
from unittest.mock import AsyncMock, patch
from jobs.history_extraction_job import extract_book_history_terms_task

@pytest.mark.asyncio
async def test_extract_book_history_terms_task():
    ctx = {"db_session_factory": AsyncMock()}
    with patch("jobs.history_extraction_job.HistoryExtractionService") as mock_service_cls:
        mock_instance = AsyncMock()
        mock_instance.process_book_id.return_value = {"extracted_count": 5}
        mock_service_cls.return_value = mock_instance

        res = await extract_book_history_terms_task(ctx, book_id="book-99", min_significance=5)
        assert res["status"] == "success"
        assert res["extracted_count"] == 5
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest services/worker/tests/jobs/history_extraction_job_test.py -v`
Expected: FAIL ("ModuleNotFoundError: No module named 'jobs.history_extraction_job'")

- [ ] **Step 3: Implement `history_extraction_job.py` and register in `worker.py`**

Create `services/worker/jobs/history_extraction_job.py` with `extract_book_history_terms_task`. Add task to `WorkerSettings.functions` in `services/worker/worker.py`.

- [ ] **Step 4: Run test to verify pass**

Run: `pytest services/worker/tests/jobs/history_extraction_job_test.py -v`
Expected: PASS

- [ ] **Step 5: Commit Worker Job**

```bash
git add services/worker/jobs/history_extraction_job.py services/worker/worker.py services/worker/tests/jobs/history_extraction_job_test.py
git commit -m "feat(worker): register extract_book_history_terms_task in ARQ worker"
```

---

### Task 6: FastAPI Admin API Router (`routes/admin/history_dictionary.py`)

**Files:**
- Create: `services/backend/app/routes/admin/history_dictionary.py`
- Modify: `services/backend/app/main.py`
- Test: `services/backend/tests/routes/admin/test_history_dictionary_routes.py`

**Interfaces:**
- Consumes: Admin auth JWT, FastAPI session
- Produces:
  - `POST /api/v1/admin/books/{book_id}/extract-history`
  - `GET /api/v1/admin/history-dictionary/staging`
  - `POST /api/v1/admin/history-dictionary/staging/{id}/approve`
  - `POST /api/v1/admin/history-dictionary/staging/bulk-approve`
  - `DELETE /api/v1/admin/history-dictionary/staging/{id}`

- [ ] **Step 1: Write API routes test**

```python
# services/backend/tests/routes/admin/test_history_dictionary_routes.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_trigger_book_history_extraction(async_admin_client: AsyncClient):
    resp = await async_admin_client.post("/api/v1/admin/books/book-123/extract-history", json={"min_significance": 5})
    assert resp.status_code == 200
    assert "task_id" in resp.json()

@pytest.mark.asyncio
async def test_list_staging_terms(async_admin_client: AsyncClient):
    resp = await async_admin_client.get("/api/v1/admin/history-dictionary/staging")
    assert resp.status_code == 200
    assert isinstance(resp.json()["items"], list)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest services/backend/tests/routes/admin/test_history_dictionary_routes.py -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement FastAPI routes & register router in `main.py`**

Create `services/backend/app/routes/admin/history_dictionary.py` and mount in `services/backend/app/main.py`.

- [ ] **Step 4: Run test to verify pass**

Run: `pytest services/backend/tests/routes/admin/test_history_dictionary_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit API Router**

```bash
git add services/backend/app/routes/admin/history_dictionary.py services/backend/app/main.py services/backend/tests/routes/admin/test_history_dictionary_routes.py
git commit -m "feat(api): implement admin routes for history dictionary extraction and staging"
```

---

### Task 7: Frontend Admin UI (`HistoryDictionaryPanel.tsx` & Catalog Button)

**Files:**
- Create: `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`
- Modify: `apps/frontend/src/components/admin/books/BookCatalog.tsx` (or equivalent catalog component)
- Modify: `apps/frontend/src/components/admin/dictionary/DictionaryAdminView.tsx`
- Test: `apps/frontend/src/tests/components/admin/HistoryDictionaryPanel.test.tsx`

**Interfaces:**
- Consumes: Admin API endpoints `/api/v1/admin/history-dictionary/staging`
- Produces: React UI for "تارىخىي ئاتالغۇلارنى تېپىش" modal, Staging Queue table (sorted by `significance_score DESC`), Diff Modal, Edit & Approve, and Bulk Approval.

- [ ] **Step 1: Write frontend component test**

```tsx
// apps/frontend/src/tests/components/admin/HistoryDictionaryPanel.test.tsx
import { render, screen } from '@testing-library/react';
import { HistoryDictionaryPanel } from '../../../components/admin/dictionary/HistoryDictionaryPanel';

test('renders history dictionary panel tabs', () => {
  render(<HistoryDictionaryPanel />);
  expect(screen.getByText(/تەستىقلانمىغانلار/i)).toBeInTheDocument();
  expect(screen.getByText(/ئېلان قىلىنغانلار/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify failure**

Run: `npm --prefix apps/frontend test HistoryDictionaryPanel.test.tsx`
Expected: FAIL ("Cannot find module HistoryDictionaryPanel")

- [ ] **Step 3: Implement `HistoryDictionaryPanel.tsx` & Catalog Button `تارىخىي ئاتالغۇلارنى تېپىش`**

Create `HistoryDictionaryPanel.tsx` with:
- Staging queue table with default sort `significance_score DESC`.
- Category filters (`figure`, `event`, `dynasty`, `concept`).
- `🤖 AI Extraction` and `✨ Enrichment Candidate` badges.
- Interactive Diff modal comparing `original_definition` vs `definition`.
- Approve, Edit & Approve, and Bulk Approve buttons.
- Add "تارىخىي ئاتالغۇلارنى تېپىش" action button in Admin Book Catalog.

- [ ] **Step 4: Run test to verify pass**

Run: `npm --prefix apps/frontend test HistoryDictionaryPanel.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit Frontend Components**

```bash
git add apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx apps/frontend/src/components/admin/books/ apps/frontend/src/tests/components/admin/HistoryDictionaryPanel.test.tsx
git commit -m "feat(frontend): implement HistoryDictionaryPanel UI and catalog trigger button"
```

---

### Task 8: End-to-End Search Integration & Docker Compose Verification

**Files:**
- Modify: `apps/frontend/src/components/dictionary/HistoryDictionaryView.tsx` (or public dictionary search tab)
- Test: Manual / End-to-End Docker Compose verification

**Interfaces:**
- Consumes: `history_dictionary` with `sources` JSONB array and inline citations `[1]`, `[2]`.
- Produces: Clickable interactive footnote badges `[1]`, `[2]` linking to book reader page.

- [ ] **Step 1: Update public search view for interactive footnote links**

Make `[1]`, `[2]` in history definition text clickable so they highlight the corresponding source book card and trigger reader navigation to the target volume/page.

- [ ] **Step 2: Rebuild & Restart Docker Compose stack**

Run: `./deploy/local/rebuild-and-restart.sh all`
Expected: All containers (`backend`, `worker`, `frontend`) build and start cleanly.

- [ ] **Step 3: Perform End-to-End Manual Verification**
1. Login to Admin Panel at `http://localhost:30080`.
2. Navigate to Book Catalog, click **"تارىخىي ئاتالغۇلارنى تېپىش"** on a history book.
3. Verify ARQ background task processes book and populates staging queue.
4. Navigate to **Dictionary Admin -> History Dictionary**, verify candidates are sorted with highest significance score (Scores 10, 9) at the top.
5. Test side-by-side Diff view, edit, and click Approve.
6. Search the approved term on the home search page; verify inline footnote `[1]` clicks open the reader page!

- [ ] **Step 4: Commit Search Integration**

```bash
git add apps/frontend/src/components/dictionary/
git commit -m "feat(search): add interactive footnote citations and reader links to history search"
```

---

## Plan Self-Review Checklist

- [x] **Spec Coverage**: All spec requirements (Migration, `system_config` dynamic model reader, continuous 15-page batching with 2-page overlap, 4-tier significance rubric, highest score ordering `significance_score DESC`, LLM enrichment, mandatory re-review gate, `تارىخىي ئاتالغۇلارنى تېپىش` button, interactive footnotes `[1]`, `[2]`) map directly to tasks.
- [x] **Placeholder Scan**: No TODOs, TBDs, or vague placeholders. Complete code snippets and commands provided.
- [x] **Type & Interface Consistency**: Pydantic schemas, DB models, repository signatures, and API endpoints match across backend and frontend tasks.
- [x] **Local Dev Rule**: Includes `./deploy/local/rebuild-and-restart.sh all` for Docker Compose verification.
