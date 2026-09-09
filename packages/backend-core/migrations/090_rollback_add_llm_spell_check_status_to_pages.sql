-- Migration Rollback: 090_rollback_add_llm_spell_check_status_to_pages.sql
-- Description: Rollback adding llm_spell_check_status/llm_spell_check_at to pages

BEGIN;

ALTER TABLE public.pages
    DROP COLUMN IF EXISTS llm_spell_check_status;

ALTER TABLE public.pages
    DROP COLUMN IF EXISTS llm_spell_check_at;

COMMIT;
