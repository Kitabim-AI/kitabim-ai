-- Rollback for Migration 015: Revert normalized book_word_index back to TEXT-based schema
--
-- WARNING: Only use this if migration 015 failed or needs to be reverted.
-- This will restore the old schema but you may lose data written after migration.

BEGIN;

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 1: Create old-style book_word_index table
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS book_word_index_old (
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (book_id, word)
);

CREATE INDEX IF NOT EXISTS idx_book_word_index_old_word ON book_word_index_old(word, book_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 2: Restore data from new schema to old schema
-- ──────────────────────────────────────────────────────────────────────────────

INSERT INTO book_word_index_old (book_id, word, occurrence_count)
SELECT bwi.book_id, w.word, bwi.occurrence_count
FROM book_word_index bwi
INNER JOIN words w ON w.id = bwi.word_id;

RAISE NOTICE 'Restored % records to old schema', (SELECT COUNT(*) FROM book_word_index_old);

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 3: Drop new tables and restore old naming
-- ──────────────────────────────────────────────────────────────────────────────

DROP TABLE book_word_index CASCADE;
DROP TABLE words CASCADE;

ALTER TABLE book_word_index_old RENAME TO book_word_index;
ALTER INDEX idx_book_word_index_old_word RENAME TO idx_book_word_index_word;

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 4: Restore words table from dictionary
-- ──────────────────────────────────────────────────────────────────────────────

ALTER TABLE dictionary RENAME TO words;
ALTER SEQUENCE IF EXISTS dictionary_id_seq RENAME TO words_id_seq;
ALTER INDEX IF EXISTS dictionary_pkey RENAME TO words_pkey;

RAISE NOTICE 'Rollback complete: restored to TEXT-based schema';

ANALYZE book_word_index;
ANALYZE words;

COMMIT;
