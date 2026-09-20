-- Rollback Migration: 094_rollback_seed_model_pricing_system_config.sql
-- Description: Rollback migration 094 by removing sys_llm_model_pricing config
-- Author: Kitabim.AI
-- Date: 2026-09-18

BEGIN;

DELETE FROM system_configs WHERE key = 'sys_llm_model_pricing';

COMMIT;
