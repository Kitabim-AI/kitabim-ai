-- STATUS_REFACTOR_ROLLBACK.sql
-- Rollback script for status naming refactor
--
-- WARNING: Run this ONLY if you need to rollback the migration
-- This should be run BEFORE deploying new code
--
-- Usage:
--   psql -h localhost -U your_user kitabim < STATUS_REFACTOR_ROLLBACK.sql

BEGIN;

-- Rollback status values in books table
UPDATE books SET status = 'processing' WHERE status = 'ocr_processing';
UPDATE books SET status = 'completed' WHERE status = 'ocr_done';
UPDATE books SET status = 'processing' WHERE status = 'indexing';

-- Rollback status values in pages table
UPDATE pages SET status = 'processing' WHERE status = 'ocr_processing';
UPDATE pages SET status = 'completed' WHERE status = 'ocr_done';
UPDATE pages SET status = 'processing' WHERE status = 'indexing';
UPDATE pages SET status = 'completed' WHERE status = 'indexed';

-- Rollback denormalized cache column
ALTER TABLE books RENAME COLUMN ocr_done_count TO completed_count;

-- Rollback page status check constraint
ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_status_check;
ALTER TABLE pages ADD CONSTRAINT pages_status_check
  CHECK (status IN ('pending', 'processing', 'completed', 'error'));

-- Rollback book status check constraint
ALTER TABLE books DROP CONSTRAINT IF EXISTS books_status_check;

COMMIT;

-- Verify rollback
SELECT 'Books status distribution:' as info;
SELECT status, COUNT(*) FROM books GROUP BY status;

SELECT 'Pages status distribution:' as info;
SELECT status, COUNT(*) FROM pages GROUP BY status;

SELECT 'Column check:' as info;
SELECT column_name FROM information_schema.columns
WHERE table_name='books' AND column_name IN ('completed_count', 'ocr_done_count');
