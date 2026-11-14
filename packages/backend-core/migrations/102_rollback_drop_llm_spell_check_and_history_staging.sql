-- Migration Rollback: 102_rollback_drop_llm_spell_check_and_history_staging.sql
-- Description: Recreate retired LLM spell-check columns/tables, history staging/batch tables, and default system_configs keys.
-- Author: Kitabim.AI
-- Date: 2026-11-09

BEGIN;

ALTER TABLE public.pages
    ADD COLUMN IF NOT EXISTS llm_spell_check_status VARCHAR(20) NOT NULL DEFAULT 'idle',
    ADD COLUMN IF NOT EXISTS llm_spell_check_at TIMESTAMPTZ NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'pages_llm_spell_check_status_check'
    ) THEN
        ALTER TABLE public.pages
            ADD CONSTRAINT pages_llm_spell_check_status_check
            CHECK (llm_spell_check_status IN ('idle', 'in_progress', 'succeeded', 'failed'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.batch_llm_spell_check_jobs (
    id SERIAL PRIMARY KEY,
    gemini_batch_id VARCHAR(255) NOT NULL UNIQUE,
    book_id VARCHAR(64) NOT NULL REFERENCES public.books(id) ON DELETE CASCADE,
    page_ids INTEGER[] NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'submitting',
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_batches INTEGER NOT NULL DEFAULT 1,
    model_name VARCHAR(100),
    error TEXT,
    submitted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT batch_llm_spell_check_jobs_status_check CHECK (
        status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_batch_llm_spell_check_jobs_book_id ON public.batch_llm_spell_check_jobs(book_id);

CREATE TABLE IF NOT EXISTS public.batch_history_extraction_jobs (
    id VARCHAR(64) PRIMARY KEY,
    gemini_batch_id VARCHAR(255) UNIQUE,
    book_id VARCHAR(64) NOT NULL REFERENCES public.books(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'submitting',
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_batches INT NOT NULL DEFAULT 0,
    min_significance INT NOT NULL DEFAULT 5,
    model_name VARCHAR(100) NOT NULL DEFAULT 'gemini-3.1-flash-lite-preview',
    error TEXT,
    submitted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_batch_history_jobs_status CHECK (
        status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_batch_history_jobs_book_id ON public.batch_history_extraction_jobs(book_id);
CREATE INDEX IF NOT EXISTS idx_batch_history_jobs_status ON public.batch_history_extraction_jobs(status);

CREATE TABLE IF NOT EXISTS public.history_dictionary_staging (
    id SERIAL PRIMARY KEY,
    existing_dictionary_id INTEGER REFERENCES public.history_dictionary(id) ON DELETE SET NULL,
    book_id VARCHAR(64) NOT NULL,
    term VARCHAR(500) NOT NULL,
    transliteration TEXT,
    definition TEXT,
    original_definition TEXT,
    category VARCHAR(30) NOT NULL DEFAULT 'general',
    significance_score INTEGER NOT NULL DEFAULT 5,
    significance_reason TEXT,
    is_ai_generated BOOLEAN NOT NULL DEFAULT TRUE,
    entry_type VARCHAR(20) NOT NULL DEFAULT 'new',
    letter_group VARCHAR(10) NOT NULL,
    facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_staging_term ON public.history_dictionary_staging(term);
CREATE INDEX IF NOT EXISTS idx_history_staging_status ON public.history_dictionary_staging(status);
CREATE INDEX IF NOT EXISTS idx_history_staging_sig ON public.history_dictionary_staging(significance_score DESC);
CREATE INDEX IF NOT EXISTS idx_history_staging_entry_type ON public.history_dictionary_staging(entry_type);

INSERT INTO public.system_configs (key, value, description, updated_at) VALUES
    ('llm_spell_check_batch_enabled', 'false', 'When true, the per-book LLM spell-check trigger submits a Gemini Batch API job instead of live concurrent calls', NOW()),
    ('gemini_llm_spell_check_model', 'gemini-3.1-flash-lite-preview', 'Gemini model used for LLM-based spell correction, both live and batch paths', NOW()),
    ('gemini_llm_spell_check_timeout', '60', 'Timeout in seconds for individual LLM spell-check Gemini API calls', NOW()),
    ('history_extraction_enabled', 'false', 'Enable automatic history dictionary term extraction during book processing', NOW()),
    ('history_gemini_model', 'gemini-3.1-flash-lite-preview', 'Gemini model used for history term extraction', NOW()),
    ('history_batch_enabled', 'false', 'Enable Gemini Batch API for history dictionary extraction', NOW()),
    ('history_batch_size', '15', 'Number of pages per history extraction batch call', NOW())
ON CONFLICT (key) DO NOTHING;

COMMIT;
