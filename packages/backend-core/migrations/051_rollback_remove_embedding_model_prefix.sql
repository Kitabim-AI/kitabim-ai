-- Migration Rollback: 051_rollback_remove_embedding_model_prefix.sql
-- Description: Restore 'models/' prefix to gemini_embedding_model config value
-- Author: Antigravity
-- Date: 2026-06-12

BEGIN;

UPDATE system_configs
  SET value = 'models/' || value
  WHERE key = 'gemini_embedding_model' AND NOT value LIKE 'models/%';

COMMIT;
