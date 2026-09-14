-- Migration: 092_add_llm_cost_tracking_to_rag_evaluations.sql
-- Description: Add per-turn LLM token/cost tracking columns to rag_evaluations.
--              input_tokens/output_tokens/cost_usd cover the synchronous chat
--              turn (query-signal extraction, retrieval agent, reranker,
--              answer agent, estimated embedding). judge_cost_usd is
--              nullable and backfilled by rag_eval_job after the async
--              LLM-judge scoring call completes.
-- Author: Kitabim.AI
-- Date: 2026-09-13

BEGIN;

ALTER TABLE rag_evaluations
    ADD COLUMN IF NOT EXISTS input_tokens INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS output_tokens INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS judge_cost_usd NUMERIC(12, 6);

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'rag_chat_cost_enabled',
    'true',
    'Globally show or hide answer cost information (tokens and USD) in chat windows.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
