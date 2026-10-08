-- Rollback Migration: 097_rollback_seed_max_book_upload_mb_system_config.sql
-- Description: Rollback migration 097 by removing sys_max_book_upload_mb config
-- Author: Kitabim.AI
-- Date: 2026-10-07

BEGIN;

DELETE FROM system_configs WHERE key = 'sys_max_book_upload_mb';

COMMIT;
