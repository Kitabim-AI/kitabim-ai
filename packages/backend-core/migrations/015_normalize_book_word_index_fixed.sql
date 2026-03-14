-- Migration 015: Normalize book_word_index to use word IDs instead of TEXT
--
-- Problem: With 8M records for 500 books, storing word TEXT repeatedly wastes space.
-- Projected 32M rows for 2000 books would consume ~4GB+ storage.
--
-- Solution: Use integer word IDs to reduce storage by 60-80% and improve query performance.
--
-- Steps:
-- 1. Rename existing 'words' table (dictionary) to 'dictionary'
-- 2. Create new 'words' table with auto-increment IDs
-- 3. Create new 'book_word_index_new' table with word_id foreign key
-- 4. Populate new tables from existing book_word_index
-- 5. Swap tables atomically
--
-- IMPORTANT: Run this during low-traffic period. Estimated time: 2-5 minutes for 8M rows.

BEGIN;

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 1: Rename existing words table to dictionary
-- ──────────────────────────────────────────────────────────────────────────────

-- Check if words table exists before renaming
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'words') THEN
        -- Rename the table
        ALTER TABLE words RENAME TO dictionary;

        -- Rename the sequence if it exists
        IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'words_id_seq') THEN
            ALTER SEQUENCE words_id_seq RENAME TO dictionary_id_seq;
        END IF;

        -- Rename indexes
        ALTER INDEX IF EXISTS words_pkey RENAME TO dictionary_pkey;

        RAISE NOTICE 'Renamed words table to dictionary';
    ELSE
        RAISE NOTICE 'words table does not exist, skipping rename';
    END IF;
END $$;

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 2: Create new words table with unique word list and IDs
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS words (
    id SERIAL PRIMARY KEY,
    word TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_words_word ON words(word);

COMMENT ON TABLE words IS 'Normalized word vocabulary table for efficient storage and lookup';
COMMENT ON COLUMN words.id IS 'Auto-increment word ID to replace TEXT storage in book_word_index';
COMMENT ON COLUMN words.word IS 'Unique normalized word form';

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 3: Create new book_word_index_new table with word_id FK
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS book_word_index_new (
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (book_id, word_id)
);

CREATE INDEX IF NOT EXISTS idx_book_word_index_new_word_id ON book_word_index_new(word_id, book_id);

COMMENT ON TABLE book_word_index_new IS 'Normalized book-word index using word IDs instead of TEXT for 60-80% storage reduction';
COMMENT ON COLUMN book_word_index_new.word_id IS 'Foreign key to words.id for normalized storage';

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 4: Populate new tables from existing book_word_index
-- ──────────────────────────────────────────────────────────────────────────────

-- First, extract all unique words from book_word_index into the words table
INSERT INTO words (word)
SELECT DISTINCT word
FROM book_word_index
ON CONFLICT (word) DO NOTHING;

-- Log progress (wrapped in DO block)
DO $$
BEGIN
    RAISE NOTICE 'Populated words table with % unique words', (SELECT COUNT(*) FROM words);
END $$;

-- Now populate book_word_index_new by joining with words to get word_id
-- This is the longest step - it processes all 8M rows
INSERT INTO book_word_index_new (book_id, word_id, occurrence_count)
SELECT bwi.book_id, w.id, bwi.occurrence_count
FROM book_word_index bwi
INNER JOIN words w ON w.word = bwi.word
ON CONFLICT (book_id, word_id) DO UPDATE
SET occurrence_count = EXCLUDED.occurrence_count;

-- Log progress (wrapped in DO block)
DO $$
BEGIN
    RAISE NOTICE 'Populated book_word_index_new with % records', (SELECT COUNT(*) FROM book_word_index_new);
END $$;

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 5: Verify data integrity before swap
-- ──────────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
    old_count BIGINT;
    new_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO old_count FROM book_word_index;
    SELECT COUNT(*) INTO new_count FROM book_word_index_new;

    IF old_count != new_count THEN
        RAISE EXCEPTION 'Data migration failed: old table has % rows, new table has % rows', old_count, new_count;
    END IF;

    RAISE NOTICE 'Verification passed: both tables have % rows', old_count;
END $$;

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 6: Atomic table swap
-- ──────────────────────────────────────────────────────────────────────────────

-- Drop old table and rename new one
DROP TABLE book_word_index CASCADE;

ALTER TABLE book_word_index_new RENAME TO book_word_index;

-- Rename indexes to match original naming
ALTER INDEX idx_book_word_index_new_word_id RENAME TO idx_book_word_index_word_id;

-- Rename primary key constraint
ALTER TABLE book_word_index RENAME CONSTRAINT book_word_index_new_pkey TO book_word_index_pkey;

-- Log completion (wrapped in DO block)
DO $$
BEGIN
    RAISE NOTICE 'Migration complete: book_word_index now uses normalized word IDs';
END $$;

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 7: Analyze tables for query planner
-- ──────────────────────────────────────────────────────────────────────────────

ANALYZE words;
ANALYZE book_word_index;

-- ──────────────────────────────────────────────────────────────────────────────
-- STEP 8: Print storage savings summary
-- ──────────────────────────────────────────────────────────────────────────────

DO $$
DECLARE
    table_size TEXT;
    index_size TEXT;
    total_size TEXT;
BEGIN
    SELECT
        pg_size_pretty(pg_total_relation_size('book_word_index')) INTO total_size;
    SELECT
        pg_size_pretty(pg_relation_size('book_word_index')) INTO table_size;
    SELECT
        pg_size_pretty(pg_indexes_size('book_word_index')) INTO index_size;

    RAISE NOTICE 'New book_word_index total size: %', total_size;
    RAISE NOTICE 'Table size: %, Index size: %', table_size, index_size;
END $$;

COMMIT;
