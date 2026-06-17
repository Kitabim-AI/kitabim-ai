-- Migration: 053_add_gemini_ocr_timeout_config.sql
-- Description: Add gemini_ocr_timeout config key to system_configs table
-- Author: Antigravity
-- Date: 2026-06-15

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'gemini_ocr_timeout',
    '120',
    'Timeout in seconds for Gemini OCR vision API calls.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
