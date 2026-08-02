-- Migration: 073_create_history_dictionary_staging.sql
-- Description: Create history_dictionary_staging table and enhance history_dictionary with metadata columns
-- Author: Omarjan
-- Date: 2026-08-02

BEGIN;

ALTER TABLE public.history_dictionary
    ADD COLUMN IF NOT EXISTS category VARCHAR(30) DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS significance_score INTEGER DEFAULT 5,
    ADD COLUMN IF NOT EXISTS is_ai_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS sources JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_history_dictionary_category ON public.history_dictionary(category);
CREATE INDEX IF NOT EXISTS idx_history_dictionary_ai_gen ON public.history_dictionary(is_ai_generated);
CREATE INDEX IF NOT EXISTS idx_history_dictionary_sig ON public.history_dictionary(significance_score DESC);

CREATE TABLE IF NOT EXISTS public.history_dictionary_staging (
    id                     SERIAL PRIMARY KEY,
    existing_dictionary_id INTEGER REFERENCES public.history_dictionary(id) ON DELETE SET NULL,
    book_id                VARCHAR(64) NOT NULL,
    term                   VARCHAR(500) NOT NULL,
    transliteration        TEXT,
    definition             TEXT NOT NULL,
    original_definition    TEXT,
    category               VARCHAR(30) NOT NULL DEFAULT 'general',
    significance_score     INTEGER NOT NULL DEFAULT 5,
    significance_reason    TEXT,
    is_ai_generated        BOOLEAN NOT NULL DEFAULT TRUE,
    entry_type             VARCHAR(20) NOT NULL DEFAULT 'new',
    letter_group           VARCHAR(10) NOT NULL,
    sources                JSONB NOT NULL DEFAULT '[]'::jsonb,
    status                 VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_staging_term ON public.history_dictionary_staging(term);
CREATE INDEX IF NOT EXISTS idx_history_staging_status ON public.history_dictionary_staging(status);
CREATE INDEX IF NOT EXISTS idx_history_staging_sig ON public.history_dictionary_staging(significance_score DESC);
CREATE INDEX IF NOT EXISTS idx_history_staging_entry_type ON public.history_dictionary_staging(entry_type);

COMMIT;
