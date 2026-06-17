-- Migration: 052_add_use_deterministic_router_config.sql
-- Description: Add use_deterministic_router config key to system_configs table
-- Author: Antigravity
-- Date: 2026-06-14

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'use_deterministic_router',
    'false',
    'Globally enable/disable the deterministic Python RAG router instead of the LLM-driven ADK ReAct agent. Set to ''true'' to activate.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
