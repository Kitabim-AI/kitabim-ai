-- Migration: 035_add_embedding_v2_columns.sql
-- Description: Add embedding_v2 (vector 3072) columns to chunks and book_summaries
--              for the Gemini Embedding 2 upgrade. No indexes yet — added in 036
--              after re-embedding is complete.
-- Author: Omarjan
-- Date: 2026-05-03

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chunks' AND column_name = 'embedding_v2'
    ) THEN
        ALTER TABLE chunks ADD COLUMN embedding_v2 vector(3072);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'book_summaries' AND column_name = 'embedding_v2'
    ) THEN
        ALTER TABLE book_summaries ADD COLUMN embedding_v2 vector(3072);
    END IF;
END $$;

-- Seed the v2 model config key so the reembedding job can read it.
-- IMPORTANT (Phase 0): verify this model ID against Google's API before running
-- the reembedding scanner. Update the value in system_configs if it differs.
INSERT INTO system_configs (key, value, description)
VALUES (
    'gemini_embedding_model_v2',
    'models/gemini-embedding-2',
    'Gemini Embedding v2 model used during migration to 3072-dim embeddings. Verify model ID before enabling reembedding_scanner.'
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
