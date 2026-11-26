-- Migration 104: Add book-level auto_correct_milestone for per-book Admin OCR Auto-Correct progress icon
BEGIN;

ALTER TABLE books
    ADD COLUMN IF NOT EXISTS auto_correct_milestone VARCHAR(20) NOT NULL DEFAULT 'idle';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'books_auto_correct_milestone_check'
    ) THEN
        ALTER TABLE books
            ADD CONSTRAINT books_auto_correct_milestone_check
            CHECK (auto_correct_milestone IN ('idle', 'in_progress', 'complete', 'partial_failure', 'failed'));
    END IF;
END $$;

COMMIT;
