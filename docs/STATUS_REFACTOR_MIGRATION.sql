-- STATUS_REFACTOR_MIGRATION.sql
-- Migration script for status naming refactor
-- Changes 'processing' → 'ocr_processing' and 'completed' → 'ocr_done'
-- Adds new statuses: 'indexing' and 'indexed'
--
-- PRE-REQUISITES:
--   1. Database backup created
--   2. All workers stopped (kubectl scale deployment worker --replicas=0)
--
-- Usage:
--   psql -h localhost -U your_user kitabim < STATUS_REFACTOR_MIGRATION.sql

BEGIN;

-- Show current state before migration
SELECT 'BEFORE MIGRATION - Books:' as info;
SELECT status, COUNT(*) FROM books GROUP BY status ORDER BY status;

SELECT 'BEFORE MIGRATION - Pages:' as info;
SELECT status, COUNT(*) FROM pages GROUP BY status ORDER BY status;

-- ========================================
-- STEP 1: Rename status values in data
-- ========================================

-- Update books table statuses
UPDATE books SET status = 'ocr_processing' WHERE status = 'processing';
UPDATE books SET status = 'ocr_done' WHERE status = 'completed';

-- Update pages table statuses
UPDATE pages SET status = 'ocr_processing' WHERE status = 'processing';
UPDATE pages SET status = 'ocr_done' WHERE status = 'completed';

-- ========================================
-- STEP 2: Rename denormalized cache column
-- ========================================

ALTER TABLE books RENAME COLUMN completed_count TO ocr_done_count;

-- ========================================
-- STEP 3: Update check constraints
-- ========================================

-- Update page status check constraint
ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_status_check;
ALTER TABLE pages ADD CONSTRAINT pages_status_check
  CHECK (status IN ('pending', 'ocr_processing', 'ocr_done', 'indexing', 'indexed', 'error'));

-- Add book status check constraint (was missing before)
ALTER TABLE books DROP CONSTRAINT IF EXISTS books_status_check;
ALTER TABLE books ADD CONSTRAINT books_status_check
  CHECK (status IN ('uploading', 'pending', 'ocr_processing', 'ocr_done', 'indexing', 'ready', 'error'));

-- ========================================
-- VERIFICATION QUERIES
-- ========================================

-- Show new state after migration
SELECT 'AFTER MIGRATION - Books:' as info;
SELECT status, COUNT(*) FROM books GROUP BY status ORDER BY status;

SELECT 'AFTER MIGRATION - Pages:' as info;
SELECT status, COUNT(*) FROM pages GROUP BY status ORDER BY status;

-- Verify no old statuses remain
SELECT 'Verify OLD statuses (should be 0):' as info;
SELECT
  (SELECT COUNT(*) FROM books WHERE status IN ('processing', 'completed')) as old_book_statuses,
  (SELECT COUNT(*) FROM pages WHERE status IN ('processing', 'completed')) as old_page_statuses;

-- Verify column rename
SELECT 'Verify column rename:' as info;
SELECT
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_name='books' AND column_name='ocr_done_count') as has_ocr_done_count,
  EXISTS(SELECT 1 FROM information_schema.columns
         WHERE table_name='books' AND column_name='completed_count') as has_completed_count;

-- Verify constraints
SELECT 'Verify constraints:' as info;
SELECT conname, consrc
FROM pg_constraint
WHERE conrelid IN ('books'::regclass, 'pages'::regclass)
  AND conname LIKE '%status_check';

COMMIT;

-- Final summary
SELECT '✅ MIGRATION COMPLETE' as status;
SELECT 'Next steps:' as info;
SELECT '1. Deploy backend code' as step;
SELECT '2. Deploy frontend code' as step;
SELECT '3. Restart workers (kubectl scale deployment worker --replicas=1)' as step;
SELECT '4. Monitor logs for 24 hours' as step;
