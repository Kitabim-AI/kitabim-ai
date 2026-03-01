-- Migration 007: Remove "v2_" prefix from pipeline columns and config keys.
-- The v1 worker is gone; these are simply the worker's columns now.

-- Rename book column
ALTER TABLE books RENAME COLUMN v2_pipeline_step TO pipeline_step;

-- Rename page columns
ALTER TABLE pages RENAME COLUMN v2_pipeline_step TO pipeline_step;
ALTER TABLE pages RENAME COLUMN v2_milestone TO milestone;
ALTER TABLE pages RENAME COLUMN v2_retry_count TO retry_count;

-- Rename system config keys
UPDATE system_configs SET key = 'ocr_max_retry_count'  WHERE key = 'v2_ocr_max_retry_count';
UPDATE system_configs SET key = 'scanner_page_limit'   WHERE key = 'v2_scanner_page_limit';
UPDATE system_configs SET key = 'scanner_book_limit'   WHERE key = 'v2_scanner_book_limit';
