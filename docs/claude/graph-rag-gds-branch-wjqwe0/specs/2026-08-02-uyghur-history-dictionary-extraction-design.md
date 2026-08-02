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
3. Candidates are evaluated against a 4-tier historical significance rubric (1–10 scale). **Highest significance candidates (Score 10 $\rightarrow$ 9 $\rightarrow$ 8) are prioritized first** in extraction outputs and admin staging queues.
4. Duplicate entries found across multiple books or existing records in `history_dictionary` are automatically merged using **LLM Incremental Enrichment**:
   - Gemini synthesizes an updated definition with **Inline Footnote Citations** (e.g. `[1]`, `[2]`) pointing to exact books and pages, appending new source metadata (`sources` JSONB array).
5. **Strict Admin Re-Review Gate**: Any modification or enrichment proposed for an existing published history record is written as a pending candidate (`entry_type = 'enrichment'`) to `history_dictionary_staging`. The live public record remains unchanged until an Admin reviews the proposed diff and explicitly approves it.

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
    
    DBCheck -->|No Match| NewStaging["Create New Candidate\n(entry_type = 'new', status = 'pending')"]
    DBCheck -->|Match Found in Live/Staging| EnrichmentSynthesizer["LLM Incremental Enrichment\n(Merge existing + new facts + inline citations)"]
    
    EnrichmentSynthesizer -->|Staged Update (Live Record Untouched)| EnrichmentStaging["Create Enrichment Candidate\n(entry_type = 'enrichment', status = 'pending')"]
    
    NewStaging --> HistoryStaging[("history_dictionary_staging\n(Sorted by significance_score DESC)")]
    EnrichmentStaging --> HistoryStaging
    
    HistoryStaging -->|Diff View & Admin Review (Highest Significance First)| AdminStagingUI["Admin Staging Queue UI\n(HistoryDictionaryPanel.tsx)"]
    AdminStagingUI -->|Admin Explicit Approval| HistoryDict[("history_dictionary Table\n(Updates Live Entry)")]
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
CREATE INDEX IF NOT EXISTS idx_history_dictionary_sig ON public.history_dictionary(significance_score DESC);
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
    status                 VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_staging_term ON public.history_dictionary_staging(term);
CREATE INDEX IF NOT EXISTS idx_history_staging_status ON public.history_dictionary_staging(status);
CREATE INDEX IF NOT EXISTS idx_history_staging_sig ON public.history_dictionary_staging(significance_score DESC);
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

* **Runtime Switching**: Admins can update `history_extraction_model` via the Admin System Settings UI or database query at any time without code redeployments.

---

## 5. Historical Significance & Highest Score Ordering

### 5.1 Four-Tier Historical Significance Rubric
- **Score 9–10**: Central historical rulers, sultans, pivotal battles, famous authors & classics.
- **Score 7–8**: Key generals, regional rulers, major historical fortresses, key treaties.
- **Score 5–6**: Verifiable secondary historical figures or localized events with documented dates and biographical contributions.
- **Score 1–4**: Incidental mentions (messengers, local soldiers, generic titles, unverified single-sentence references) $\rightarrow$ **Filtered Out**.

### 5.2 Highest Significance Score Ordering (`significance_score DESC`)
- Both backend database queries (`GET /api/v1/admin/history-dictionary/staging`) and the Admin Staging Queue UI sort candidate entries strictly by **`significance_score DESC`** by default.
- This ensures admins always review, edit, and approve the highest priority historical terms (Scores 10, 9, 8) first before lower-tier entries.

### 5.3 Mandatory Admin Re-Review Gate for Enriched Records
- Proposed modifications or additions to existing live records in `history_dictionary` **NEVER** overwrite the published live record automatically.
- Candidate entries are written to staging with `entry_type = 'enrichment'`, sorted by significance score, and require explicit admin approval before live updating.

---

## 6. Admin & User UI Design

### 6.1 Book Catalog Action
- Button Label: **"تارىخىي ئاتالغۇلارنى تېپىش"**
- Confirmation modal displays book details, dynamic model from `system_config`, and a **Significance Threshold Slider** (default: 5).

### 6.2 Admin Staging Queue (`HistoryDictionaryPanel.tsx`)
- **Location**: `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`
- **Tab 1 (Staging Queue)**:
  - Default Sort: **Highest Significance First (`significance_score DESC`)**.
  - Table Columns: Term, Transliteration/Dates, Category Badge, Type Badge (`🆕 New` vs `✨ Enrichment`), Significance Score Badge (with hover tooltip displaying `significance_reason`), `🤖 AI Extraction` Badge, Enriched Definition (with inline footnotes `[1]`, `[2]`), Sources, Actions.
  - **Diff Modal**: For `✨ Enrichment` candidates, clicking "View Diff (تەققىقلاش)" displays side-by-side comparison.
  - Actions: **Approve (تەستىقلاش)**, **Edit & Approve (تەھرىرلەپ تەستىقلاش)**, **Reject (رەت قىلىش)**.
  - Bulk approval support.
- **Tab 2 (Published Terms)**: Search and edit live entries in `history_dictionary`.

### 6.3 Public Search View with Interactive Footnotes
- Footnotes `[1]`, `[2]` in definition text are clickable badges that jump to the source citation card and highlight the **"بەتنى ئوقۇش / Read Page"** button.

---

## 7. Verification Plan

### Automated Verification
1. Default ordering test: Verify `GET /api/v1/admin/history-dictionary/staging` returns candidates sorted by `significance_score DESC`.
2. `system_config` integration test: Verify dynamic loading of `history_extraction_model`.
3. Re-review gate test: Verify modified existing concepts require explicit approval.

### Manual Verification
1. Run **"تارىخىي ئاتالغۇلارنى تېپىش"** on a history book.
2. Open Staging Queue: confirm candidates are sorted with **Score 10 and 9 terms at the top**.
3. Approve top candidates and verify live dictionary search results.
