-- Rollback Migration: 106_rollback_add_normalized_trgm_index_on_words.sql
-- Description: Drop normalized GIN trigram expression index on words.word
-- Author: Antigravity
-- Date: 2026-11-26

BEGIN;

DROP INDEX IF EXISTS public.idx_words_norm_trgm;

COMMIT;
