-- Migration: 091_add_batch_llm_spell_check_jobs.sql
-- Description: Add batch_llm_spell_check_jobs table for Gemini Batch API LLM
--              spell-check processing, plus system_configs for the batch flag
--              and model
-- Author: Kitabim.AI
-- Date: 2026-09-08

BEGIN;

CREATE TABLE IF NOT EXISTS batch_llm_spell_check_jobs (
    id SERIAL PRIMARY KEY,
    gemini_batch_id VARCHAR(255) NOT NULL UNIQUE,
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_batch_llm_spell_check_jobs_book_id ON batch_llm_spell_check_jobs(book_id);

INSERT INTO system_configs (key, value, description, updated_at) VALUES
    ('llm_spell_check_batch_enabled', 'false',
     'When true, the per-book LLM spell-check trigger submits a Gemini Batch API job instead of live concurrent calls', NOW()),
    ('gemini_llm_spell_check_model', 'gemini-3.1-flash-lite',
     'Gemini model used for LLM-based spell correction, both live and batch paths', NOW())
ON CONFLICT (key) DO NOTHING;

COMMIT;
