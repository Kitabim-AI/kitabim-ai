-- Migration: 058_rename_dictionary_to_words_and_create_new_dictionary.sql
-- Description: Rename existing dictionary table to words, and create a new dictionary table (idempotent)
-- Author: Antigravity
-- Date: 2026-06-27

BEGIN;

-- Rename existing dictionary table to words using idempotent DO block
DO $$
BEGIN
    -- Check if 'dictionary' table exists and does NOT have 'definition' column
    -- (which means it's the old spell check dictionary table that needs to be renamed)
    IF EXISTS (
        SELECT 1 
        FROM pg_tables 
        WHERE schemaname = 'public' 
          AND tablename = 'dictionary'
    ) AND NOT EXISTS (
        SELECT 1 
        FROM pg_attribute 
        WHERE attrelid = 'public.dictionary'::regclass 
          AND attname = 'definition'
    ) THEN
        ALTER TABLE ONLY public.dictionary RENAME TO words;
        ALTER TABLE ONLY public.words RENAME CONSTRAINT dictionary_pkey TO words_pkey;
        ALTER TABLE ONLY public.words RENAME CONSTRAINT dictionary_word_key TO words_word_key;
        ALTER SEQUENCE IF EXISTS public.dictionary_id_seq RENAME TO words_id_seq;
    END IF;
END
$$;

-- Create the new dictionary table
CREATE TABLE IF NOT EXISTS public.dictionary (
    id SERIAL PRIMARY KEY,
    word character varying(255) NOT NULL UNIQUE,
    definition text,
    audio character varying(255)
);

CREATE INDEX IF NOT EXISTS idx_dictionary_word ON public.dictionary (word);
CREATE INDEX IF NOT EXISTS idx_dictionary_word_trgm ON public.dictionary USING gin (word public.gin_trgm_ops);

COMMIT;
