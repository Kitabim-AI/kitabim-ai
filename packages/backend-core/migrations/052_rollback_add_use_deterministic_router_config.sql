-- Migration: 052_rollback_add_use_deterministic_router_config.sql
-- Description: Rollback use_deterministic_router config key
-- Author: Antigravity
-- Date: 2026-06-14

BEGIN;

DELETE FROM system_configs WHERE key = 'use_deterministic_router';

COMMIT;
