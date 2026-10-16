-- Migration: 100_rollback_add_gemini_llm_spell_check_timeout_config.sql
-- Description: Rollback gemini_llm_spell_check_timeout config key

BEGIN;

DELETE FROM system_configs WHERE key = 'gemini_llm_spell_check_timeout';

COMMIT;
