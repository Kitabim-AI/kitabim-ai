-- Migration 083: Drop chunks.text_search (superseded by pages.text_search)
--
-- The chat RAG keyword leg (ChunksRepository.keyword_search) now sources
-- exact-phrase search from pages.text_search (migration 076) instead of
-- chunks.text_search (migration 074) — pages give one hit per page instead
-- of one per chunk, matching what the home Content-tab search already
-- switched to. Nothing queries chunks.text_search anymore.
--
-- DROP INDEX CONCURRENTLY runs outside a transaction block by design (no
-- BEGIN/COMMIT wrapper) so it doesn't hold a long lock.

DROP INDEX CONCURRENTLY IF EXISTS idx_chunks_text_search;

ALTER TABLE chunks DROP COLUMN IF EXISTS text_search;
