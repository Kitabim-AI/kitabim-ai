-- Migration: 051_remove_embedding_model_prefix.sql
-- Description: Remove 'models/' prefix from gemini_embedding_model config value
-- Author: Antigravity
-- Date: 2026-06-12

BEGIN;

UPDATE system_configs
  SET value = REGEXP_REPLACE(value, '^models/', '')
  WHERE key = 'gemini_embedding_model';

COMMIT;
