# Design Spec: Uyghur History Dictionary Extraction from Books

- **Date**: 2026-08-02
- **Topic**: Extracting Uyghur historical figures, events, dynasties, and concepts from catalog books to populate `history_dictionary`
- **Model**: Configurable via `system_config` (default: Gemini 3.6 Flash / `gemini-2.5-flash`)
- **UI Action Label**: `تارىخىي ئاتالغۇلارنى تېپىش`

---

## 1. Overview & Objectives

Currently, the `history_dictionary` table primarily contains translated world history entries but lacks specific Uyghur historical content. Kitabim-AI has a rich catalog of digitized history books.

This design introduces an on-demand, semi-automated extraction pipeline:
1. Admins trigger **"تارىخىي ئاتالغۇلارنى تېپىش"** (Find Historical Terms) on any book in the Admin Book Catalog.
2. An ARQ background worker scans the book using Gemini Flash (or configured model from `system_config`), evaluating entities across 4 categories:
   - **Figures** (`شەخسلەر`)
   - **Events** (`ۋەقە-ھادىسىلەر`)
   - **Dynasties & Regimes** (`خانلىقلار`)
   - **Concepts & Places** (`ئاتالغۇ-جاي-ئورۇنلار`)
3. Candidates are filtered for historical significance (default $\ge 5/10$).
4. Duplicate entries found across multiple books are automatically synthesized using LLM text consolidation and assigned multi-book source citations (`sources` JSONB array).
5. Candidates are written to a `history_dictionary_staging` table (marked with `is_ai_generated = true`) for admin review, editing, and single/bulk approval in the Admin Panel before going live into `history_dictionary`.

---

## 2. Architecture & Data Flow

```mermaid
flowchart TD
    AdminBookCatalog["Admin Book Catalog UI\n('تارىخىي ئاتالغۇلارنى تېپىش')"] -->|POST /api/v1/admin/books/:id/extract-history| FastAPIEndpoint["FastAPI Admin Route"]
    FastAPIEndpoint -->|Enqueue Task| ARQWorker["ARQ Background Worker\n(history_extraction_job)"]
    
    ARQWorker -->|Read Config| SystemConfig[("system_config Table\n(model, min_significance)")]
    ARQWorker -->|Fetch Pages| BookPages[("book_pages Table")]
    
    ARQWorker -->|Batch Pages + 2-Page Window| GeminiClient["Gemini 3.6 Flash API\n(response_schema)"]
    
    GeminiClient -->|Candidate Entities (is_ai_generated=true)| DeduplicationEngine["Deduplication & LLM Synthesis Engine"]
    DeduplicationEngine -->|Normalized Similarity Check| HistoryStaging[("history_dictionary_staging")]
    
    DeduplicationEngine -->|Existing Duplicate Found| LLMSynthesizer["LLM Multi-Book Synthesizer"]
    LLMSynthesizer -->|Merge Text & Sources| HistoryStaging
    
    HistoryStaging -->|Review & Approve| AdminStagingUI["Admin Staging Queue UI\n(HistoryDictionaryPanel.tsx)"]
    AdminStagingUI -->|Publish| HistoryDict[("history_dictionary Table")]
```

---

## 3. Detailed Data Models & Migrations

### 3.1 Migration: Enhance `public.history_dictionary`
Add the following columns to `public.history_dictionary`:
```sql
ALTER TABLE public.history_dictionary
    ADD COLUMN IF NOT EXISTS category VARCHAR(30) DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS significance_score INTEGER DEFAULT 5,
    ADD COLUMN IF NOT EXISTS is_ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS sources JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_history_dictionary_category ON public.history_dictionary(category);
CREATE INDEX IF NOT EXISTS idx_history_dictionary_ai_gen ON public.history_dictionary(is_ai_generated);
```

### 3.2 Migration: Create `public.history_dictionary_staging`
```sql
CREATE TABLE IF NOT EXISTS public.history_dictionary_staging (
    id                 SERIAL PRIMARY KEY,
    book_id            VARCHAR(64) NOT NULL,
    term               VARCHAR(500) NOT NULL,
    transliteration    TEXT,
    definition         TEXT NOT NULL,
    category           VARCHAR(30) NOT NULL DEFAULT 'general',
    significance_score INTEGER NOT NULL DEFAULT 5,
    is_ai_generated    BOOLEAN NOT NULL DEFAULT TRUE,
    letter_group       VARCHAR(10) NOT NULL,
    sources            JSONB NOT NULL DEFAULT '[]'::jsonb,
    status             VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_history_staging_term ON public.history_dictionary_staging(term);
CREATE INDEX IF NOT EXISTS idx_history_staging_status ON public.history_dictionary_staging(status);
CREATE INDEX IF NOT EXISTS idx_history_staging_category ON public.history_dictionary_staging(category);
```

---

## 4. Backend Extraction Pipeline & Configuration

### 4.1 System Configuration Keys (`system_config`)
The pipeline reads the following dynamic settings from `system_config`:
- `history_extraction_model`: Default `'gemini-2.5-flash'` (or `'gemini-1.5-flash'`).
- `history_extraction_min_significance`: Default `'5'`.
- `history_extraction_batch_pages`: Default `'15'`.

### 4.2 Handling Split-Page Events & Cross-Book Merging
1. **Continuous Batching with Overlap**:
   - Reads pages in 15-page blocks.
   - Applies a 2-page overlapping sliding window between batches so events split across page boundaries (e.g. Page 45–46) are never severed at batch seams.
2. **Page Range Citations**:
   - Structured JSON schema returns `pages: number[]` for multi-page entities.
3. **Cross-Book Synthesis**:
   - When a candidate matches an existing term in `history_dictionary_staging` or `history_dictionary` (`trigram similarity > 0.85`), the synthesizer sends both definitions to Gemini to construct a single unified biography/event text, appending the new book's citation to `sources`. `is_ai_generated` remains `TRUE`.

### 4.3 Admin API Routes (`services/backend/app/routes/admin/history_dictionary.py`)
- `POST /api/v1/admin/books/{book_id}/extract-history`: Enqueue ARQ task.
- `GET /api/v1/admin/history-dictionary/staging`: List pending candidates with pagination, category, `is_ai_generated`, and significance filters.
- `POST /api/v1/admin/history-dictionary/staging/{id}/approve`: Move candidate from staging to `history_dictionary`.
- `POST /api/v1/admin/history-dictionary/staging/bulk-approve`: Approve multiple selected IDs.
- `DELETE /api/v1/admin/history-dictionary/staging/{id}`: Reject staging item.

---

## 5. Admin Frontend UI Design

### 5.1 Book Catalog Action
- Button Label: **"تارىخىي ئاتالغۇلارنى تېپىش"**
- Opens confirmation modal showing target book title, dynamic `system_config` model name, and significance slider.

### 5.2 Admin Staging Queue (`HistoryDictionaryPanel.tsx`)
- **Location**: `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`
- **Tab 1 (Staging Queue)**:
  - Table Columns: Term (تارىخىي ئاتالغۇ), Transliteration/Dates, Category Badge, Significance Badge (1–10), **AI Badge (`🤖 AI Extraction`)**, Definition, Sources (`Book Title, p. 45–46`), Actions.
  - Actions: **Approve (تەستىقلاش)**, **Edit & Approve (تەھرىرلەپ تەستىقلاش)**, **Reject (رەت قىلىش)**.
  - Bulk approval support.
- **Tab 2 (Published Terms)**: Search and edit live entries in `history_dictionary`, with an `is_ai_generated` filter badge and column.

---

## 6. Verification Plan

### Automated Verification
1. Migration test: Apply migrations and verify `is_ai_generated` column exists in both tables.
2. Backend core test: Unit tests for `history_extraction_service.py` verifying JSON prompt parsing, `is_ai_generated=true` flag set, split-page windowing, and similarity deduplication logic.
3. API route test: Test FastAPI admin routes for extraction enqueue, staging list, approval, and rejection.

### Manual Verification
1. Trigger **"تارىخىي ئاتالغۇلارنى تېپىش"** on a test history book in the Admin Panel.
2. Verify candidate terms appear in the Staging Queue marked with `🤖 AI Extraction`.
3. Edit and approve a candidate term; verify it moves to `history_dictionary` with `is_ai_generated = true` preserved and appears in public History Dictionary search results.
