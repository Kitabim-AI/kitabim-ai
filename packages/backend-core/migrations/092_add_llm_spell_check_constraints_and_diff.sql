-- Migration: 092_add_llm_spell_check_constraints_and_diff.sql
-- Description: Add check constraints for llm_spell_check_status and batch job status,
--              plus prev_text column on pages for undo/diff tracking.
-- Author: Kitabim.AI
-- Date: 2026-10-14

BEGIN;

-- 1. Add column to store original text before LLM correction
ALTER TABLE public.pages
    ADD COLUMN IF NOT EXISTS prev_text TEXT NULL;

-- 2. Add CHECK constraint on pages.llm_spell_check_status
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

-- 3. Add CHECK constraint on batch_llm_spell_check_jobs.status
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'batch_llm_spell_check_jobs_status_check'
    ) THEN
        ALTER TABLE public.batch_llm_spell_check_jobs
            ADD CONSTRAINT batch_llm_spell_check_jobs_status_check
            CHECK (status IN ('submitting', 'running', 'succeeded', 'failed', 'cancelled', 'expired'));
    END IF;
END $$;

COMMIT;
