-- Migration: 064_create_english_uyghur_dictionary.sql
-- Description: Create english_uyghur_dictionary table
-- Author: Omarjan
-- Date: 2026-06-26

BEGIN;

CREATE TABLE IF NOT EXISTS public.english_uyghur_dictionary (
    id           SERIAL PRIMARY KEY,
    english      character varying(500) NOT NULL,
    uyghur       TEXT NOT NULL,
    letter_group character varying(5) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_english_uyghur_dictionary_english
    ON public.english_uyghur_dictionary (english);

CREATE INDEX IF NOT EXISTS idx_english_uyghur_dictionary_letter_group
    ON public.english_uyghur_dictionary (letter_group);

CREATE INDEX IF NOT EXISTS idx_english_uyghur_dictionary_english_trgm
    ON public.english_uyghur_dictionary USING gin (english public.gin_trgm_ops);

COMMIT;
