-- Migration: 060_create_history_dictionary.sql
-- Description: Create history_dictionary table for Uyghur historical vocabulary
-- Author: Omarjan
-- Date: 2026-06-26

BEGIN;

CREATE TABLE IF NOT EXISTS public.history_dictionary (
    id          SERIAL PRIMARY KEY,
    term        character varying(500) NOT NULL,
    transliteration TEXT,
    definition  TEXT,
    letter_group character varying(10) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_history_dictionary_term
    ON public.history_dictionary (term);

CREATE INDEX IF NOT EXISTS idx_history_dictionary_letter_group
    ON public.history_dictionary (letter_group);

CREATE INDEX IF NOT EXISTS idx_history_dictionary_term_trgm
    ON public.history_dictionary USING gin (term public.gin_trgm_ops);

COMMIT;
