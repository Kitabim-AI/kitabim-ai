# Implementation Plan: Gemini Batch API Integration

## Context

The Kitabim AI system processes books through OCR and embeddings using Google Gemini API. Currently, all operations use synchronous/real-time API calls through LangChain abstractions, which incur full API costs.

**Problem**: High-volume, non-time-sensitive operations (OCR and embeddings) are expensive at standard pricing.

**Solution**: Integrate Google Gemini Batch API to achieve **50% cost savings** for bulk processing operations.

**Key Findings**:
- ✅ **LangChain does NOT support Gemini Batch API** - We must use the `google-genai` SDK directly
- ✅ **Gemini Batch API offers 50% cost reduction** with 24-hour turnaround time
- ✅ **Current architecture is ready** - ARQ worker infrastructure and circuit breakers exist
- ✅ **Good candidates**: OCR processing (~100-300 pages/book), embeddings
- ❌ **Not suitable**: RAG queries and category classification (need real-time responses)

**Cost Impact**:
- Current: ~$0.30 per 100-page book
- With Batch API: ~$0.15 per 100-page book
- Savings: **50% reduction** = $150/month for 1,000 books or $1,500/month for 10,000 books

## Plan vs Current Implementation

### ✅ What Already Exists

1. **Database Models** (in `app/db/models.py`):
   - ✅ `Page` model with `status`, `text`, `is_indexed` fields
   - ✅ `Chunk` model with `embedding Vector(768)` (nullable), `book_id`, `page_number`, `chunk_index`
   - ✅ `Book` model with `status`, but missing `processing_mode` field

2. **Services**:
   - ✅ `pdf_service.py` - Main processing pipeline (OCR → chunk+embed)
   - ✅ `chunking_service.py` - Text splitting logic (`ChunkingService.split_text()`)
   - ✅ `ocr_service.py` - OCR processing
   - ✅ `GeminiEmbeddings` - Embedding generation

3. **Worker Infrastructure**:
   - ✅ ARQ workers with Redis (`worker.py`, `queue.py`)
   - ✅ Cron jobs: `rescue_stale_jobs`, `scheduled_gcs_sync`

### ❌ What Needs to Be Built

1. **New Database Tables:**
   - ❌ `batch_jobs` - Track Gemini Batch API submissions
   - ❌ `batch_requests` - Map individual requests to batch jobs

2. **New Fields:**
   - ❌ `books.processing_mode` - Choose batch vs realtime

3. **New Services:**
   - ❌ `gemini_batch_client.py` - Direct Google Gen AI SDK integration
   - ❌ `batch_service.py` - Batch orchestration logic

4. **New Cron Jobs:**
   - ❌ `submit_ocr_batch_job()` - Collect and submit OCR batches
   - ❌ `submit_embedding_batch_job()` - Collect and submit embedding batches
   - ❌ `poll_batch_jobs()` - Check batch completion

### 🔧 What Needs to Be Modified

1. **`pdf_service.py`:** (Phase 0 - CRITICAL)
   - **Split chunking from embedding for BOTH modes** (unified architecture)
   - ALL modes: create chunks with `embedding=NULL` first
   - Real-time: embed immediately after chunk creation
   - Batch: skip embedding, let batch cron handle it later
   - Add batch mode routing based on `processing_mode`

2. **`db/models.py`:**
   - Add new `BatchJob` and `BatchRequest` models
   - Extend `Book` model with `processing_mode`

### Key Architectural Change

**UNIFIED ARCHITECTURE** - Both modes use the same flow:

**Current (Combined):**
```
OCR → Chunk+Embed (atomic) → Chunks created WITH vectors → Mark indexed
```

**New (Unified Split for BOTH modes):**
```
OCR → Create chunks (embedding=NULL) → Embed (timing differs) → Chunks get vectors → Mark indexed

Where:
- Real-time mode: Embedding happens immediately after chunk creation (same transaction)
- Batch mode: Embedding happens later via batch cron (next batch cycle)
```

**Benefits of Unified Approach:**
- ✅ Single code path = easier to maintain
- ✅ Same database state for both modes (chunks always exist, may or may not have embeddings)
- ✅ Better testability (test chunking once, embedding once)
- ✅ Future flexibility (can re-embed without re-chunking)
- ✅ Gradual migration (refactor real-time first, add batch later)

## Edge Cases & Architectural Fixes

1. **Schema Optimization (`batch_requests` foreign key)**
   Instead of using `book_id` + `page_number` for OCR requests, use the existing `page_id INTEGER REFERENCES pages(id)`. This guarantees referential integrity and keeps queries simpler.

2. **The Book `batch_job_id` Field**
   Because requests naturally span multiple batches across a 1,000-request clump, a single book could be split across different batch jobs. Tracking `batch_job_id` on the `books` table is inherently flawed and has been dropped. Rely purely on joining `batch_requests` to see a book's active jobs.

3. **Re-indexing a Full Book (`/books/{id}/reindex`)**
   When an admin triggers a book re-index, the endpoint executes raw SQL to set `is_indexed = FALSE`. In the new architecture, we must explicitly `DELETE FROM chunks WHERE book_id = X` or `UPDATE chunks SET embedding = NULL` during this step. If old 768-D vectors remain on chunks, the batch embedding crawler won't detect them as "needing embed".

4. **Single-Page Updates (Critical UX Edge Cases)**

   There are TWO distinct scenarios for updating a single page:

   **4a. Text Edit (Manual Correction)**: `/books/{id}/pages/{page_num}/update`
   - Volunteer manually corrects OCR text in the UI
   - **Process**: Skip OCR → Delete old chunks → Create new chunks from edited text → Re-embed immediately
   - **Why real-time**: Instant feedback is crucial for editors
   - **Implementation**: API endpoint updates `page.text` directly, deletes old chunks, creates new chunks, embeds immediately
   - **No ARQ job needed**: This is a direct API call → database update → chunking → embedding (all synchronous)

   **4b. Re-OCR (User clicks "OCR Again")**: `/books/{id}/pages/{page_num}/reprocess`
   - User requests to re-run OCR on a page (e.g., better image uploaded)
   - **Process**: OCR → Chunk → Embed (full pipeline)
   - **Mode**: Can use `force_realtime=True` for instant results OR follow book's `processing_mode`
   - **Implementation**: Queue job with `process_pdf_task(book_id, page_id, force_realtime=True)` for real-time

5. **Idempotent Polling**
   The worker cron `poll_batch_jobs` runs hourly. If generating and writing result blobs takes time, a subsequent cron execution could try to pull and double-process the same output file. **Fix**: Update the `batch_jobs.status` to `'processing_results'` immediately when picked up to lock it.

### How Edge Cases Are Addressed in Implementation

**Note:** All edge cases have been considered and integrated into the implementation phases below. No separate tracking needed during execution.

| Edge Case | Phase | Implementation Location | Considered |
|-----------|-------|------------------------|------------|
| #1: Schema Optimization (page_id) | Phase 1 | Database migration, `batch_requests` table | ✅ Yes |
| #2: No batch_job_id field | Phase 1 | Database migration, `books` table extension | ✅ Yes |
| #3: Re-indexing clears embeddings | Phase 3 | `books.py` API endpoint `/books/{id}/reindex` | ✅ Yes |
| #4a: Text edit (manual correction) | Phase 0 | `books.py` API endpoint `/pages/{id}/update` | ✅ Yes |
| #4b: Re-OCR single page | Phase 2 | `pdf_service.py` process_pdf_task() | ✅ Yes |
| #5: Idempotent polling lock | Phase 2 | `batch_service.py` poll_batch_status() | ✅ Yes |

**Testing Strategy for Edge Cases:**
- Edge Case #1: Verify foreign key constraints work correctly
- Edge Case #2: Test querying book's batches via join (see query in schema section)
- Edge Case #3: Re-index a book and verify embeddings are cleared/NULL
- Edge Case #4a: Manually edit page text and verify instant re-chunking and re-embedding (synchronous API call)
- Edge Case #4b: Click "OCR Again" and verify real-time processing (even if book is in batch mode)
- Edge Case #5: Run poll cron twice simultaneously, verify no double-processing

## Implementation Strategy

### Batching Strategy: Request-Level Across Books

**Key Decision**: Batch individual requests across multiple books (not book-level batching).

**Two Types of Batching**:

1. **OCR Batching** - Operates on pages (before chunks exist)
   - Collect pending OCR pages from all books
   - Submit batch of page OCR requests
   - Store extracted text in pages table

2. **Embedding Batching** - Operates on chunks (after OCR completes)
   - OCR completes → create chunks → mark for embedding
   - Collect pending embedding chunks from all books
   - Submit batch of embedding requests
   - Store vectors in chunks table

**Rationale**:
- ✅ **Efficiency**: Batches fill up faster (up to 1000 requests)
- ✅ **Lower latency**: Don't wait to accumulate full books
- ✅ **Simpler logic**: Just collect pending requests and submit
- ✅ **Better resource utilization**: Maximize batch sizes quickly

**Processing Flow**:
1. **OCR Phase**: Pages → OCR Batch → Text extracted → Chunks created
2. **Embedding Phase**: Chunks → Embedding Batch → Vectors stored
3. **Completion**: Mark book complete when all chunks have embeddings

**Trade-off**: Book completion is incremental (requests finish as batches complete), but this is acceptable for non-real-time processing.

### Dual-Mode Processing Architecture

The system will support **two processing modes** for books:

1. **Batch Mode (default)**: Cost-optimized for bulk library processing
   - OCR and embeddings submitted as batch jobs to Gemini Batch API
   - 24-hour turnaround acceptable
   - 50% cost savings

2. **Real-time Mode**: Immediate processing for urgent uploads
   - Uses existing LangChain integration
   - Full cost, instant results
   - Opt-in via book configuration

### Data Flow

**Two-Phase Batch Processing** (OCR → Chunking → Embeddings)

```
Book Upload → Check Processing Mode (new field: book.processing_mode)
    │
    ├─ BATCH MODE (processing_mode='batch'):
    │
    │   PHASE 1: OCR Processing
    │   └─> Pages created with status='pending'
    │   └─> OCR batch cron (every 2 hours)
    │       └─> Collect pages WHERE status='pending' from ALL books (up to 1000)
    │       └─> Submit OCR batch job to Gemini API
    │       └─> Poll for completion (every hour)
    │       └─> Store OCR text in pages table, status='ocr_done'
    │       └─> Create chunks from extracted text (embedding=NULL) ← UNIFIED
    │       └─> Mark pages as status='chunked' (chunks exist with NULL embeddings)
    │
    │   PHASE 2: Embedding Processing
    │   └─> Embedding batch cron (every 2 hours)
    │       └─> Collect chunks WHERE embedding IS NULL from ALL books (up to 1000)
    │       └─> (Also: pages WHERE status='chunked' indicate chunks needing embeddings)
    │       └─> Submit embedding batch job to Gemini API
    │       └─> Poll for completion (every hour)
    │       └─> UPDATE chunks SET embedding=vector ← UNIFIED
    │       └─> Mark pages as status='indexed', is_indexed=True
    │       └─> Mark book status='ready' when all chunks embedded
    │
    └─ REAL-TIME MODE (processing_mode='realtime'):
        │
        └─> OCR completes (status='ocr_done')
        └─> Create chunks from text (embedding=NULL) ← UNIFIED (same code as batch!)
        └─> Mark pages status='chunked' (transiently, same code as batch!)
        └─> Embed chunks immediately (in same transaction)
        └─> UPDATE chunks SET embedding=vector ← UNIFIED (same code as batch!)
        └─> Mark pages status='indexed', is_indexed=True
```

**Key Insight:** Both modes use identical chunking and embedding logic. Only difference is WHEN embedding happens (immediate vs batched).

**Note**: Both OCR and embedding batches contain requests from multiple books. This maximizes batch efficiency and minimizes wait time.

## Database Schema Changes

### Current Implementation Status

**Existing Schema:**
- ✅ **Page** model exists with status field
  - **Current statuses:** `'pending', 'ocr_processing', 'ocr_done', 'indexing', 'indexed', 'error'`
  - **New unified flow:** `'pending', 'ocr_processing', 'ocr_done', 'chunked', 'indexed', 'error'`
  - **Change:** Replace `'indexing'` with `'chunked'` to represent "chunks created (embedding=NULL), waiting for embeddings"
- ✅ **Chunk** model exists with `embedding` field (Vector(768), nullable=True)
- ❌ **Chunk** model has NO status field (tracks pending via `embedding IS NULL`)
- ❌ **Book** model missing `processing_mode` field (needs to be added)
- ❌ **Batch tables** don't exist yet (need to create)

**Current Processing Flow:**
```
Book upload → Pages created (status='pending')
→ OCR processing (status='ocr_processing' → 'ocr_done')
→ Chunking + Embedding (combined step!)
→ Chunks created WITH embeddings immediately
→ Page marked (status='indexed', is_indexed=True)
→ Book status → 'ready'
```

**New Unified Processing Flow (Both Modes):**
```
Book upload → Pages created (status='pending')
→ OCR processing (status='ocr_processing' → 'ocr_done')
→ Chunking (status='chunked', chunks created with embedding=NULL)
→ Embedding (timing differs by mode)
→ Page marked (status='indexed', is_indexed=True)
→ Book status → 'ready'
```

**Key Status Milestones:**
- `'ocr_done'` → OCR complete, text stored
- `'chunked'` → Chunks created (embedding=NULL), waiting for embeddings
- `'indexed'` → Embeddings complete, page searchable

**Adaptation Needed for Batch API:**
Since current implementation combines chunking+embedding, we need to split it:
1. Create chunks WITHOUT embeddings (embedding=NULL), set page status='chunked'
2. Track chunks needing embedding via `embedding IS NULL`
3. Batch embed chunks, then UPDATE chunks SET embedding=vector, set page status='indexed'

### New Table: `batch_jobs`
Tracks Gemini Batch API job submissions and status.

**Note**: Each batch job contains requests from multiple books (pages for OCR, chunks for embeddings).

```sql
CREATE TABLE batch_jobs (
    id SERIAL PRIMARY KEY,
    batch_id VARCHAR(255) UNIQUE NOT NULL,  -- Gemini Batch API job ID
    batch_type VARCHAR(50) NOT NULL,        -- 'ocr', 'embeddings'
    status VARCHAR(50) NOT NULL,            -- Status values below
    book_ids TEXT[] NOT NULL,               -- Array of book IDs with requests in this batch
    request_count INTEGER DEFAULT 0,        -- Total number of requests (pages or chunks)
    retry_count INTEGER DEFAULT 0,          -- Number of retry attempts
    output_file_uri TEXT,                   -- GCS URI for results
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metadata JSONB,                         -- Request mapping data, retry info, success/failure counts
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_batch_jobs_status ON batch_jobs(status);
CREATE INDEX idx_batch_jobs_batch_id ON batch_jobs(batch_id);
CREATE INDEX idx_batch_jobs_retry_count ON batch_jobs(retry_count);

-- Status values:
-- 'pending' - Created, waiting for submission
-- 'submitted' - Sent to Gemini API
-- 'processing' - Gemini is processing
-- 'completed' - Gemini finished, ready to download
-- 'processing_results' - Worker is processing results (Edge Case #5 lock)
-- 'partial_success' - Some requests succeeded, some failed
-- 'failed' - Entire batch failed
-- 'failed_fallback_complete' - Failed, real-time fallback completed

-- Status flow: pending → submitted → processing → completed → processing_results → (done/partial_success/failed)
```

### New Table: `batch_requests`
Maps individual requests (OCR pages, embedding chunks) to batch jobs.

**Note**: Supports both page-level (OCR) and chunk-level (embeddings) batching.

**Current Schema Compatibility:**
- OCR requests: Use existing `pages.status='pending'` to identify
- Embedding requests: Use existing `chunks.embedding IS NULL` to identify chunks needing embedding

**Schema Optimization (Edge Case #1):**
- ✅ Use `page_id INTEGER REFERENCES pages(id)` for OCR requests (guarantees referential integrity)
- ❌ Don't use `book_id + page_number` (weaker integrity, more complex queries)

```sql
CREATE TABLE batch_requests (
    id SERIAL PRIMARY KEY,
    batch_job_id INTEGER REFERENCES batch_jobs(id) ON DELETE CASCADE,

    -- For OCR requests (foreign key to pages table)
    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,

    -- For embedding requests (foreign key to chunks table)
    chunk_id INTEGER REFERENCES chunks(id) ON DELETE CASCADE,

    request_type VARCHAR(50) NOT NULL,      -- 'ocr', 'embedding'
    request_index INTEGER NOT NULL,         -- Position in batch for result mapping
    request_payload JSONB NOT NULL,         -- Original request data
    response_payload JSONB,                 -- Response when retrieved
    status VARCHAR(50) DEFAULT 'pending',   -- 'pending', 'completed', 'failed'
    retry_count INTEGER DEFAULT 0,          -- Track retries for this specific request
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraint: OCR requests need page_id, embedding requests need chunk_id
    CONSTRAINT chk_request_reference CHECK (
        (request_type = 'ocr' AND page_id IS NOT NULL AND chunk_id IS NULL) OR
        (request_type = 'embedding' AND chunk_id IS NOT NULL AND page_id IS NULL)
    )
);

CREATE INDEX idx_batch_requests_batch_job ON batch_requests(batch_job_id);
CREATE INDEX idx_batch_requests_page ON batch_requests(page_id);
CREATE INDEX idx_batch_requests_chunk ON batch_requests(chunk_id);
CREATE INDEX idx_batch_requests_status ON batch_requests(status);
CREATE INDEX idx_batch_requests_retry_count ON batch_requests(retry_count);
```

### Extend `books` Table

**Current Status:** Book model exists but missing these fields.

**Edge Case #2:** Do NOT add `batch_job_id` field to books table. Books naturally span multiple batches (1000-request limit), so tracking a single job ID is inherently flawed. To see a book's active batch jobs, join through `batch_requests`.

```sql
-- NEW COLUMN: Choose processing mode per book
ALTER TABLE books ADD COLUMN processing_mode VARCHAR(20) DEFAULT 'batch';
-- Values: 'batch' (default, cost-optimized), 'realtime' (urgent)
-- NOTE: Start with 'realtime' default for safety, switch to 'batch' after testing
```

**Query to find active batch jobs for a book:**
```sql
SELECT DISTINCT bj.*
FROM batch_jobs bj
JOIN batch_requests br ON br.batch_job_id = bj.id
JOIN pages p ON br.page_id = p.id
WHERE p.book_id = 'book_id_here' AND bj.status IN ('pending', 'submitted', 'processing');
```

**Current Book Statuses (unchanged):**
- 'uploading', 'pending', 'ocr_processing', 'ocr_done', 'indexing', 'ready', 'error'

### Configuration in `system_configs`

```sql
INSERT INTO system_configs (key, value, description) VALUES
('batch_processing_enabled', 'true', 'Enable Gemini Batch API processing'),
('batch_min_pages', '20', 'Minimum pages to use batch mode'),
('batch_polling_interval_minutes', '60', 'How often to poll for batch results'),
('batch_max_requests_per_job', '1000', 'Maximum requests per batch job'),
('batch_submission_interval_minutes', '120', 'How often to collect and submit batches');
```

## Critical Files to Create/Modify

### New Files

1. **`/packages/backend-core/app/services/gemini_batch_client.py`**
   - Direct Google Gen AI SDK integration (bypasses LangChain)
   - Methods: `create_batch_job()`, `get_batch_status()`, `download_results()`
   - Handles batch submission and result retrieval

2. **`/packages/backend-core/app/services/batch_service.py`**
   - Core batch orchestration service
   - Methods:
     - `collect_ocr_requests()` - Find pending OCR pages across ALL books
     - `collect_embedding_requests()` - Find pending embedding chunks across ALL books
     - `submit_batch_job()` - Submit collected requests to Gemini Batch API
     - `poll_batch_status()` - Check batch completion with idempotent locking
       - **Edge Case #5:** Lock job immediately to prevent double-processing
       ```python
       # UPDATE batch_jobs SET status='processing_results' WHERE id=? AND status='completed'
       # Only process if update succeeds (prevents race condition)
       ```
     - `process_batch_results()` - Update pages (for OCR) or chunks (for embeddings) with results
     - `create_chunks_from_ocr()` - Create chunk records after OCR completes
     - `handle_batch_failure()` - Error handling and fallback to real-time
     - `mark_book_complete()` - Mark book as complete when all chunks have embeddings

3. **`/packages/backend-core/alembic/versions/XXX_add_batch_tables.py`**
   - Alembic migration for new tables and columns
   - Creates `batch_jobs`, `batch_requests`
   - Alters `books` table

### Files to Modify

4. **`/packages/backend-core/app/services/pdf_service.py`** ✅ EXISTS
   - **Current flow:** OCR pages → chunk+embed together → mark indexed
   - **Modifications needed:**
     - Add check for `book.processing_mode` at start of `process_pdf_task()`
     - If `processing_mode='batch'`: create pages with `status='pending'` and return early
     - If `processing_mode='realtime'`: continue with existing flow
     - **Split chunking from embedding:** After OCR in batch mode, create chunks with `embedding=NULL`
     - Embedding phase will separately collect chunks WHERE `embedding IS NULL`
     - **Edge Case #4a: Text Edit (Manual Correction)** - Direct API endpoint, no ARQ job:
       ```python
       # In /packages/backend-core/app/api/endpoints/books.py
       @router.put("/books/{book_id}/pages/{page_id}/update")
       async def update_page_text(book_id: str, page_id: int, text: str):
           page = await get_page(page_id)
           page.text = text  # Update text directly

           # Delete old chunks
           await session.execute(delete(Chunk).where(Chunk.page_id == page_id))

           # Create new chunks from edited text
           chunks_text = chunking_service.split_text(text)
           chunk_records = []
           for idx, chunk_text in enumerate(chunks_text):
               chunk = Chunk(page_id=page_id, text=chunk_text, embedding=None)
               session.add(chunk)
               chunk_records.append(chunk)

           await session.flush()

           # Embed immediately (synchronous, instant feedback)
           vectors = await embedder.aembed_documents([c.text for c in chunk_records])
           for chunk, vector in zip(chunk_records, vectors):
               chunk.embedding = vector

           page.status = 'indexed'
           await session.commit()
           return {"status": "success", "chunks_updated": len(chunk_records)}
       ```

     - **Edge Case #4b: Re-OCR Single Page** - ARQ task with force_realtime:
       ```python
       # Modify ARQ task signature to accept force_realtime parameter
       async def process_pdf_task(ctx, book_id: str, page_id: Optional[int] = None, force_realtime: bool = False):
           book = await get_book(book_id)

           # Determine effective mode
           effective_mode = 'realtime' if force_realtime else book.processing_mode

           if effective_mode == 'batch':
               # ... Process as batch
           else:
               # ... Process in real-time (OCR → Chunk → Embed)
       ```

5. **`/packages/backend-core/app/queue.py`** ✅ EXISTS
   - **Current functions:** `process_pdf_job`, `scheduled_gcs_sync`
   - **Edge Case #4a (Text Edit):** No queue modification needed - handled synchronously in API endpoint
   - **Edge Case #4b (Re-OCR):** Pass `force_realtime: bool` kwarg in `enqueue_pdf_processing` for "OCR Again" feature
   - **Add new ARQ job functions:**
     - `submit_ocr_batch_job()` - Cron job to collect pending OCR pages and submit batch
     - `submit_embedding_batch_job()` - Cron job to collect pending chunks and submit batch
     - `poll_batch_jobs()` - Cron job to check batch status and process results

6. **`/packages/backend-core/app/worker.py`** ✅ EXISTS
   - **Current cron jobs:** `rescue_stale_jobs` (every 30 min), `scheduled_gcs_sync` (every 30 min)
   - **Add new cron jobs to WorkerSettings:**
     - `submit_ocr_batch_job` - runs every 2 hours
     - `submit_embedding_batch_job` - runs every 2 hours
     - `poll_batch_jobs` - runs every hour

7. **`/packages/backend-core/app/core/config.py`**
   - Add batch processing configuration:
     - `batch_processing_enabled: bool`
     - `batch_min_pages: int`
     - `batch_polling_interval_minutes: int`
     - `batch_max_requests_per_job: int`
     - `batch_submission_interval_minutes: int`
     - `gemini_batch_model: str`

8. **`/packages/backend-core/app/db/models.py`**
   - Add SQLAlchemy models for `BatchJob` and `BatchRequest`
   - Extend `Book` model with `processing_mode` field

9. **`requirements.txt` (or equivalent)**
   - Add dependency: `google-genai>=0.8.0` (or latest version)

### Optional Enhancement Files

10. **`/packages/backend-core/app/api/endpoints/admin.py`** (if exists)
    - Add admin endpoints:
      - `GET /api/admin/batch-jobs` - List batch jobs
      - `GET /api/admin/batch-jobs/{id}` - Batch job details
      - `POST /api/admin/batch-jobs/{id}/retry` - Retry failed batch

11. **`/packages/backend-core/app/api/endpoints/books.py`** ✅ EXISTS

    **Edge Case #3: Re-indexing Handler**
    - Modify `/books/{id}/reindex` endpoint to handle batch mode:
      ```python
      # Current: UPDATE pages SET is_indexed = FALSE WHERE book_id = ?
      # Batch mode fix: Also clear embeddings to trigger batch re-embedding
      DELETE FROM chunks WHERE book_id = ?
      # OR: UPDATE chunks SET embedding = NULL WHERE book_id = ?
      # This ensures batch embedding crawler detects chunks needing embedding
      ```

    **Edge Case #4a: Text Edit (Manual Correction)**
    - Add or modify `PUT /books/{book_id}/pages/{page_id}/update` endpoint:
      - Update page.text directly (no OCR)
      - Delete old chunks for this page
      - Create new chunks from edited text (embedding=NULL)
      - Embed immediately (synchronous, instant feedback)
      - Update page.status='indexed'
      - Return success response

    **Edge Case #4b: Re-OCR Single Page**
    - Add `POST /books/{book_id}/pages/{page_id}/reprocess` endpoint:
      - Queue job with `force_realtime=True`
      - Run full OCR → Chunk → Embed pipeline
      - Ensure real-time processing for instant feedback

### Frontend/UI Changes

The frontend needs to be updated to reflect the new batch processing architecture and provide visibility into the new processing modes.

**Required UI Updates:**

12. **Page Status Display** - `apps/frontend/src/components/`
    - Update page status badges/indicators to handle new `'chunked'` status:
      ```typescript
      // Old statuses: 'pending', 'ocr_processing', 'ocr_done', 'indexing', 'indexed', 'error'
      // New statuses: 'pending', 'ocr_processing', 'ocr_done', 'chunked', 'indexed', 'error'

      const PAGE_STATUS_LABELS = {
        pending: 'Waiting for OCR',
        ocr_processing: 'Processing OCR',
        ocr_done: 'OCR Complete',
        chunked: 'Waiting for Embedding',  // NEW
        indexed: 'Ready',
        error: 'Error'
      }
      ```
    - Update color schemes and icons for the new status
    - Show clear visual distinction between `'chunked'` (waiting) and `'indexed'` (complete)

13. **Book Processing Mode Display** - Book detail/list views
    - Show `processing_mode` field on book cards/details:
      - Badge: "Batch Processing" (blue) or "Real-time" (green)
      - Tooltip explaining the difference (cost vs speed)
    - Display estimated completion time:
      - Batch mode: "Processing in batch (up to 24 hours)"
      - Real-time mode: "Processing immediately"

14. **Book Upload Form** - Admin book upload interface
    - Add processing mode selector (admin only):
      ```typescript
      <Select name="processing_mode" defaultValue="batch">
        <option value="batch">Batch Processing (50% cheaper, 24-hour turnaround)</option>
        <option value="realtime">Real-time (Instant, standard cost)</option>
      </Select>
      ```
    - Auto-select batch mode for books with > 50 pages
    - Show cost estimate based on page count and selected mode

15. **Progress Indicators** - Book processing status
    - Update progress bars to show three phases:
      - OCR: `pending` → `ocr_processing` → `ocr_done`
      - Chunking: `ocr_done` → `chunked`
      - Embedding: `chunked` → `indexed`
    - For batch mode, show "Waiting for batch" message when appropriate
    - Display: "X/Y pages indexed" instead of just boolean status

16. **Localization Updates** - `apps/frontend/src/locales/`
    - Add translations for new statuses and messages:
      ```json
      {
        "page.status.chunked": "Waiting for Embedding",
        "book.processing_mode.batch": "Batch Processing",
        "book.processing_mode.realtime": "Real-time",
        "book.batch_notice": "This book is being processed in batch mode. It may take up to 24 hours to complete.",
        "book.batch_cost_savings": "Processing in batch mode saves 50% on API costs"
      }
      ```

**Optional Admin Dashboard Enhancements:**

17. **Batch Job Monitor Dashboard** - `apps/frontend/src/components/admin/`
    - New component: `BatchJobMonitor.tsx`
    - Features:
      - List active/recent batch jobs with status
      - Show batch type (OCR vs Embeddings)
      - Display request counts, success/failure rates
      - Retry failed batches button
      - Filter by status, type, date range
    - API integration:
      - `GET /api/admin/batch-jobs` - List batch jobs
      - `GET /api/admin/batch-jobs/{id}` - Job details
      - `POST /api/admin/batch-jobs/{id}/retry` - Retry failed job

18. **Batch Processing Statistics** - Add to existing admin stats panel
    - Total books processed in batch vs real-time
    - Average batch completion time
    - Cost savings estimate (batch vs real-time)
    - Batch success rate (percentage)
    - Current queue depth (pending batches)

19. **Book Management Enhancements** - Book admin interface
    - Add "Switch to Real-time" action for stuck batch books
    - Show batch job history for each book
    - Display which batch jobs a book's pages/chunks are in
    - Manual re-index trigger with mode selection

**User-Facing Information:**

20. **User Expectations Management**
    - On book detail page, show clear messaging:
      - Batch: "This book is being processed in the background. Check back in a few hours."
      - Real-time: "This book is being processed immediately."
    - Add FAQ section explaining batch vs real-time processing
    - Show estimated completion time on book cards

**API Response Changes:**

21. **Update API Responses** - Include new fields in book/page responses:
    ```typescript
    interface Book {
      // ... existing fields
      processing_mode: 'batch' | 'realtime';
      pages_chunked: number;    // Count of pages with status='chunked'
      pages_indexed: number;    // Count of pages with status='indexed'
      estimated_completion?: Date; // For batch books
    }

    interface Page {
      // ... existing fields
      status: 'pending' | 'ocr_processing' | 'ocr_done' | 'chunked' | 'indexed' | 'error';
    }
    ```

**Implementation Priority:**

- **Must Have (Phase 2-3):** Items 12-16 (status display, basic UI updates)
- **Nice to Have (Phase 4):** Items 17-21 (admin dashboard, advanced features)
- **Can Defer:** Advanced batch monitoring, detailed statistics

**Testing Requirements:**

- Verify UI displays all new page statuses correctly
- Test processing mode selector on book upload
- Verify localization works for all new strings (English, Uyghur)
- Test progress indicators for both batch and real-time modes
- Verify admin dashboard shows accurate batch job data

## Implementation Phases

### Phase 0: Unified Architecture Refactoring (Week 1)
**Goal**: Refactor real-time mode to use split chunking/embedding (prepare for batch mode)

**Why First?**
- Establishes unified code path for both modes
- Tests split approach in production with real-time mode
- De-risks batch implementation (chunking logic already proven)
- Smaller, safer change (no new tables, just refactoring)

**Current State:**
- ✅ Real-time mode works: OCR → chunk+embed together → indexed
- ❌ Chunking and embedding tightly coupled

**Tasks**:
1. **Refactor `pdf_service.py`** to split chunking from embedding:
   ```python
   # BEFORE (current):
   async def process_after_ocr(page, text):
       chunks = chunking_service.split_text(text)
       vectors = await embedder.aembed_documents(chunks)
       for chunk, vector in zip(chunks, vectors):
           Chunk(text=chunk, embedding=vector)  # Created with vector

   # AFTER (unified - Phase 0 version for real-time only):
   async def process_after_ocr(page, text):
       # Step 1: Always create chunks with NULL embeddings
       chunks_text = chunking_service.split_text(text)
       chunk_records = []
       for idx, chunk_text in enumerate(chunks_text):
           chunk = Chunk(
               book_id=page.book_id,
               page_number=page.page_number,
               chunk_index=idx,
               text=chunk_text,
               embedding=None  # ALWAYS NULL initially
           )
           session.add(chunk)
           chunk_records.append(chunk)

       await session.flush()  # Get chunk IDs

       # Mark page as chunked (chunks created, no embeddings yet)
       page.status = 'chunked'
       await session.flush()

       # Step 2: For real-time mode, embed immediately
       # NOTE: Phase 2 will modify this to check mode and conditionally embed
       vectors = await embedder.aembed_documents([c.text for c in chunk_records])
       for chunk, vector in zip(chunk_records, vectors):
           chunk.embedding = vector

       # Mark page as indexed (embeddings complete)
       page.status = 'indexed'
       page.is_indexed = True
       await session.flush()

   # FUTURE (Phase 2): Add embed_immediately parameter
   # async def process_after_ocr(page, text, embed_immediately=True):
   #     ... create chunks ...
   #     if embed_immediately:
   #         ... embed chunks ...
   #     else:
   #         return  # Chunks stay status='chunked', batch cron will embed later
   ```

2. **Implement Edge Case #4a** - Add text edit endpoint in `books.py`:
   - `PUT /books/{book_id}/pages/{page_id}/update`
   - Uses the same chunking/embedding logic from task #1
   - Provides instant feedback for volunteer editors
   - See detailed code example in "Files to Modify" section (item #11)

3. **Test thoroughly:**
   - Process 10-20 test books in staging
   - Verify chunks created with NULL then immediately filled
   - Verify search quality unchanged
   - Verify no performance regression
   - Test text edit endpoint (Edge Case #4a): edit page text, verify instant re-chunking and embedding

4. **Deploy to production:**
   - Monitor for errors
   - Verify all new books process correctly
   - Rollback plan: revert to previous pdf_service.py

**Deliverables**:
- ✅ Real-time mode uses split chunking/embedding
- ✅ Production tested and stable
- ✅ Unified code path ready for batch mode

**Verification**:
```sql
-- Verify chunks are being created correctly
SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;  -- Should equal total chunks
SELECT COUNT(*) FROM chunks WHERE embedding IS NULL;       -- Should be 0 (all embedded immediately)
```

**Risk**: Low - just refactoring, same functionality
**Rollback**: Revert single file (`pdf_service.py`)

---

### Phase 1: Batch Infrastructure (Week 2)
**Goal**: Add batch API infrastructure (tables, client, services)

**Current State:**
- ✅ ARQ worker infrastructure exists
- ✅ Database models framework exists
- ✅ Configuration system exists (`app/core/config.py`)
- ❌ No batch API code exists yet

**Tasks**:
1. **Dependencies:** Add `google-genai>=0.8.0` to requirements.txt
2. **Database Migration:** Create Alembic migration
   - Add `batch_jobs` table with status including 'processing_results' (Edge Case #5)
   - Add `batch_requests` table with `page_id` and `chunk_id` foreign keys (Edge Case #1)
   - Add `books.processing_mode` field (default='realtime' for safety)
   - **Update page status enum:** Change 'indexing' → 'chunked' (or add 'chunked' if using VARCHAR)
   - **DO NOT** add `books.batch_job_id` field (Edge Case #2: books span multiple batches)
   - Migration strategy: If pages currently have status='indexing', migrate to 'chunked' OR keep both during transition
   - Run migration: `alembic upgrade head`
3. **Configuration:** Update `app/core/config.py`
   - Add `batch_processing_enabled: bool = False`
   - Add `batch_min_pages: int = 50`
   - Add `batch_max_requests_per_job: int = 1000`
   - Add `gemini_batch_model: str = "gemini-2.0-flash"`
4. **Create Services:**
   - `app/services/gemini_batch_client.py` - Direct SDK integration
     - Methods: `create_batch_job()`, `get_batch_status()`, `download_results()`
   - `app/services/batch_service.py` - Orchestration logic (skeleton)
5. **Create Models:** Update `app/db/models.py`
   - Add `BatchJob` SQLAlchemy model
   - Add `BatchRequest` SQLAlchemy model
6. **Unit Tests:** `tests/test_batch_client.py` (mock API responses)

**Deliverables**:
- ✅ Working batch submission to Gemini API (tested manually with small batch)
- ✅ Database schema in place and migrated
- ✅ Configuration framework ready
- ✅ No production impact (batch_processing_enabled=False)

**Verification**:
```bash
# Test database migration
alembic upgrade head
# Verify tables created
psql -c "\\d batch_jobs"
# Test batch client manually
python -m app.services.gemini_batch_client
```

**Risk**: None - all changes are additive, no production impact

### Phase 2: OCR Batch Processing (Week 3)
**Goal**: Enable batch mode for OCR with real-time fallback

**Current State (After Phase 0):**
- ✅ **Unified architecture in place:** Both modes create chunks with `embedding=NULL` first
- ✅ `ChunkingService` exists and is used by both modes
- ✅ Real-time mode: chunks created → embedded immediately
- ❌ Batch mode: not yet implemented

**Tasks**:
1. Add `processing_mode` field to Book model (already done in Phase 1 migration)
2. Implement OCR request collection in `BatchService`
   - Query: `SELECT p.id FROM pages p JOIN books b ON p.book_id = b.id WHERE p.status='pending' AND b.processing_mode='batch'`
   - Use `page_id` for batch_requests (Edge Case #1: referential integrity)
3. **Modify `process_pdf_task()` for batch routing:**
   ```python
   async def process_pdf_task(book_id: str):
       book = await get_book(book_id)

       if book.processing_mode == 'batch':
           # Just create pages, don't process
           await create_pages_from_pdf(book_id)
           # Pages stay status='pending', batch cron will pick them up
           return

       # Real-time mode: continue with OCR
       await perform_ocr(book_id)
       # Chunking happens in process_after_ocr() (Phase 0 refactored code)
       # Embedding happens immediately (Phase 0 refactored code)
   ```
   - Implement single-page re-OCR with force_realtime (Edge Case #4b)
   - Note: Edge Case #4a (text edit) is handled in API endpoint, not here
4. **Chunking after batch OCR:** Modify `process_after_ocr()` from Phase 0
   - Add `embed_immediately` parameter (default=True for backward compatibility)
   - When batch OCR completes, call `process_after_ocr(page, text, embed_immediately=False)`
   - When real-time processes, call `process_after_ocr(page, text, embed_immediately=True)`
   - If `embed_immediately=False`: chunks created with `embedding=NULL`, page stays `status='chunked'`
   - Batch embedding cron will process these chunks later
5. Create batch submission cron job (`submit_ocr_batch_job`)
6. Create batch polling cron job (`poll_batch_jobs`)
   - Implement idempotent locking (Edge Case #5: status='processing_results')
7. Implement result processing: update `pages.text` and `pages.status='ocr_done'`
8. Add error handling and fallback to real-time
9. **Frontend Updates (Required):**
   - Update page status display to handle `'chunked'` status
   - Add `processing_mode` badge to book cards/details
   - Update localization files with new status labels
   - Update API responses to include `processing_mode` field
10. Test with small books (10-20 pages)

**Processing Flow**:
```
Pages created status='pending' → OCR batch → Text extracted → status='ocr_done'
→ Chunks created (embedding=NULL) → status='chunked' → Ready for embedding batch
```

**Configuration**:
```python
# Conservative defaults for gradual rollout
batch_processing_enabled = False  # Enable manually per book initially
batch_min_pages = 50              # Only large books use batch mode
```

**Testing**:
- Mark 2-3 test books with `processing_mode='batch'`
- Monitor batch submission and retrieval
- Verify chunks are created after OCR completes
- Compare OCR quality with real-time mode
- Measure actual cost savings

**Deliverable**: OCR batching works end-to-end, chunks ready for embedding

**Rollback**: Set `batch_processing_enabled=false` in config

### Phase 3: Embeddings Batch Processing (Week 4)
**Goal**: Enable batch mode for embeddings

**Current State (After Phase 0-2):**
- ✅ **Unified embedding logic:** Real-time and batch use SAME embedding code
- ✅ Chunks table exists with `embedding Vector(768)` field (nullable)
- ✅ `GeminiEmbeddings` service exists in `app/langchain/models.py`
- ✅ Batch OCR working (Phase 2), chunks created with `embedding=NULL`
- ❌ Batch embedding: not yet implemented

**Tasks**:
1. Implement embedding request collection in `BatchService`
   - Query: `SELECT c.id FROM chunks c JOIN books b ON c.book_id = b.id WHERE c.embedding IS NULL AND b.processing_mode='batch'`
   - Use `chunk_id` for batch_requests (Edge Case #1: referential integrity)
2. Create batch submission cron job (`submit_embedding_batch_job`)
3. Process embedding results and UPDATE `chunks.embedding` with vectors
   - Implement idempotent processing (Edge Case #5: check status lock)
4. After chunks embedded, update `pages.status='indexed'` and `pages.is_indexed=True`
5. Mark books `status='ready'` when all chunks have embeddings
6. **Handle re-indexing** (Edge Case #3): Ensure re-index endpoint clears embeddings
7. Test embedding quality and search accuracy
8. Verify search results match real-time mode quality
9. **Test single-page edits** (Edge Case #4): Verify real-time embedding for manual corrections

**Processing Flow**:
```
Pages WHERE status='chunked' (chunks with embedding IS NULL) → Embedding batch (up to 1000 chunks)
→ UPDATE chunks SET embedding=vector → pages.status='indexed', is_indexed=True → book.status='ready'
```

**Key Points**:
- Chunks already exist in database (created after OCR in Phase 2 with `embedding=NULL`)
- Batch requests reference `chunk_id` directly
- Embedding batches contain chunks from multiple books for efficiency
- Book is "complete" when: `SELECT COUNT(*) FROM chunks WHERE book_id=? AND embedding IS NULL` = 0

**Testing**:
- Verify chunks are embedded correctly (vector dimension = 768)
- Compare search quality with real-time embeddings (semantic search)
- Test cross-book chunk batching
- Verify `is_indexed` flag propagates correctly

**Frontend Updates (Required):**
- Update progress indicators to show three-phase processing (OCR → Chunking → Embedding)
- Add book upload form with processing mode selector (admin)
- Show estimated completion time for batch books
- Update page detail views with new status flow

**Deliverable**: End-to-end batch processing (OCR → Chunks → Embeddings) working

### Phase 4: Monitoring & Optimization (Week 5-6)
**Goal**: Production-ready with full observability

**Tasks**:
1. **Backend Metrics Tracking:**
   - Batch submission rate
   - Average batch completion time
   - Cost savings (estimated)
   - Failure rates
   - Quality metrics
2. **Admin API Endpoints:**
   - `GET /api/admin/batch-jobs` - List batch jobs
   - `GET /api/admin/batch-jobs/{id}` - Job details
   - `POST /api/admin/batch-jobs/{id}/retry` - Retry failed batch
   - `GET /api/admin/batch-stats` - Statistics and cost savings
3. **Frontend Admin Dashboard (Optional):**
   - Batch job monitoring interface (`BatchJobMonitor.tsx`)
   - Batch processing statistics panel
   - Book management enhancements (switch modes, view batch history)
   - Cost savings visualization
4. Implement alerting for stuck batches (>48 hours)
5. Optimize batch sizes based on performance data
6. Document operational procedures
7. **Deployment:**
   - Update frontend: `./rebuild-and-restart.sh frontend`
   - Update backend: `./rebuild-and-restart.sh backend`
   - Update worker: `./rebuild-and-restart.sh worker`

**Deliverables**:
- Admin API endpoints for batch monitoring
- Automated alerts for failures
- Cost savings dashboard (frontend + backend)
- Full UI support for batch processing
- Production-ready monitoring

## Error Handling & Resilience

### Failure Scenarios & Handling

#### 1. OCR Batch Failures

**Scenario A: Entire Batch Fails (Network/API Error)**
```python
# In batch_service.py - handle_batch_failure()
if batch_job.status == 'failed' and batch_job.batch_type == 'ocr':
    # Get all pending pages from this batch
    failed_pages = await get_pages_from_batch(batch_job.id)

    # Mark batch_requests as failed
    await update_batch_requests_status(batch_job.id, 'failed')

    # Decision tree:
    if batch_job.retry_count < 3:
        # Retry: Create new batch job with same pages
        await resubmit_batch(failed_pages, delay=exponential_backoff(retry_count))
    else:
        # Fallback: Queue pages for real-time OCR
        for page in failed_pages:
            await enqueue_realtime_ocr(page.id)
            await update_page_status(page.id, 'pending')  # Will be picked up by real-time
```

**Scenario B: Partial Batch Failure (Some Pages OCR Failed)**
```python
# In batch_service.py - process_batch_results()
for request in batch_requests:
    if request.response_payload.get('error'):
        # Individual page failed OCR
        await update_batch_request(request.id, status='failed', error=error_msg)
        await update_page_status(request.page_id, status='error', error=error_msg)

        # Automatic retry for transient errors
        if is_transient_error(error_msg) and request.retry_count < 2:
            # Re-queue for next OCR batch
            await update_page_status(request.page_id, 'pending')
        else:
            # Mark for manual review or real-time retry
            await log_ocr_failure(request.page_id, error_msg)
    else:
        # Success: Store OCR text
        await update_page_text(request.page_id, text=response.text, status='ocr_done')
        await create_chunks_from_text(request.page_id, response.text)
```

**OCR Error Types & Actions:**
| Error Type | Retry Strategy | Fallback |
|------------|---------------|----------|
| Network timeout | ✅ Retry batch up to 3x | Real-time OCR |
| API rate limit | ✅ Retry with backoff | Wait and retry |
| Invalid image format | ❌ No retry | Mark as error, alert admin |
| OCR confidence too low | ✅ Retry once | Keep low-confidence text, flag for review |
| API quota exceeded | ❌ No retry | Pause batching, alert admin |

#### 2. Embedding Batch Failures

**Scenario A: Entire Batch Fails**
```python
# In batch_service.py - handle_batch_failure()
if batch_job.status == 'failed' and batch_job.batch_type == 'embeddings':
    failed_chunks = await get_chunks_from_batch(batch_job.id)

    await update_batch_requests_status(batch_job.id, 'failed')

    if batch_job.retry_count < 3:
        # Retry: Chunks still have embedding=NULL, will be picked up
        await resubmit_batch(failed_chunks, delay=exponential_backoff(retry_count))
    else:
        # Fallback: Real-time embedding
        for chunk in failed_chunks:
            await enqueue_realtime_embedding(chunk.id)
```

**Scenario B: Partial Batch Failure (Some Chunks Failed)**
```python
# In batch_service.py - process_batch_results()
for request in batch_requests:
    if request.response_payload.get('error'):
        # Individual chunk failed embedding
        await update_batch_request(request.id, status='failed', error=error_msg)
        # Chunk.embedding remains NULL, will be retried in next batch

        if request.retry_count > 2:
            # Too many retries, try real-time
            await enqueue_realtime_embedding(request.chunk_id)
    else:
        # Success: Store embedding vector
        await update_chunk_embedding(request.chunk_id, embedding=response.vector)
        await check_and_mark_page_indexed(request.chunk_id)
```

**Embedding Error Types & Actions:**
| Error Type | Retry Strategy | Fallback |
|------------|---------------|----------|
| Network timeout | ✅ Retry batch up to 3x | Real-time embedding |
| Text too long | ❌ No retry | Split chunk, re-submit |
| Invalid characters | ❌ No retry | Clean text, re-submit |
| Model error | ✅ Retry with different model | Real-time with fallback model |

#### 3. Partial Success Handling

**Key Principle:** Never lose progress when batch partially succeeds.

```python
# Process results incrementally
async def process_batch_results(batch_job_id: int):
    # Lock job to prevent double-processing (Edge Case #5)
    locked = await lock_batch_job(batch_job_id, status='processing_results')
    if not locked:
        return  # Another worker is processing

    try:
        results = await download_batch_results(batch_job_id)

        success_count = 0
        failure_count = 0

        for idx, result in enumerate(results):
            request = await get_batch_request_by_index(batch_job_id, idx)

            if result.success:
                await process_successful_request(request, result)
                success_count += 1
            else:
                await process_failed_request(request, result.error)
                failure_count += 1

        # Update batch job status
        if failure_count == 0:
            await update_batch_job(batch_job_id, status='completed',
                                  metadata={'success': success_count})
        elif success_count > 0:
            # Partial success
            await update_batch_job(batch_job_id, status='partial_success',
                                  metadata={'success': success_count, 'failed': failure_count})
        else:
            await update_batch_job(batch_job_id, status='failed',
                                  error_message=f'{failure_count} requests failed')
    finally:
        await unlock_batch_job(batch_job_id)
```

### Circuit Breaker Integration

**Current Implementation:** The system already has `_TEXT_BREAKER` and `_EMBED_BREAKER`.

**Add Batch Breaker:**
```python
# In app/langchain/models.py or app/services/batch_service.py
from app.utils.circuit_breaker import CircuitBreaker

_BATCH_BREAKER = CircuitBreaker(
    failure_threshold=5,      # Open after 5 consecutive failures
    recovery_timeout=300,     # 5 minutes
    expected_exception=Exception
)

async def submit_batch_with_breaker(batch_type: str, requests: list):
    try:
        result = await _BATCH_BREAKER.call(submit_batch_job, batch_type, requests)
        return result
    except CircuitBreakerOpen:
        # Batch API is down, fallback to real-time
        logger.warning(f"Batch API circuit breaker open, falling back to real-time for {len(requests)} requests")
        for request in requests:
            await enqueue_realtime_processing(request)
```

### Retry Strategy

**Exponential Backoff Implementation:**
```python
def exponential_backoff(retry_count: int, base_delay: int = 60) -> int:
    """Calculate retry delay in seconds"""
    return min(base_delay * (2 ** retry_count), 3600)  # Max 1 hour

# Usage
delay = exponential_backoff(batch_job.retry_count)  # 60s, 120s, 240s, 480s...
```

**Batch Submission Failures**:
- Retry up to 3 times with exponential backoff (60s, 120s, 240s)
- Track retry count in `batch_jobs.metadata`
- If all retries fail, mark pages/chunks for real-time processing
- Alert admin after 3rd failure

**Batch Polling Failures**:
- Continue polling for up to 48 hours
- After timeout, mark as failed and alert admin
- Optionally trigger real-time processing for critical books
- Log timeout in `batch_jobs.error_message`

**Individual Request Failures**:
- Extract error from batch response
- Mark specific `batch_requests` as 'failed' with error message
- Pages/chunks remain in 'pending' state (for OCR) or keep `embedding=NULL` (for embeddings)
- Automatically retry in next batch cycle (up to 2 more times)
- After 3 total attempts, escalate to real-time or manual review

### Fallback Mechanism

```python
async def handle_batch_failure(batch_job_id: int):
    """Handle failed batch jobs with intelligent fallback"""
    batch_job = await get_batch_job(batch_job_id)

    # Check if should retry or fallback
    if batch_job.retry_count < 3 and is_retriable_error(batch_job.error_message):
        # Retry the batch
        await retry_batch_job(batch_job)
        return

    # Fallback to real-time processing
    if batch_job.batch_type == 'ocr':
        pending_pages = await get_pending_pages_from_batch(batch_job_id)
        for page in pending_pages:
            logger.info(f"Falling back to real-time OCR for page {page.id}")
            await enqueue_realtime_ocr_task(page.id)

    elif batch_job.batch_type == 'embeddings':
        pending_chunks = await get_pending_chunks_from_batch(batch_job_id)
        for chunk in pending_chunks:
            logger.info(f"Falling back to real-time embedding for chunk {chunk.id}")
            await enqueue_realtime_embedding_task(chunk.id)

    # Update batch job as handled
    await update_batch_job(batch_job_id, status='failed_fallback_complete')
```

### Monitoring & Alerting

**Critical Alerts (Immediate):**
- Batch failure rate > 10%
- Circuit breaker opened
- Batch stuck in 'processing' > 48 hours
- API quota exceeded

**Warning Alerts (Daily Summary):**
- Individual request failure rate > 5%
- Average batch completion time > 30 hours
- Real-time fallback rate > 20%

**Metrics to Track:**
```python
# In batch_service.py
metrics = {
    'batch_success_rate': success_count / total_count,
    'avg_retry_count': sum(retry_counts) / batch_count,
    'fallback_rate': realtime_fallback_count / total_requests,
    'ocr_error_rate': ocr_failures / total_ocr_requests,
    'embedding_error_rate': embed_failures / total_embed_requests,
}
```

## Configuration Management

### Environment Variables

```bash
# Gemini Batch API Settings
BATCH_PROCESSING_ENABLED=true
BATCH_MIN_PAGES=20
BATCH_MAX_REQUESTS_PER_JOB=1000
BATCH_POLLING_INTERVAL_MINUTES=60
BATCH_SUBMISSION_INTERVAL_MINUTES=120
GEMINI_BATCH_MODEL=gemini-2.0-flash
BATCH_TIMEOUT_HOURS=48
```

### Runtime Configuration
Use `system_configs` table for dynamic adjustment:
- Allows disabling batch processing without redeployment
- Per-operation thresholds adjustable in production
- Configuration changes take effect on next cron run

## Verification & Testing

### Unit Tests
- `test_batch_client.py`: Mock Gemini API responses, test request/response parsing
- `test_batch_service.py`: Test request collection, batch submission logic
- `test_batch_jobs.py`: Database operations, job state transitions

### Integration Tests
- Submit small batches (5-10 pages) to actual Gemini API
- Verify result mapping and database updates
- Test error scenarios (malformed responses, timeouts)

### End-to-End Testing
1. Upload a test book (20-50 pages) with `processing_mode='batch'`
2. Verify pages marked as `batch_pending`
3. Manually trigger batch submission cron
4. Poll batch status until completion
5. Verify OCR text stored correctly in database
6. Verify embeddings generated and search works
7. Compare results with real-time processing

### Quality Validation
- **OCR Accuracy**: Compare batch OCR vs real-time OCR on same pages
- **Embedding Quality**: Verify search results equivalence
- **Performance**: Measure average completion time (<24 hours)
- **Cost Savings**: Track actual API costs before/after

### Load Testing
- Submit batches of varying sizes (100, 500, 1000 requests)
- Verify no degradation in quality or success rate
- Measure actual cost per batch

## Monitoring & Observability

### Key Metrics
- **Batch submission rate**: Jobs submitted per day
- **Completion time**: Average time from submission to completion
- **Success rate**: Percentage of successful batches
- **Cost savings**: Estimated monthly savings
- **Queue depth**: Pending batches awaiting submission
- **Error rate**: Failed requests per batch

### Alerting
- Batch stuck in 'processing' for >48 hours
- Batch failure rate >10%
- Circuit breaker opened for batch API
- Queue depth exceeding threshold

### Admin Dashboard
- List of active batch jobs with status
- Recent completions and failures
- Cost savings dashboard
- Manual retry/cancel controls

## Migration & Rollout Strategy

### Gradual Rollout Plan

```
Week 1-2: Infrastructure setup (no production impact)
Week 3:   Enable for NEW books only, pages >= 50
Week 4:   Lower threshold to pages >= 30
Week 5:   Enable embeddings batch processing
Week 6:   Lower threshold to pages >= 20
Week 7:   Enable for ALL new books by default (batch_processing_enabled=true)
Week 8:   Backfill historical books (optional, opt-in)
```

### Monitoring During Migration
- Track batch success rate (target: >95%)
- Monitor average completion time (target: <24 hours)
- Compare quality metrics
- Watch for increased error rates

### Rollback Triggers
- Batch failure rate >10%
- Average completion time >48 hours
- Quality degradation detected (OCR accuracy drops)
- **Action**: Disable `batch_processing_enabled`, resume real-time processing

## Deployment Considerations

### Kubernetes Deployment
Following the project's Kubernetes deployment pattern:

1. **Backend changes**: Run `./rebuild-and-restart.sh backend` after code changes
2. **Worker changes**: Run `./rebuild-and-restart.sh worker` after cron job changes
3. **Database migration**: Run `alembic upgrade head` before deploying
4. **Configuration**: Update ConfigMap or environment variables
5. **Pod restart**: Delete pods to force new image pull (`:local` tag)

### Database Migration
```bash
# Generate migration
alembic revision --autogenerate -m "Add batch processing tables"

# Review generated migration
# Edit if needed

# Apply migration
alembic upgrade head
```

### Feature Flag
Use `batch_processing_enabled` config to control rollout:
- Start with `false` (disabled)
- Enable for specific books manually
- Gradually increase to default `true`

## Operational Procedures

### Daily Operations
1. Check batch job dashboard for stuck jobs
2. Review error logs for patterns
3. Monitor cost savings metrics

### Weekly Operations
1. Analyze batch completion times
2. Optimize batch sizes based on data
3. Review and adjust configuration

### Incident Response

**Scenario: Batches stuck >36 hours**
1. Check Gemini API status page
2. Manually poll batch via API
3. If completed, trigger result retrieval
4. If failed, mark failed and re-queue for real-time

**Scenario: High failure rate**
1. Disable batch processing immediately (`batch_processing_enabled=false`)
2. Investigate error patterns in logs
3. Fallback pending books to real-time
4. Fix root cause before re-enabling

## Expected Outcomes

### Benefits
- **50% cost reduction** for OCR and embeddings
- No disruption to existing workflows
- Gradual, safe rollout with rollback capability
- Full monitoring and observability
- Scalable to high-volume processing

### Trade-offs
- **24-hour latency** for batch-processed pages (acceptable for bulk library processing)
- **Incremental book completion** - pages from same book may finish in different batches
- **Increased complexity** with dual processing modes
- **Operational overhead** for monitoring batch jobs

### Success Criteria
- ✅ Batch success rate >95%
- ✅ Average completion time <24 hours
- ✅ OCR quality equivalent to real-time
- ✅ Cost savings 50% confirmed
- ✅ Zero downtime during migration
- ✅ Easy rollback if issues arise

## References

### Research Sources
- [Batch API | Gemini API | Google AI for Developers](https://ai.google.dev/gemini-api/docs/batch-api)
- [Batch Mode in Gemini API: Process more for less](https://developers.googleblog.com/en/scale-your-ai-workloads-batch-mode-gemini-api/)
- [Google Gemini API Batch Mode is 50% Cheaper](https://apidog.com/blog/gemini-api-batch-mode/)
- [Gemini Batch API Colab Notebook](https://colab.research.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Batch_mode.ipynb)
- [LangChain Google GenAI Integration](https://python.langchain.com/api_reference/google_genai/)

### Key Learnings
- ✅ **LangChain does NOT support Gemini Batch API natively** - Must use `google-genai` SDK directly
- ✅ **Batch API supports embeddings and text generation** - Both OCR and embeddings can be optimized
- ✅ **50% cost savings confirmed** - Official pricing from Google
- ✅ **24-hour SLA** - Acceptable for non-real-time workloads
- ✅ **Two-phase batching required** - OCR batches pages → creates chunks → Embedding batches chunks
- ✅ **Request-level batching is sufficient** - No need for book-level batching; collecting requests across multiple books is more efficient
- ✅ **Current implementation combines chunking+embedding** - Must split for batch mode
- ✅ **Chunks table supports NULL embeddings** - Can track pending embeddings via `embedding IS NULL`

## Implementation Review Summary

### Compatibility with Current System

**Good News:**
1. ✅ Existing schema is compatible - Chunks support NULL embeddings
2. ✅ Page statuses work for batch mode - 'pending' → 'ocr_done' → 'indexed'
3. ✅ ChunkingService exists and ready to use
4. ✅ ARQ worker infrastructure ready for new cron jobs
5. ✅ No breaking changes required to existing code

**Adaptations Needed:**
1. 🔧 Split chunking from embedding in `pdf_service.py`
2. 🔧 Add `processing_mode` field to route batch vs realtime
3. 🔧 Collect chunks WHERE `embedding IS NULL` for batch embedding
4. 🔧 Update page status after chunks embedded (not during creation)

### Migration Path

**Phase 1-2: OCR Batching**
- Build on existing page statuses
- Minimal changes to current flow
- Real-time mode unchanged

**Phase 3: Embedding Batching**
- Leverage existing NULL embedding support
- Query chunks by `embedding IS NULL`
- Update chunks table with vectors

**Phase 4: Rollout**
- Start with `processing_mode='realtime'` as default
- Test batch mode on select books
- Gradually switch default to 'batch'

### Risk Assessment

**Low Risk:**
- All batch infrastructure is additive (new tables, new services)
- Existing real-time flow remains unchanged
- Can rollback by setting `batch_processing_enabled=false`

**Medium Risk:**
- Splitting chunking from embedding requires careful testing
- Need to verify search quality matches real-time mode
- Batch failure handling needs robust fallback

**Mitigation:**
- Comprehensive testing before rollout
- Gradual migration (high-page books first)
- Monitor batch success rate (target >95%)
- Keep real-time mode as fallback

### Success Metrics

After implementation, verify:
- ✅ Batch OCR accuracy matches real-time mode
- ✅ Embedding search quality equivalent
- ✅ Cost savings 50% confirmed
- ✅ Average batch completion <24 hours
- ✅ Batch success rate >95%
- ✅ Zero production incidents during rollout

## Unified Architecture Benefits

### Why Split Chunking/Embedding for Both Modes?

**Decision:** Refactor real-time mode FIRST (Phase 0) before adding batch mode.

**Rationale:**

1. **Single Code Path = Less Bugs**
   ```python
   # ONE chunking function used by both modes
   chunks = chunking_service.split_text(text)

   # ONE embedding function used by both modes
   vectors = await embedder.aembed_documents(chunks)
   ```

2. **Same Database State**
   - Chunks always created with `embedding=NULL` first
   - Embedding happens separately (immediately or batched)
   - No special cases or mode-specific states

3. **Easier Testing**
   - Test chunking logic once
   - Test embedding logic once
   - Test mode routing separately
   - Phase 0 validates split approach in production before batch

4. **Better Error Handling**
   ```python
   # If embedding fails, chunks are already saved
   # Can retry embedding without re-chunking
   # Works for both real-time and batch modes
   ```

5. **Future Flexibility**
   - Re-embed books without re-chunking: `UPDATE chunks SET embedding=NULL`
   - Change embedding model: keep chunks, re-embed all
   - Switch book from batch to real-time: chunks already exist, just embed
   - Selective re-embedding: pick specific chunks to re-process

6. **Gradual, Low-Risk Migration**
   ```
   Week 1: Refactor real-time (Phase 0) → Test in production
   Week 2: Add batch infrastructure (Phase 1) → No user impact
   Week 3: Enable batch OCR (Phase 2) → Uses proven chunking code
   Week 4: Enable batch embedding (Phase 3) → Uses proven embedding code
   ```

### Comparison: Unified vs Separate Flows

| Aspect | Unified (Implemented) | Separate Flows (Rejected) |
|--------|----------------------|---------------------------|
| Chunking code | ✅ 1 function | ❌ 2 functions (sync/batch) |
| Embedding code | ✅ 1 function | ❌ 2 functions (sync/batch) |
| Database states | ✅ Consistent | ❌ Different per mode |
| Testing surface | ✅ Small | ❌ Large (2x paths) |
| Bug risk | ✅ Low | ❌ High (code duplication) |
| Re-indexing | ✅ Simple (clear embeddings) | ❌ Complex (mode-specific) |
| Migration risk | ✅ Low (gradual) | ❌ High (big-bang) |
| Maintenance | ✅ Easy (1 place to change) | ❌ Hard (keep 2 paths in sync) |

### Implementation Timeline

```
Phase 0 (Week 1): Unified Architecture Refactoring
├─> Refactor real-time mode to split chunking/embedding
├─> Test in production with existing books
└─> ✅ Unified code path proven and stable

Phase 1 (Week 2): Batch Infrastructure
├─> Add batch tables, client, services
├─> No changes to book processing yet
└─> ✅ Infrastructure ready

Phase 2 (Week 3): OCR Batch Processing
├─> Reuse chunking code from Phase 0
├─> Add batch-specific routing
└─> ✅ Batch OCR working

Phase 3 (Week 4): Embeddings Batch Processing
├─> Reuse embedding code from Phase 0
├─> Add batch cron for embeddings
└─> ✅ End-to-end batch processing

Phase 4 (Week 5-6): Monitoring & Rollout
├─> Add metrics and alerts
├─> Gradual rollout to production
└─> ✅ 50% cost savings achieved
```

**Total Timeline:** 6 weeks (vs 7-8 weeks with separate flows)
**Risk Profile:** Lower (proven at each phase)
**Code Quality:** Higher (unified, maintainable)
