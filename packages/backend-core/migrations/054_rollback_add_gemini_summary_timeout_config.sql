-- Migration: 054_rollback_add_gemini_summary_timeout_config.sql
-- Description: Rollback gemini_summary_timeout config key
-- Author: Antigravity
-- Date: 2026-06-16

BEGIN;

DELETE FROM system_configs WHERE key = 'gemini_summary_timeout';

COMMIT;
