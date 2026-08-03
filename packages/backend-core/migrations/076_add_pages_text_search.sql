-- Migration 076: Full-text search column for page-level content search
--
-- Adds a page-level tsvector + GIN index mirroring migration 074
-- (chunks.text_search), so the home "Content" search tab can query `pages`
-- directly instead of `chunks` -- one row per page means no dedup step is
-- needed for phrases that match multiple chunks on the same page, and
-- avoids the ranking dilution/window-function overhead a chunk-side dedupe
-- would add. Uses 'simple' text search config for the same reason as 074:
-- book content is substantially Uyghur-language, and 'simple' just
-- tokenizes/lowercases rather than applying English-specific stemming.
--
-- CREATE INDEX CONCURRENTLY runs outside a transaction block by design (no
-- BEGIN/COMMIT wrapper) so it doesn't hold a long lock on a potentially
-- large table. The ADD COLUMN itself still requires a one-time table
-- rewrite to backfill the generated column for all existing rows -- on a
-- large `pages` table this holds an ACCESS EXCLUSIVE lock on `pages` for
-- the full duration of the backfill (can take hours). Run via
-- scripts/run_pages_text_search_migration.sh, in the background.

ALTER TABLE pages ADD COLUMN IF NOT EXISTS text_search tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pages_text_search ON pages USING GIN (text_search);
