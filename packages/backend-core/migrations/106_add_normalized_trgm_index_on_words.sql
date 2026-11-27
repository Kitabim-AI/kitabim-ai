-- Migration: 106_add_normalized_trgm_index_on_words.sql
-- Description: Add GIN trigram expression index on normalized words.word for fast spell-check suggestions and drop duplicate idx_words_trgm
-- Author: Antigravity
-- Date: 2026-11-26

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Matches DictionaryRepository._sql_normalize_uyghur(Word.word):
-- ې (U+06D0), ى (U+0649), ي (U+064A) -> ی (U+06CC), collapsing یی -> ی.
CREATE INDEX IF NOT EXISTS idx_words_norm_trgm
    ON public.words USING gin (
        (replace(replace(replace(replace(word, U&'\06d0', U&'\06cc'), U&'\0649', U&'\06cc'), U&'\064a', U&'\06cc'), U&'\06cc\06cc', U&'\06cc'))
        public.gin_trgm_ops
    );

-- Drop duplicate raw-word GIN index from 001_initial_baseline.sql (idx_words_word_trgm from 066 is identical).
DROP INDEX IF EXISTS public.idx_words_trgm;

ANALYZE public.words;

COMMIT;
