-- Migration: Add worker v2 pipeline columns
-- Created: 2026-02-28
-- Description: Adds v2_pipeline_step, v2_milestone, and v2_retry_count to pages,
--              and v2_pipeline_step to books. V1 columns are untouched.
--              Worker v2 uses these columns exclusively; v1 continues using status.

ALTER TABLE pages
    ADD COLUMN IF NOT EXISTS v2_pipeline_step VARCHAR(20),
    ADD COLUMN IF NOT EXISTS v2_milestone      VARCHAR(20),
    ADD COLUMN IF NOT EXISTS v2_retry_count   INTEGER NOT NULL DEFAULT 0;

ALTER TABLE books
    ADD COLUMN IF NOT EXISTS v2_pipeline_step VARCHAR(20);

-- Seed default worker v2 system configs
INSERT INTO system_configs (key, value, description)
VALUES
    ('v2_ocr_max_retry_count', '3',
     'Worker v2: Maximum OCR retry attempts per page before the page is skipped'),
    ('v2_scanner_page_limit', '100',
     'Worker v2: Maximum pages claimed per chunking/embedding scanner run'),
    ('v2_scanner_book_limit', '10',
     'Worker v2: Maximum books dispatched per OCR scanner run')
ON CONFLICT (key) DO NOTHING;
