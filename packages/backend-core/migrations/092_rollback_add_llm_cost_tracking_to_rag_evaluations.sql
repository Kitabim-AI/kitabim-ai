-- Migration Rollback: 092_rollback_add_llm_cost_tracking_to_rag_evaluations.sql
-- Description: Rollback LLM token/cost tracking columns on rag_evaluations

BEGIN;

ALTER TABLE rag_evaluations
    DROP COLUMN IF EXISTS input_tokens,
    DROP COLUMN IF EXISTS output_tokens,
    DROP COLUMN IF EXISTS cost_usd,
    DROP COLUMN IF EXISTS judge_cost_usd;

DELETE FROM system_configs WHERE key = 'rag_chat_cost_enabled';

COMMIT;
