-- Migration 006: Drop v1 worker columns and tables
-- Safe to run: all columns/tables use IF EXISTS guards

-- v1 book columns
ALTER TABLE books DROP COLUMN IF EXISTS processing_step;
ALTER TABLE books DROP COLUMN IF EXISTS processing_lock;
ALTER TABLE books DROP COLUMN IF EXISTS processing_lock_expires_at;
ALTER TABLE books DROP COLUMN IF EXISTS ocr_done_count;
ALTER TABLE books DROP COLUMN IF EXISTS error_count;

-- v1 page column
ALTER TABLE pages DROP COLUMN IF EXISTS retry_count;

-- v1 job tracking table
DROP TABLE IF EXISTS jobs;

-- Gemini batch tables
DROP TABLE IF EXISTS batch_requests;
DROP TABLE IF EXISTS batch_jobs;
