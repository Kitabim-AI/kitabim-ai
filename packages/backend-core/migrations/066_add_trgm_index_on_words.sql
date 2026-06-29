-- Migration: 066_add_trgm_index_on_words.sql
-- Description: Add trigram GIN index on words.word for OCR spell-check fuzzy matching

BEGIN;

CREATE INDEX IF NOT EXISTS idx_words_word_trgm ON public.words USING gin (word public.gin_trgm_ops);

COMMIT;
