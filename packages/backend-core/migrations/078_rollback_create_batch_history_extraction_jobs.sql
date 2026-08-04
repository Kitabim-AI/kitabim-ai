-- Rollback Migration 078: Drop batch_history_extraction_jobs table

DROP TABLE IF EXISTS batch_history_extraction_jobs CASCADE;
DELETE FROM system_configs WHERE key = 'gemini_batch_history_extraction_enabled';
