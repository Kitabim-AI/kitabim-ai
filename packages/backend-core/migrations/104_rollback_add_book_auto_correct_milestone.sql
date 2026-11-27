-- Rollback Migration 104: Drop book-level auto_correct_milestone
BEGIN;

ALTER TABLE books
    DROP CONSTRAINT IF EXISTS books_auto_correct_milestone_check,
    DROP COLUMN IF EXISTS auto_correct_milestone;

COMMIT;
