-- Migration: 054_add_gemini_summary_timeout_config.sql
-- Description: Add gemini_summary_timeout config key to system_configs table
-- Author: Antigravity
-- Date: 2026-06-16

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'gemini_summary_timeout',
    '300',
    'Timeout in seconds for Gemini book summary generation API calls.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
