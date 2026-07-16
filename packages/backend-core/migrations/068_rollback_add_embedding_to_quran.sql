-- Migration: 068_rollback_add_embedding_to_quran.sql
-- Description: Rollback adding embedding column and index to the quran table
-- Author: Antigravity
-- Date: 2026-07-11

BEGIN;

DROP INDEX IF EXISTS idx_quran_embedding;
ALTER TABLE public.quran DROP COLUMN IF EXISTS embedding;

COMMIT;
