-- Migration: 068_add_embedding_to_quran.sql
-- Description: Add embedding column and index to the quran table for semantic search support
-- Author: Antigravity
-- Date: 2026-07-11

BEGIN;

ALTER TABLE public.quran ADD COLUMN IF NOT EXISTS embedding vector(3072);

-- Create HNSW index using halfvec for space efficiency and fast retrieval
CREATE INDEX IF NOT EXISTS idx_quran_embedding
  ON public.quran USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);

COMMIT;
