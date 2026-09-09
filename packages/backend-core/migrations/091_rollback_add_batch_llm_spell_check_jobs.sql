-- Migration Rollback: 091_rollback_add_batch_llm_spell_check_jobs.sql
-- Description: Rollback batch_llm_spell_check_jobs table and its system_configs seeds

BEGIN;

DROP TABLE IF EXISTS batch_llm_spell_check_jobs CASCADE;

DELETE FROM system_configs WHERE key = 'llm_spell_check_batch_enabled';
DELETE FROM system_configs WHERE key = 'gemini_llm_spell_check_model';

COMMIT;
