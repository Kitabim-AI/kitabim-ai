-- Migration: 053_rollback_add_gemini_ocr_timeout_config.sql
-- Description: Rollback gemini_ocr_timeout config key
-- Author: Antigravity
-- Date: 2026-06-15

BEGIN;

DELETE FROM system_configs WHERE key = 'gemini_ocr_timeout';

COMMIT;
