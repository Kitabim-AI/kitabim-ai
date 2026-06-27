-- Migration: 059_create_synonyms_table.sql
-- Description: Create synonyms table for Uyghur synonym dictionary
-- Author: Omarjan
-- Date: 2026-06-26

BEGIN;

CREATE TABLE IF NOT EXISTS public.synonyms (
    id SERIAL PRIMARY KEY,
    word VARCHAR(255) NOT NULL UNIQUE,
    letter_group VARCHAR(50) NOT NULL,
    synonyms TEXT[] NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_synonyms_letter_group ON public.synonyms (letter_group);
CREATE INDEX IF NOT EXISTS idx_synonyms_word_trgm ON public.synonyms USING gin (word public.gin_trgm_ops);

COMMIT;
