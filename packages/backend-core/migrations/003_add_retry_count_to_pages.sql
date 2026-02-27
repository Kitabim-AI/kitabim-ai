-- Migration: Add retry_count column to pages table
-- Created: 2026-02-26
-- Description: Tracks how many times OCR has been attempted on a page.
--              When retry_count reaches ocr_max_retry_count (system config),
--              the page is skipped and marked as done to prevent infinite retry loops.

ALTER TABLE pages
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;

-- Seed the default max retry config (admin can change via system_configs API)
INSERT INTO system_configs (key, value, description)
VALUES (
    'ocr_max_retry_count',
    '3',
    'Maximum number of OCR retry attempts per page before the page is skipped and marked as done'
)
ON CONFLICT (key) DO NOTHING;
