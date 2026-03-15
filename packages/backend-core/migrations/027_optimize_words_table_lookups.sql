-- Migration: Optimize words table lookups for spell check performance
-- Description: Adds hash index for exact word lookups and optimizes join performance

-- Drop the existing B-tree index on words.word (created in migration 015)
-- We'll replace it with a hash index for exact lookups (faster than B-tree for equality)
DROP INDEX IF EXISTS idx_words_word;

-- Create hash index for exact word lookups (used in index_book_words JOIN)
-- Hash indexes are faster for equality comparisons (=) which is all we need
CREATE INDEX IF NOT EXISTS idx_words_word_hash ON words USING hash(word);

-- Add covering index on book_word_index for common query patterns
-- This helps the unique_to_book query and other cross-book lookups
CREATE INDEX IF NOT EXISTS idx_book_word_index_word_id_covering
ON book_word_index (word_id, occurrence_count)
INCLUDE (book_id);

-- Analyze tables to update query planner statistics
ANALYZE words;
ANALYZE book_word_index;
