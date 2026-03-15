-- Migration: Optimize book_word_index upsert performance
-- Description: Improves index_book_words query performance to prevent timeouts

-- Ensure we have a proper btree index on words.word for the CTE join
-- This is in addition to the unique constraint, optimized for lookup performance
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_words_word_btree
ON words (word);

-- Add a partial index on book_word_index for conflict resolution
-- This speeds up the ON CONFLICT clause significantly
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_book_word_index_book_id
ON book_word_index (book_id);

-- Analyze tables to update query planner statistics
ANALYZE words;
ANALYZE book_word_index;
