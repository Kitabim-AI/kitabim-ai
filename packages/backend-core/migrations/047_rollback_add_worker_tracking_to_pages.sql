-- Rollback Migration: 047_add_worker_tracking_to_pages.sql
-- Description: Drop worker_id and claimed_at columns from pages table
-- Author: Antigravity
-- Date: 2026-06-06

BEGIN;

ALTER TABLE pages DROP COLUMN IF EXISTS worker_id;
ALTER TABLE pages DROP COLUMN IF EXISTS claimed_at;

COMMIT;
