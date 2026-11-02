# RAG Handlers (`app/services/rag/handlers`)

## Overview
Houses specialized query domain handlers for RAG execution, formatting targeted context for library catalog queries, author bibliographies, and book availability.

## Interface
- `[catalog.py:CatalogHandler]` — Specialized query handler providing deterministic book and author catalog metadata retrieval.
- `[catalog.py:CatalogHandler._build_catalog_context]` — `_build_catalog_context(question: str, session: AsyncSession, categories: Optional[List[str]] = None) -> Tuple[str, int]`: Matches query against book titles and authors or returns catalog overview.
- `[catalog.py:CatalogHandler._prepend_current_book]` — Enriches catalog context with details of the active book in single-book reading mode.

## Invariants
- `[catalog.py:CatalogHandler]` — Follows strict matching hierarchy: specific book title match -> author match -> full library catalog fallback.
- `[catalog.py:CatalogHandler]` — Strictly excludes books in `status == 'error'` from catalog responses.

## Side Effects
- Reads book titles, authors, volumes, and page counts from PostgreSQL `books` table.

## Verification
- Run: `pytest packages/backend-core/tests`
