-- Migration: 097_seed_max_book_upload_mb_system_config.sql
-- Description: Seed sys_max_book_upload_mb system configuration key
-- Author: Kitabim.AI
-- Date: 2026-10-07

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'sys_max_book_upload_mb',
    '500',
    'Maximum allowed book upload file size in megabytes (MB).',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
