-- Migration: 040_summary_embedding_cutover.sql
-- Description: Cutover to new full-content summaries and their embeddings.
--              Swaps embedding_draft → embedding, restores NOT NULL on summary,
--              then drops the staging columns added in migration 039.
--              Run only once all books have been regenerated (embedding_draft IS NOT NULL).
-- Author: Omarjan
-- Date: 2026-05-07

BEGIN;

-- Swap new embeddings into the active search column
UPDATE book_summaries
SET embedding = embedding_draft
WHERE embedding_draft IS NOT NULL;

-- Restore NOT NULL constraint now that all summaries are populated
ALTER TABLE book_summaries ALTER COLUMN summary SET NOT NULL;

-- Drop staging columns
ALTER TABLE book_summaries DROP COLUMN IF EXISTS embedding_draft;
ALTER TABLE book_summaries DROP COLUMN IF EXISTS summary_v1;

COMMIT;
