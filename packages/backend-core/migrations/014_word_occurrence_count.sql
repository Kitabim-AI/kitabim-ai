-- Migration: Add occurrence_count to book_word_index and reset milestones for re-indexing
-- Reason: Enables frequency-aware spell checking (knowing how many times a word appears in a book)

-- 1. Add the occurrence_count column
-- Default to 1 to satisfy non-null constraint for existing (temporary) records
ALTER TABLE book_word_index 
ADD COLUMN IF NOT EXISTS occurrence_count INTEGER DEFAULT 1 NOT NULL;

-- 2. Clear existing index (Option 1: Clean Sweep)
-- This ensures we build accurate counts from scratch rather than having partial data
TRUNCATE TABLE book_word_index;

-- 3. Reset page milestones to trigger the background scanner
-- This will mark all pages with text as ready for the word_index_scanner to pick up
UPDATE pages 
SET word_index_milestone = 'idle'
WHERE text IS NOT NULL;

-- 4. Set a comment for documentation
COMMENT ON COLUMN book_word_index.occurrence_count IS 'How many times this word appears in this specific book';
