-- Rollback Migration 101: Revert book structure milestone, book_sections table, and section-stream chunking columns
BEGIN;

-- 1. Revert chunks columns and indexes
DROP INDEX IF EXISTS idx_chunks_book_text_hash;
DROP INDEX IF EXISTS idx_chunks_book_section;

ALTER TABLE chunks
    DROP COLUMN IF EXISTS text_hash,
    DROP COLUMN IF EXISTS section_id,
    DROP COLUMN IF EXISTS end_page_number;

-- 2. Drop book_sections table and indexes
DROP INDEX IF EXISTS idx_book_sections_norm_title;
DROP INDEX IF EXISTS idx_book_sections_book_norm_title;
DROP INDEX IF EXISTS idx_book_sections_parent_id;
DROP INDEX IF EXISTS idx_book_sections_book_id;
DROP TABLE IF EXISTS book_sections;

-- 3. Revert pages columns and index
DROP INDEX IF EXISTS idx_pages_book_content_page;

ALTER TABLE pages
    DROP COLUMN IF EXISTS content_page_number_manual,
    DROP COLUMN IF EXISTS detected_page_number;

-- 4. Revert books columns and constraint
ALTER TABLE books
    DROP CONSTRAINT IF EXISTS books_structure_milestone_check;

ALTER TABLE books
    DROP COLUMN IF EXISTS gcs_ocr_backup_uri,
    DROP COLUMN IF EXISTS ocr_backfill_at,
    DROP COLUMN IF EXISTS ocr_version,
    DROP COLUMN IF EXISTS embedding_claimed_at,
    DROP COLUMN IF EXISTS embedding_retry_count,
    DROP COLUMN IF EXISTS chunking_claimed_at,
    DROP COLUMN IF EXISTS chunking_retry_count,
    DROP COLUMN IF EXISTS structure_claimed_at,
    DROP COLUMN IF EXISTS structure_retry_count,
    DROP COLUMN IF EXISTS structure_milestone;

-- 5. Revert system_configs
DELETE FROM system_configs
WHERE key = 'embed_gemini_batch_timeout';

UPDATE system_configs
SET value = '1000', updated_at = NOW()
WHERE key = 'embed_batch_max_chunks_per_job' AND value = '5000';

COMMIT;
