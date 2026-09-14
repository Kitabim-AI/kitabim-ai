-- Migration: 090_add_llm_spell_check_status_to_pages.sql
-- Description: Add llm_spell_check_status and llm_spell_check_at columns to pages
--              for the on-demand Gemini-based spell correction pass
-- Author: Kitabim.AI
-- Date: 2026-09-08

BEGIN;

ALTER TABLE public.pages
    ADD COLUMN IF NOT EXISTS llm_spell_check_status VARCHAR(20) NOT NULL DEFAULT 'idle';

ALTER TABLE public.pages
    ADD COLUMN IF NOT EXISTS llm_spell_check_at TIMESTAMPTZ NULL;

COMMIT;
