-- Migration: 038_drop_embedding_v1_columns.sql
-- Description: Cleanup — drop the 768-dim embedding_v1 columns and their indexes
--              after validating the v2 cutover is stable (~1 week post-cutover).
--              PostgreSQL automatically drops indexes on a dropped column, so
--              idx_chunks_embedding_v1 and idx_book_summaries_embedding_v1 are
--              removed implicitly.
--
--              Do NOT apply until RAG search quality has been verified post-cutover.
-- Author: Omarjan
-- Date: 2026-05-03

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chunks' AND column_name = 'embedding_v1'
    ) THEN
        ALTER TABLE chunks DROP COLUMN embedding_v1;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'book_summaries' AND column_name = 'embedding_v1'
    ) THEN
        ALTER TABLE book_summaries DROP COLUMN embedding_v1;
    END IF;
END $$;

COMMIT;
