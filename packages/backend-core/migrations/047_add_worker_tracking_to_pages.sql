-- Migration: 047_add_worker_tracking_to_pages.sql
-- Description: Add worker_id and claimed_at to pages table for precise stale watchdog recovery
-- Author: Antigravity
-- Date: 2026-06-06

BEGIN;

ALTER TABLE pages ADD COLUMN IF NOT EXISTS worker_id VARCHAR(255) NULL;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP WITH TIME ZONE NULL;

COMMIT;
