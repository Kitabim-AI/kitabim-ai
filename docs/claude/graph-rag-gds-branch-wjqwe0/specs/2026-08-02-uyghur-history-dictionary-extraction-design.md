# Design Spec: Uyghur History Dictionary Extraction from Books

- **Date**: 2026-08-02
- **Topic**: Extracting Uyghur historical figures, events, dynasties, and concepts from catalog books to populate and enrich `history_dictionary`
- **Model**: Dynamic runtime configuration via `system_config` table (key: `history_extraction_model`, default: `gemini-2.5-flash`)
- **UI Action Label**: `تارىخىي ئاتالغۇلارنى تېپىش`

---

## 1. Overview & Objectives

Currently, the `history_dictionary` table primarily contains translated world history entries but lacks specific Uyghur historical content. Kitabim-AI has a rich catalog of digitized history books.

This design introduces an on-demand, semi-automated extraction and enrichment pipeline:
1. Admins trigger **"تارىخىي ئاتالغۇلارنى تېپىش"** (Find Historical Terms) on any book in the Admin Book Catalog.
2. An ARQ background worker scans the book using the LLM model configured in `system_config` (`history_extraction_model`), evaluating entities across 4 categories:
   - **Figures** (`شەخسلەر`)
   - **Events** (`ۋەقە-ھادىسىلەر`)
   - **Dynasties & Regimes** (`خانلىقلار`)
   - **Concepts & Places** (`ئاتالغۇ-جاي-ئورۇنلار`)
3. Candidates are filtered against a 4-tier historical significance rubric (default threshold $\ge 5/10$, configured via `history_extraction_min_significance`).
4. Duplicate entries found across multiple books or existing records in `history_dictionary` are automatically merged using **LLM Incremental Enrichment**:
   - Gemini synthesizes an updated definition with **Inline Footnote Citations** (e.g. `[1]`, `[2]`) pointing to exact books and pages, appending new source metadata (`sources` JSONB array).
5. Candidates & Enriched updates are written to a `history_dictionary_staging` table (marked with `is_ai_generated = true` and `entry_type = 'new'` or `'enrichment'`) for admin review, editing, and single/bulk approval in the Admin Panel before going live.

---

## 2. Architecture & Data Flow

```mermaid
flowchart TD
    AdminBookCatalog["Admin Book Catalog UI\n('تارىخىي ئاتالغۇلارنى تېپىش')"] -->|POST /api/v1/admin/books/:id/extract-history| FastAPIEndpoint["FastAPI Admin Route"]
    FastAPIEndpoint -->|Enqueue Task| ARQWorker["ARQ Background Worker\n(history_extraction_job)"]
    
    ARQWorker -->|Read Config Key: history_extraction_model| SystemConfig[("system_config Table\n(history_extraction_model, min_significance)")]
    ARQWorker -->|Fetch Pages| BookPages[("book_pages Table")]
    
    ARQWorker -->|Batch Pages + 2-Page Window| GeminiClient["Configured Gemini Model\n(via system_config)"]
    
    GeminiClient -->|Candidate Entities + Significance Rubric| SignificanceFilter["Significance Filter\n(score >= min_significance)"]
    SignificanceFilter -->|Passes Threshold| DeduplicationEngine["Deduplication & LLM Synthesis Engine"]
    
    DeduplicationEngine -->|Trigram Similarity Match| DBCheck{Existing Term Found?}
    
    DBCheck -->|No Match| NewStaging["Create New Candidate\n(entry_type = 'new')"]
    DBCheck -->|Match Found in Live/Staging| EnrichmentSynthesizer["LLM Incremental Enrichment\n(Merge existing + new facts + inline citations)"]
    
    EnrichmentSynthesizer -->|Staged Update| EnrichmentStaging["Create Enrichment Candidate\n(entry_type = 'enrichment')"]
    
    NewStaging --> HistoryStaging[("history_dictionary_staging")]
    EnrichmentStaging --> HistoryStaging
    
    HistoryStaging -->|Review & Approve| AdminStagingUI["Admin Staging Queue UI\n(HistoryDictionaryPanel.tsx)"]
    AdminStagingUI -->|Publish / Update| HistoryDict[("history_dictionary Table")]
```

---

## 3. Detailed Data Models & Multi-Book Citation Schema

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
    id                     SERIAL PRIMARY KEY,
    existing_dictionary_id INTEGER REFERENCES public.history_dictionary(id) ON DELETE SET NULL,
    book_id                VARCHAR(64) NOT NULL,
    term                   VARCHAR(500) NOT NULL,
    transliteration        TEXT,
    definition             TEXT NOT NULL,
    original_definition    TEXT, -- Stashed existing definition for side-by-side diff
    category               VARCHAR(30) NOT NULL DEFAULT 'general',
    significance_score     INTEGER NOT NULL DEFAULT 5,
    significance_reason    TEXT, -- LLM rationale for significance rating
    is_ai_generated        BOOLEAN NOT NULL DEFAULT TRUE,
    entry_type             VARCHAR(20) NOT NULL DEFAULT 'new', -- 'new' or 'enrichment'
    letter_group           VARCHAR(10) NOT NULL,
    sources                JSONB NOT NULL DEFAULT '[]'::jsonb,
    status                 VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_staging_term ON public.history_dictionary_staging(term);
CREATE INDEX IF NOT EXISTS idx_history_staging_status ON public.history_dictionary_staging(status);
CREATE INDEX IF NOT EXISTS idx_history_staging_entry_type ON public.history_dictionary_staging(entry_type);
```

---

## 4. Dynamic LLM Provider & System Config Integration

### 4.1 System Configuration Keys (`system_config`)
The extraction pipeline dynamically fetches settings from `system_config` at the start of every extraction/enrichment run:

| Config Key | Default Value | Description |
| :--- | :--- | :--- |
| `history_extraction_model` | `'gemini-2.5-flash'` | Model string passed to LLM client (e.g. `gemini-2.5-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.5-pro`). |
| `history_extraction_min_significance` | `'5'` | Minimum threshold score (1–10) required for a candidate to be staged. |
| `history_extraction_batch_pages` | `'15'` | Number of continuous OCR pages passed per prompt batch. |

* **Runtime Switching**: Admins can update `history_extraction_model` via the Admin System Settings UI or database query at any time. The background extraction service reads the live value per task invocation without needing a backend deployment or container restart.

---

## 5. Historical Significance Evaluation & Extraction Pipeline

### 5.1 Four-Tier Historical Significance Rubric
Gemini evaluates candidate terms against a strict 4-tier rubric:
- **Score 9–10**: Central historical rulers, sultans, pivotal battles, famous authors & classics.
- **Score 7–8**: Key generals, regional rulers, major historical fortresses, key treaties.
- **Score 5–6**: Verifiable secondary historical figures or localized events with documented dates and biographical contributions.
- **Score 1–4**: Incidental mentions (messengers, local soldiers, generic titles, unverified single-sentence references) $\rightarrow$ **Filtered Out**.

### 5.2 Split-Page Handling & LLM Incremental Enrichment
1. **Continuous Batching with Overlap**:
   - Reads pages in 15-page blocks with a 2-page sliding overlap window to handle cross-page split narratives.
2. **Incremental Enrichment Logic**:
   - Matches candidate terms against `history_dictionary_staging` and `history_dictionary` using normalized trigram similarity (`similarity > 0.85`).
   - If a match is found, Gemini synthesizes an enriched definition with inline footnote citations (`[1]`, `[2]`) pointing to exact books and pages, preserving original content and updating `sources`.

### 5.3 Admin API Routes (`services/backend/app/routes/admin/history_dictionary.py`)
- `POST /api/v1/admin/books/{book_id}/extract-history`: Enqueue ARQ task.
- `GET /api/v1/admin/history-dictionary/staging`: List pending candidates with filters (`category`, `entry_type`, `is_ai_generated`, `significance`).
- `POST /api/v1/admin/history-dictionary/staging/{id}/approve`: Apply candidate.
- `POST /api/v1/admin/history-dictionary/staging/bulk-approve`: Approve multiple selected IDs.
- `DELETE /api/v1/admin/history-dictionary/staging/{id}`: Reject staging item.

---

## 6. Admin & User UI Design

### 6.1 Book Catalog Action
- Button Label: **"تارىخىي ئاتالغۇلارنى تېپىش"**
- Confirmation modal displays book details, the currently configured model loaded from `system_config` (e.g. *Model: gemini-2.5-flash*), and a **Significance Threshold Slider** (default: 5).

### 6.2 Admin Staging Queue (`HistoryDictionaryPanel.tsx`)
- **Location**: `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`
- **Tab 1 (Staging Queue)**:
  - Table Columns: Term, Transliteration/Dates, Category Badge, Type Badge (`🆕 New` vs `✨ Enrichment`), Significance Score Badge (with hover tooltip displaying `significance_reason`), `🤖 AI Extraction` Badge, Enriched Definition (with inline footnotes `[1]`, `[2]`), Sources, Actions.
  - Actions: **Approve (تەستىقلاش)**, **Edit & Approve (تەھرىرلەپ تەستىقلاش)**, **Reject (رەت قىلىش)**.
  - Bulk approval support.
- **Tab 2 (Published Terms)**: Search and edit live entries in `history_dictionary`.

### 6.3 Public Search View with Interactive Footnotes
- Footnotes `[1]`, `[2]` in definition text are clickable badges that jump to the source citation card and highlight the **"بەتنى ئوقۇش / Read Page"** button.

---

## 7. Verification Plan

### Automated Verification
1. `system_config` integration test: Verify `history_extraction_service.py` dynamically loads `history_extraction_model` from `system_config` repo.
2. Migration test: Verify `history_dictionary_staging` schema includes `significance_reason`, `existing_dictionary_id`, `entry_type`, and `original_definition`.
3. Significance filtering test: Unit test verifying candidates with score $< min\_significance$ are dropped automatically.

### Manual Verification
1. Update `history_extraction_model` in `system_config` to `gemini-2.5-flash`.
2. Run **"تارىخىي ئاتالغۇلارنى تېپىش"** on a test history book and confirm the task executes using the configured model.
3. Inspect Staging Queue, verify significance scores/rationale, edit & approve a candidate term, and test search result interactive footnotes.
