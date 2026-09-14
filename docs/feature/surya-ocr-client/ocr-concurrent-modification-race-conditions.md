# OCR & Concurrent Book Modification Race Conditions Analysis

**Branch:** `feature/surya-ocr-client`  
**Date:** September 5, 2026  
**Scope:** Investigating race conditions between active OCR pipelines (worker OCR jobs, batch OCR pollers, desktop Surya OCR client pushes) and concurrent content modifications (web reader edits, spell-check auto-corrections, TOC edits) on the same book.

---

## Executive Summary

There are **multiple critical race conditions** in Kitabim AI when OCR is being performed or re-run on a book while its pages or metadata are being modified concurrently. 

The most severe finding is **silent data loss**: when an OCR job or batch OCR poller completes, it performs an unconditional `UPDATE pages SET text = :ocr_text ...`, completely overwriting any human edits, desktop client pushes, or spell-check auto-corrections applied while the OCR was in flight. Furthermore, distributed locks (`MultiPageLock`) are only acquired by workers and are completely bypassed by all REST API endpoints.

---

## Architecture & Concurrency Context

In Kitabim AI, content modifications and OCR operations occur across three distinct execution environments:

1. **Background Workers (ARQ / Redis)**:
   - `ocr_scanner.py` claims idle pages and dispatches `ocr_job.py`.
   - `batch_ocr_poller_scanner.py` periodically polls Gemini Batch API and ingests completed OCR results via `batch_ocr_service.py`.
   - `chunking_scanner.py` / `embedding_scanner.py` / `spell_check_scanner.py` drive downstream stages.
   - `auto_correct_job.py` batch-rewrites page text based on active spell-check rules.
2. **Backend API (`services/backend`)**:
   - `POST /api/books/{book_id}/pages/{page_num}/update`: Synchronously updates page text, re-chunks, and re-embeds.
   - `POST /api/books/{book_id}/pages/{page_num}/toc`: Modifies TOC flags and recalculates `content_page_offset`.
   - `POST /api/books/{book_id}/pages/{page_num}/spell-check/apply`: Applies word corrections by character offset.
   - `POST /api/books/{book_id}/reprocess/ocr` & `POST /api/books/{book_id}/pages/{page_num}/reset`: Re-triggers OCR.
3. **Standalone Desktop Client (`clients/kitabim-ocr`)**:
   - Runs local Surya OCR and pushes updates via rapid sequential calls to `/update` and `/toc`.

---

## Detailed Findings

### 1. The "Lost Update" on Page Text (Critical Data Loss)
* **Affected Code**:
  * `services/worker/jobs/ocr_job.py:254-275`
  * `packages/backend-core/app/services/batch_ocr_service.py:619-638`
  * `services/backend/api/endpoints/books_router.py:2374-2420`
* **Mechanism**:
  1. An OCR worker or Gemini Batch OCR job begins processing Page $X$. Calling the Gemini Vision API takes 2–15 seconds per page (or hours for Batch API).
  2. While OCR is in flight, an editor opens Page $X$ in the web reader or sends an update via `POST /pages/{page_num}/update`.
  3. The editor's transaction writes `Page.text = new_text`, deletes old chunks, inserts new chunks, embeds them, and commits.
  4. The OCR job finishes and executes:
     ```python
     await session.execute(
         update(Page)
         .where(Page.id == page.id)
         .values(
             text=text,
             is_toc=is_toc,
             ocr_milestone="succeeded",
             last_updated=func.now(),
         )
     )
     ```
* **Impact**:
  * There is **no optimistic concurrency control (OCC)** (no `version` check and no `WHERE last_updated = :claimed_at`).
  * The human editor's manual edits are **silently wiped out and replaced with raw OCR text**.
  * The worker emits an `ocr_succeeded` pipeline event, which triggers downstream chunking and re-embedding of the raw OCR text, overwriting the editor's manual embeddings.

---

### 2. Distributed Locking Scope Mismatch (False Sense of Security)
* **Affected Code**:
  * `services/worker/jobs/ocr_job.py:42-48`
  * `services/backend/api/endpoints/books_router.py:2375-2420`
  * `services/backend/api/endpoints/spell_check_router.py:312-450`
* **Mechanism**:
  * `ocr_job.py` acquires a Redis lock via `MultiPageLock(redis_client, page_ids, prefix="ocr")`.
  * However, neither `update_page_text`, `set_page_toc`, nor `apply_spell_corrections` checks or acquires this Redis lock.
  * None of the API endpoints acquire database row locks (`SELECT ... FOR UPDATE`) against the `pages` table.
* **Impact**:
  * The lock only prevents two worker processes from claiming the same page. It provides **zero isolation** against concurrent human edits, automated spell corrections, or desktop client pushes.

---

### 3. Mid-Flight State Gap & Double-Embedding Race
* **Affected Code**:
  * `services/backend/api/endpoints/books_router.py:2452-2480`
  * `services/worker/scanners/embedding_scanner.py:40-62`
* **Mechanism**:
  * In `update_page_text`, the operation splits into two transactions to avoid holding an open database transaction during a slow AI embedding call:
    ```python
    page.status = "chunked"
    page.chunking_milestone = PAGE_MILESTONE_SUCCEEDED
    page.embedding_milestone = PAGE_MILESTONE_IDLE
    await session.commit()  # <-- Transaction 1 committed

    # Network I/O: Async call to Gemini Embeddings (1-5s)
    embedder = GeminiEmbeddings(...)
    vectors = await embedder.aembed_documents(...)

    # Transaction 2: Update chunks and page milestone
    ...
    page.embedding_milestone = PAGE_MILESTONE_SUCCEEDED
    await session.commit()
    ```
  * During the 1–5 second window while awaiting Gemini:
    * The database row has `chunking_milestone = 'succeeded'` and `embedding_milestone = 'idle'`.
    * `EmbeddingScanner` (which runs every 60 seconds) queries:
      ```python
      where(Page.chunking_milestone == "succeeded", Page.embedding_milestone == "idle")
      ```
    * If `EmbeddingScanner` ticks during this window, it claims the page, marks `embedding_milestone = 'in_progress'`, and enqueues an `embedding_job`.
* **Impact**:
  * Both the HTTP request and the worker process invoke Gemini embeddings for the same chunks.
  * Both attempt to update vector embeddings in the `chunks` table concurrently, wasting Gemini API quota and causing write contention.

---

### 4. Table of Contents (TOC) & Offset Clobbering
* **Affected Code**:
  * `services/worker/jobs/ocr_job.py:251, 365-367`
  * `services/backend/api/endpoints/books_router.py:2538-2560`
  * `packages/backend-core/app/db/repositories/pages_repository.py:267-285`
* **Mechanism**:
  * `ocr_job.py` automatically checks `is_toc = is_toc_page(text)` and writes `is_toc=is_toc` to the database.
  * At the end of the batch, `ocr_job` calls `sync_content_page_offset(book_id)`, which executes:
    ```sql
    SELECT COALESCE(MAX(page_number), 0) FROM pages WHERE book_id = :book_id AND is_toc IS TRUE
    ```
  * If an editor manually toggles a page's TOC flag (`POST /pages/{page_num}/toc`):
    1. If the editor marked Page $Y$ as TOC, but `ocr_job` subsequently processes Page $Y$, the heuristic overwrites `is_toc` back to `False`.
    2. If a later page contains false-positive chapter listings, `ocr_job` marks it `is_toc = True` and inflates `book.content_page_offset`, corrupting page number mapping throughout the reader.

---

### 5. Spell-Check Character Offset Invalidation & Text Corruption
* **Affected Code**:
  * `services/backend/api/endpoints/books_router.py:2412-2419`
  * `services/worker/jobs/spell_check_job.py:76-99`
  * `services/backend/api/endpoints/spell_check_router.py:420-431`
* **Mechanism**:
  * When page text is updated, `update_page_text` clears `page_spell_issues` rows because character offsets are no longer valid.
  * However, if `SpellCheckJob` was already running on that page:
    1. `SpellCheckJob` tokenizes the old text and calculates `char_offset` and `char_end`.
    2. If `SpellCheckJob` commits *after* `update_page_text` deleted the old issues, it inserts `page_spell_issues` rows that point to positions in the *previous* text.
* **Impact**:
  * When a user opens the Spell Check modal and clicks "Apply", the backend splices replacement words into the wrong character offsets:
    ```python
    page_text = page_text[:start] + corrected + page_text[end:]
    ```
  * This results in **severe character corruption and scrambled text**.

---

### 6. Book State Flapping & Premature Summary Generation
* **Affected Code**:
  * `services/worker/scanners/pipeline_driver.py:200-260`
  * `services/backend/api/endpoints/books_router.py:2363-2370`
* **Mechanism**:
  * When an admin resets a single page (`POST /pages/{page_num}/reset`) or triggers OCR re-processing on a completed book:
    * `book.status` is set to `'pending'`.
    * `book.ocr_milestone` is set to `'in_progress'`.
  * If another user edits an already-completed page via `update_page_text`, it calls `BookMilestoneService.update_book_milestones(session, book_id)`.
  * Meanwhile, `pipeline_driver.py` periodically scans for books where all pages have reached terminal status:
    ```python
    func.count(Page.id) == func.count(terminal_case)
    ```
* **Impact**:
  * As pages finish asynchronously, intermediate milestone calculations can cause `pipeline_driver.py` to observe intermittent completion states.
  * In particular, the condition for enqueueing `summary_job` (`BookSummary.book_id.is_(None)`) can fire prematurely or fail to re-fire after major text changes.

---

### 7. Desktop Client (`kitabim-ocr`) Push Storm Contention
* **Affected Code**:
  * `clients/kitabim-ocr/kitabim_client/api.py:87-102`
  * `clients/kitabim-ocr/preview/server.py:806-823`
* **Mechanism**:
  * The local Surya OCR desktop client pushes corrections by issuing two HTTP calls per page in rapid succession (`/update` and `/toc`).
  * For a 400-page book, this creates 800 rapid API calls.
  * Each `/update` request:
    1. Synchronously calls Gemini embeddings (`aembed_documents`).
    2. Runs `BookMilestoneService.update_book_milestones`, executing an aggregation query over all pages.
    3. Flushes Redis caches:
       ```python
       await cache_service.delete(f"book:{book_id}")
       await cache_service.delete_pattern(f"rag:search:{book_id}:*")
       ```
* **Impact**:
  * If a push occurs while server-side OCR or auto-correct jobs are executing, database lock timeouts and transaction rollbacks occur.
  * Server-side OCR finishing after a desktop push will overwrite the pushed Surya OCR text.

---

## Summary Matrix

| Issue | Severity | Components Involved | Consequence |
|---|---|---|---|
| **Lost Updates / Clobbering** | **CRITICAL** | `ocr_job.py`, `batch_ocr_service.py`, `books_router.py` | Manual edits or client pushes silently overwritten by OCR output. |
| **Lock Scope Mismatch** | **HIGH** | `ocr_job.py`, `MultiPageLock`, `books_router.py` | Redis locks protect worker vs worker, but ignore API calls. |
| **Double-Embedding Gap** | **MEDIUM** | `books_router.py`, `embedding_scanner.py` | Mid-flight `idle` state triggers duplicate background embedding jobs. |
| **TOC & Offset Clobbering** | **MEDIUM** | `ocr_job.py`, `pages_repository.py`, `books_router.py` | Heuristics overwrite manual TOC designations and shift page offset. |
| **Spell-Check Offset Skew** | **HIGH** | `spell_check_job.py`, `spell_check_router.py` | Stale offsets splice text into wrong positions, garbling content. |
| **Desktop Push Contention** | **HIGH** | `kitabim-ocr`, `update_page_text`, `cache_service` | Cache thrashing, DB lock contention, and overwrite of pushed text. |

---

## Actionable Remediation Plan

1. **Optimistic Concurrency Control (OCC)**:
   * Add a `version: int` column to `Page` (or compare `Page.last_updated == claimed_at`).
   * In `ocr_job.py` and `batch_ocr_service.py`, execute updates conditionally:
     ```python
     stmt = (
         update(Page)
         .where(Page.id == page.id, Page.last_updated == claimed_last_updated)
         .values(...)
     )
     ```
   * If `rowcount == 0`, log that the page was modified by a user, and **abort overwriting the page text**.

2. **Unify Concurrency Guarding in API Routes**:
   * In `update_page_text` and `apply_spell_corrections`, check whether `page.ocr_milestone == 'in_progress'`.
   * Either acquire the Redis lock (`MultiPageLock`) or return `409 Conflict` (`"Page is currently undergoing OCR processing"`).

3. **Eliminate the Mid-Flight Embedding Gap**:
   * In `update_page_text`, set `embedding_milestone = PAGE_MILESTONE_IN_PROGRESS` (instead of `PAGE_MILESTONE_IDLE`) before calling `embedder.aembed_documents`.
   * This prevents `EmbeddingScanner` from claiming the page while the HTTP handler awaits the Gemini API response.

4. **Protect Manual TOC Configurations**:
   * Introduce an `is_toc_manual: bool` column on `Page`.
   * Ensure `ocr_job.py` and `batch_ocr_service.py` only assign `is_toc` if `is_toc_manual` is `False`.
