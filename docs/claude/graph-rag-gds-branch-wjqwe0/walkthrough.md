# Uyghur History Dictionary AI Extraction — Implementation Walkthrough

## Completed Implementation Overview
We have fully implemented the end-to-end **Uyghur History Dictionary Extraction Feature** from OCR books with multi-book citations, significance sorting, dynamic LLM model configuration, and mandatory admin review gates.

---

## 1. Database & Schema Changes
- **Migration Script (`073_create_history_dictionary_staging.sql`)**:
  - Added `category`, `significance_score`, `is_ai_generated`, and JSONB `sources` to `history_dictionary`.
  - Created `history_dictionary_staging` table with `entry_type` (`new` | `enrichment`), `status` (`pending` | `approved` | `rejected`), and `original_definition`.
  - Created pg_trgm trigram index `idx_history_dict_staging_term_trgm` for similarity matching.
  - Added `history_gemini_model` key to `system_config` (defaulting to `gemini-2.5-flash`).
- **SQLAlchemy & Pydantic Models**:
  - Created `HistoryDictionaryStaging` ORM model in `packages/backend-core/app/db/models.py`.
  - Added `SourceCitation`, `HistoryStagingItem`, and `PaginatedHistoryStagingItems` Pydantic schemas in `packages/backend-core/app/models/schemas.py`.

---

## 2. Repository Layer
- **`DictionaryRepository`**:
  - Added `get_staging_terms()` with **`significance_score DESC`** default sorting to ensure highest significance entries appear first.
  - Implemented `find_matching_history_term()` and `find_matching_staging_term()` using `pg_trgm` similarity.
  - Implemented `approve_staging_term()` (publishing new entries or merging enrichments into `history_dictionary`) and `reject_staging_term()`.

---

## 3. History Extraction Service & LLM Synthesis
- **`HistoryExtractionService`**:
  - Reads `history_gemini_model` dynamically from `system_config`.
  - Continuous 15-page batching with 2-page sliding overlap window.
  - 4-tier significance rubric (default threshold $\ge 5/10$).
  - LLM Incremental Synthesis with inline footnote citations (`[1]`, `[2]`).

---

## 4. Background Job & API Endpoints
- **ARQ Worker Job**:
  - `extract_book_history_terms_task` registered in `services/worker/worker.py`.
- **FastAPI Admin Endpoints (`api/endpoints/admin_history_dictionary_router.py`)**:
  - `POST /api/v1/admin/books/{book_id}/extract-history`: Triggers background extraction job ("تارىخىي ئاتالغۇلارنى تېپىش").
  - `GET /api/v1/admin/history-dictionary/staging`: Lists review candidates sorted by significance score.
  - `POST /api/v1/admin/history-dictionary/staging/{staging_id}/approve`: Approves candidate.
  - `POST /api/v1/admin/history-dictionary/staging/bulk-approve`: Bulk approves candidate batch.
  - `DELETE /api/v1/admin/history-dictionary/staging/{staging_id}`: Rejects candidate.

---

## 5. Frontend Admin Interface
- **Action Menu Button**:
  - Added **`تارىخىي ئاتالغۇلارنى تېپىش`** button to per-book catalog action menu in `ActionMenu.tsx`.
- **Review Queue Panel (`HistoryStagingQueuePanel.tsx`)**:
  - Displays candidates with color-coded significance badges (`★ 9/10`, `★ 7/10`).
  - Side-by-side diff comparison for enrichment candidates.
  - Multi-book fact citations display (`[1] «ئۇيغۇر تارىخى» 1-جىلد (45-بەت)`).
  - Single and bulk approval controls.
- **Admin Tab Navigation**:
  - Added `تارىخىي ئاتالغۇلار باھالاش` tab to `AdminTabs.tsx`.

---

## Verification Results
All automated tests passed successfully:
```bash
# Backend-core repository & service tests
packages/backend-core/tests/app/models/history_staging_schemas_test.py PASSED
packages/backend-core/tests/app/db/repositories/test_history_dictionary_repo.py PASSED
packages/backend-core/tests/app/services/history_extraction_service_test.py PASSED

# Worker job & API router tests
services/worker/tests/jobs/history_extraction_job_test.py PASSED
services/backend/tests/api/endpoints/admin_history_dictionary_router_test.py PASSED
```
