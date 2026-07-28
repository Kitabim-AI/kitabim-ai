-- Rollback 074: Remove full-text search column for hybrid retrieval
DROP INDEX CONCURRENTLY IF EXISTS idx_chunks_text_search;

ALTER TABLE chunks DROP COLUMN IF EXISTS text_search;
