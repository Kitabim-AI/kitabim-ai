-- Rollback Migration: 093_rollback_update_history_model_to_gemini_3_5_flash_lite.sql
-- Description: Rollback history extraction Gemini model default and config to gemini-2.5-flash
-- Author: Kitabim.AI
-- Date: 2026-09-18

BEGIN;

UPDATE system_configs
SET value = 'gemini-2.5-flash', updated_at = NOW()
WHERE key IN ('history_gemini_model', 'history_extraction_model')
  AND value = 'gemini-3.5-flash-lite';

ALTER TABLE batch_history_extraction_jobs
    ALTER COLUMN model_name SET DEFAULT 'gemini-2.5-flash';

COMMIT;
