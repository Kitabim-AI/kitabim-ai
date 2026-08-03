-- Rollback 076: Remove page-level full-text search column
DROP INDEX CONCURRENTLY IF EXISTS idx_pages_text_search;

ALTER TABLE pages DROP COLUMN IF EXISTS text_search;
