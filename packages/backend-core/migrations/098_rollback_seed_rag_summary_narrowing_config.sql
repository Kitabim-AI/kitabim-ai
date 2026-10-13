-- Rollback Migration: 098_rollback_seed_rag_summary_narrowing_config.sql
-- Description: Rollback migration 098 by removing rag_summary_narrowing_enabled config
-- Author: Kitabim.AI
-- Date: 2026-10-13

BEGIN;

DELETE FROM system_configs WHERE key = 'rag_summary_narrowing_enabled';

COMMIT;
