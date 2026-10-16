-- Migration: 100_add_gemini_llm_spell_check_timeout_config.sql
-- Description: Add gemini_llm_spell_check_timeout config key to system_configs table
-- Author: Antigravity
-- Date: 2026-10-16

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'gemini_llm_spell_check_timeout',
    '180',
    'Timeout in seconds for Gemini LLM spell check generation API calls.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
