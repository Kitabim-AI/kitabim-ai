-- Rollback 083: Restore chunks.text_search (mirrors migration 074 forward)
--
-- CREATE INDEX CONCURRENTLY runs outside a transaction block by design (no
-- BEGIN/COMMIT wrapper) so it doesn't hold a long lock on a potentially large
-- table. The ADD COLUMN itself still requires a one-time table rewrite to
-- backfill the generated column for existing rows.

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_search tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_text_search ON chunks USING GIN (text_search);
