-- Migration 074: Full-text search column for hybrid (keyword + vector) retrieval
--
-- Uses 'simple' text search config deliberately, not 'english' — book content
-- is substantially Uyghur-language, and 'english' applies English-specific
-- stemming rules that don't meaningfully apply here. 'simple' just
-- tokenizes/lowercases, which is the correct choice for mixed-language content.
--
-- CREATE INDEX CONCURRENTLY runs outside a transaction block by design (no
-- BEGIN/COMMIT wrapper) so it doesn't hold a long lock on a potentially large
-- table. The ADD COLUMN itself still requires a one-time table rewrite to
-- backfill the generated column for existing rows.

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_search tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chunks_text_search ON chunks USING GIN (text_search);
