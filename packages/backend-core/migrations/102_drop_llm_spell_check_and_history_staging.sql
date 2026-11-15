-- Migration: 102_drop_llm_spell_check_and_history_staging.sql
-- Description: Drop retired LLM spell-check columns/tables, history dictionary staging & batch extraction tables, and retired system_configs keys.
-- Author: Kitabim.AI
-- Date: 2026-11-09

BEGIN;

ALTER TABLE public.pages
    DROP CONSTRAINT IF EXISTS pages_llm_spell_check_status_check;

ALTER TABLE public.pages
    DROP COLUMN IF EXISTS llm_spell_check_status,
    DROP COLUMN IF EXISTS llm_spell_check_at;

DROP TABLE IF EXISTS public.batch_llm_spell_check_jobs CASCADE;
DROP TABLE IF EXISTS public.history_dictionary_staging CASCADE;
DROP TABLE IF EXISTS public.batch_history_extraction_jobs CASCADE;

DELETE FROM public.system_configs
WHERE key IN (
    'llm_spell_check_batch_enabled',
    'gemini_llm_spell_check_model',
    'gemini_llm_spell_check_timeout',
    'history_extraction_enabled',
    'history_gemini_model',
    'history_batch_enabled',
    'history_batch_size',
    'history_extraction_model',
    'history_extraction_batch_size',
    'gemini_batch_history_extraction_enabled'
);

COMMIT;
