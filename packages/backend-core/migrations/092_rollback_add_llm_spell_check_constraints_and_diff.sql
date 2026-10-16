-- Migration Rollback: 092_rollback_add_llm_spell_check_constraints_and_diff.sql
BEGIN;

ALTER TABLE public.pages
    DROP CONSTRAINT IF EXISTS pages_llm_spell_check_status_check;

ALTER TABLE public.batch_llm_spell_check_jobs
    DROP CONSTRAINT IF EXISTS batch_llm_spell_check_jobs_status_check;

ALTER TABLE public.pages
    DROP COLUMN IF EXISTS prev_text;

COMMIT;
