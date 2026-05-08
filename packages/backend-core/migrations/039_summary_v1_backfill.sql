-- Migration: 039_summary_v1_backfill.sql
-- Description: Preserve existing summaries + embeddings while all books are
--              re-summarised using full content (replacing the old 15K-char sample).
--
--              summary_v1    — preserves old summary text for reference / rollback
--              embedding_draft — receives new embeddings; active 'embedding' column
--                               is untouched until cutover migration 040 swaps them.
--
--              summary is set NULL so summary_scanner picks up every book for
--              regeneration. Drop summary_v1 and embedding_draft in migration 040
--              once satisfied with new summaries.
-- Author: Omarjan
-- Date: 2026-05-07

BEGIN;

ALTER TABLE book_summaries ADD COLUMN IF NOT EXISTS summary_v1 TEXT;
ALTER TABLE book_summaries ADD COLUMN IF NOT EXISTS embedding_draft vector(3072);

UPDATE book_summaries SET summary_v1 = summary;

ALTER TABLE book_summaries ALTER COLUMN summary DROP NOT NULL;

UPDATE book_summaries SET summary = NULL;

COMMIT;
