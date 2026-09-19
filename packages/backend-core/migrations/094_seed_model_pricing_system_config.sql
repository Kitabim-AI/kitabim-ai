-- Migration: 094_seed_model_pricing_system_config.sql
-- Description: Seed Gemini model pricing system configuration (JSON format)
-- Author: Kitabim.AI
-- Date: 2026-09-18

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'sys_llm_model_pricing',
    '{"gemini-2.5-flash":{"input":0.30,"output":2.50},"gemini-2.5-flash-lite":{"input":0.10,"output":0.40},"gemini-2.5-pro":{"input":1.25,"output":10.00},"gemini-3.1-flash-lite":{"input":0.10,"output":0.40},"gemini-3.5-flash-lite":{"input":0.10,"output":0.40},"gemini-3.7-flash":{"input":0.30,"output":2.50},"gemini-embedding-2":{"input":0.15,"output":0.0},"_fallback":{"input":0.30,"output":2.50}}',
    'JSON dictionary of Gemini model pricing (USD per 1M tokens) for input and output tokens.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
