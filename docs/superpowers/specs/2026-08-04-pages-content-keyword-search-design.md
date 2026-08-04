# Design Document: Pages Content Keyword Search

## Overview
This design details the transition of the home "Content" keyword search tab from searching `chunks` to searching `pages` directly using PostgreSQL full-text search index (`pages.text_search`).

## Problem & Motivation
Previously, content search targeted `chunks.text_search`. Because a single page in a book is divided into multiple text chunks during OCR processing, keyword searches often matched multiple chunks on the exact same page. This resulted in duplicate search hits for the same page, required deduplication window functions or post-processing, and diluted text search ranking scores.

With migration 076 (`076_add_pages_text_search.sql`), a `tsvector` generated column (`text_search`) and a GIN index (`idx_pages_text_search`) were added directly to the `pages` table. Querying `pages` directly yields exactly one hit per matching page with zero duplicate page hits.

## Proposed Changes

### 1. `packages/backend-core/app/db/repositories/pages_repository.py`
Add `search_content_pages` method to `PagesRepository`:
- **Function Signature**:
  ```python
  async def search_content_pages(
      self,
      phrase: str,
      skip: int = 0,
      limit: int = 40,
      restrict_to_public: bool = True,
  ) -> tuple[List[dict], int]:
  ```
- **SQL Execution**:
  - Filter: `p.text_search @@ phraseto_tsquery('simple', :phrase)`
  - Table of Contents Exclusion: `(p.is_toc IS NOT TRUE OR p.id IS NULL)`
  - Book Visibility: Public visitors only see `b.status = 'ready' AND (b.visibility = 'public' OR b.visibility IS NULL)`. Authenticated admin/editor users see `b.status != 'error'`.
  - Single-Token Optimization: `len(phrase.strip().split()) == 1` skips `ts_rank` and orders by `b.title ASC, p.page_number ASC` to enable fast GIN index scans. Multi-token queries order by `rank DESC, b.title ASC, p.page_number ASC`.
  - Session Safety: Executes `SET LOCAL work_mem = '64MB'` and `SET LOCAL statement_timeout = '15000ms'`.
- **Output Dict Fields**: `id` (`{book_id}_{page_number}`), `book_id`, `book_title`, `book_author`, `book_volume`, `book_cover_url`, `page_number`, `page`, `snippet` (full `p.text`), `rank`.

### 2. `services/backend/api/endpoints/books_router.py`
Update `GET /api/v1/books/content-search`:
- Instantiate `PagesRepository(session)`.
- Call `pages_repo.search_content_pages(q, skip=skip, limit=pageSize, restrict_to_public=restrict_to_public)`.
- Return `PaginatedContentHits`.

### 3. Repository & Router Tests
- Update unit tests in `packages/backend-core/tests/app/db/pages_repository_test.py` to cover `search_content_pages()`.
- Update API route unit tests in `services/backend/tests/api/endpoints/books_router_test.py`.

## Verification Plan
1. Run backend unit tests: `pytest packages/backend-core/tests/app/db/pages_repository_test.py` and `pytest services/backend/tests/api/endpoints/books_router_test.py`.
2. Run frontend unit tests: `npm test` inside `apps/frontend/`.
3. Verify local Docker Compose environment endpoint response for `/api/v1/books/content-search?q=...`.
