# Work Protection, Anti-Scraping & Provenance Tracking (TODOs)

**Branch:** `feature/surya-ocr-client`  
**Date:** 2026-08-30  
**Status:** Backlog / Planned Implementation

---

## 1. Background & Objective
Kitabim.AI digitizes, OCRs, proofreads, chunks, embeds, and knowledge-graphs Uyghur print books. While copyright over the underlying historical or community source texts may not reside exclusively with Kitabim, **the digitized corpus, OCR transcripts, human editorial corrections, dictionary additions, and vector/graph embeddings represent substantial compute, time, and intellectual labor**.

This document details the planned technical safeguards to:
1. Prevent bulk scraping of curated full-text data and OCR transcripts.
2. Track provenance, authorship, and editorial revision history for proofread pages.
3. Enforce granular rate limits and access controls across retrieval endpoints.

---

## 2. Inventory of TODO Items

### TODO 1: Anti-Scraping Rate Limiting on Content Endpoints
- **Target Files**:
  - [`services/backend/api/endpoints/books_router.py`](file:///Users/Omarjan/Projects/kitabim-ai/services/backend/api/endpoints/books_router.py)
  - [`services/backend/api/endpoints/chat_router.py`](file:///Users/Omarjan/Projects/kitabim-ai/services/backend/api/endpoints/chat_router.py)
- **Problem**:
  Currently, only `auth_router.py` has `@limiter.limit(...)` decorators. Endpoints that dump page text (`/books/{id}/pages`, `/books/{id}/content`, `/books/content-search`) can be crawled in bulk by automated bots without rate limits.
- **Proposed Solution**:
  Apply `slowapi` rate limits based on client IP / user token:
  - `GET /books/{book_id}/content`: `@limiter.limit("20/minute")`
  - `GET /books/{book_id}/pages`: `@limiter.limit("60/minute")`
  - `GET /books/{book_id}/pages/{page_num}`: `@limiter.limit("120/minute")`
  - `GET /books/content-search`: `@limiter.limit("30/minute")`
  - `POST /chat`: `@limiter.limit("30/minute")`

---

### TODO 2: Editorial Provenance & Metadata Columns
- **Target Files**:
  - [`packages/backend-core/app/models/schemas.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/models/schemas.py)
  - `packages/backend-core/app/models/` (SQLAlchemy DB models)
  - Alembic migrations in `services/backend/`
- **Problem**:
  The database does not record *who* proofread a page or *which* OCR engine/model version generated the transcript.
- **Proposed Solution**:
  Add provenance columns to `Page` and `Book` models:
  - `Page.last_edited_by_user_id`: UUID of the editor/curator who modified the text.
  - `Page.ocr_engine`: Name of the OCR engine used (e.g., `"surya"`, `"easyocr"`, `"gemini"`).
  - `Page.ocr_engine_version`: Version string of the model or client.
  - `Page.is_human_verified`: Boolean flag indicating manual human review.

---

### TODO 3: Page Correction Audit Log & Revision History
- **Target Files**:
  - `packages/backend-core/app/models/page_revision.py` (New Model)
  - `packages/backend-core/app/repositories/page_revisions_repo.py` (New Repository)
  - [`services/backend/api/endpoints/books_router.py`](file:///Users/Omarjan/Projects/kitabim-ai/services/backend/api/endpoints/books_router.py) (Update `update_page_text` handler)
- **Problem**:
  When an editor edits page text (`POST /books/{id}/pages/{n}/update`), the existing text is overwritten directly in PostgreSQL without retaining history.
- **Proposed Solution**:
  Create a `page_revisions` table:
  ```sql
  CREATE TABLE page_revisions (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
      page_number INTEGER NOT NULL,
      user_id UUID REFERENCES users(id),
      previous_text TEXT NOT NULL,
      updated_text TEXT NOT NULL,
      char_diff INTEGER,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
  );
  ```
  Every update writes an immutable revision entry, establishing a clear proof of editorial labor and audit trail.

---

### TODO 4: Corpus Export Control & Watermark Signature
- **Target Files**:
  - [`services/backend/api/endpoints/books_router.py`](file:///Users/Omarjan/Projects/kitabim-ai/services/backend/api/endpoints/books_router.py)
- **Problem**:
  Public books permit full text scraping without attribution or signatures.
- **Proposed Solution**:
  - Restrict bulk-dump endpoints to authenticated `reader` or `editor` accounts.
  - Include cryptographic signature / provenance headers on API content delivery (e.g. `X-Kitabim-Provenance: Kitabim-AI-Digitized`).

---

## 3. Implementation Priority Matrix

| Priority | Item | Impact | Complexity |
| :---: | :--- | :--- | :---: |
| **P1** | Add rate limits on retrieval endpoints (`TODO 1`) | Prevents automated bulk scraping | Low |
| **P1** | Add editor ID & OCR engine metadata to Page (`TODO 2`) | Captures provenance at creation time | Low |
| **P2** | Add `page_revisions` audit history table (`TODO 3`) | Full proof of human review & versioning | Medium |
| **P3** | Watermark & export permission rules (`TODO 4`) | Brand protection & licensed distribution | Low |
