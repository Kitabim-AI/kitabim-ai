-- Migration: 062_create_names_dictionary.sql
-- Description: Create names_dictionary table for Uyghur person names
-- Author: Omarjan
-- Date: 2026-06-26

BEGIN;

CREATE TABLE IF NOT EXISTS public.names_dictionary (
    id          SERIAL PRIMARY KEY,
    name        character varying(500) NOT NULL,
    letter_group character varying(20) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_names_dictionary_name
    ON public.names_dictionary (name);

CREATE INDEX IF NOT EXISTS idx_names_dictionary_letter_group
    ON public.names_dictionary (letter_group);

CREATE INDEX IF NOT EXISTS idx_names_dictionary_name_trgm
    ON public.names_dictionary USING gin (name public.gin_trgm_ops);

COMMIT;
