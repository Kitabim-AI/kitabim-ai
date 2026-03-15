-- Migration: Cleanup redundant indexes after book-level milestone refactoring
-- Description: Removes indexes that are no longer used or are duplicates.

-- 1. Drop terminal book detection index (idx_pages_book_id_terminal)
-- Reason: The query in pipeline_driver.py doesn't filter by book_id in the WHERE clause.
--         It uses UNION ALL of separate milestone queries, each already covered by:
--         - idx_pages_embedding_milestone_failed
--         - idx_pages_retry_count_low
DROP INDEX IF EXISTS idx_pages_book_id_terminal;

-- 2. Drop redundant id+book_id index (idx_pages_id_book_id)
-- Reason: No queries use this specific column combination.
--         Most queries filter by book_id alone (covered by idx_pages_book_id)
--         or by id alone (covered by pages_pkey).
DROP INDEX IF EXISTS idx_pages_id_book_id;

-- 3. Drop duplicate categories index (idx_books_categories)
-- Reason: Duplicate of idx_books_categories_gin. Both are GIN indexes on same column.
--         Keep idx_books_categories_gin (more explicit naming).
DROP INDEX IF EXISTS idx_books_categories;

-- 4. Drop redundant content_hash index (idx_books_content_hash)
-- Reason: Duplicate of books_content_hash_key (unique constraint creates index automatically).
--         The unique constraint index is sufficient.
DROP INDEX IF EXISTS idx_books_content_hash;

-- Summary of removed indexes:
-- - idx_pages_book_id_terminal: Not used by current query patterns
-- - idx_pages_id_book_id: No queries use this column combination
-- - idx_books_categories: Duplicate of idx_books_categories_gin
-- - idx_books_content_hash: Duplicate of books_content_hash_key unique constraint

-- Indexes KEPT and actively used:
--
-- Books table milestone indexes (used by scanners to filter books):
--   - idx_books_ocr_milestone (partial: != 'complete')
--   - idx_books_chunking_milestone (partial: != 'complete')
--   - idx_books_embedding_milestone (partial: != 'complete')
--   - idx_books_word_index_milestone (partial: != 'complete')
--   - idx_books_spell_check_milestone (partial: != 'complete')
--
-- Pages table milestone indexes (used by scanners to find idle/failed pages):
--   - idx_pages_ocr_milestone_idle
--   - idx_pages_ocr_milestone_failed
--   - idx_pages_chunking_milestone_idle
--   - idx_pages_chunking_milestone_failed
--   - idx_pages_embedding_milestone_idle
--   - idx_pages_embedding_milestone_failed
--   - idx_pages_word_index_milestone (idle)
--   - idx_pages_word_index_milestone_failed
--   - idx_pages_spell_check_milestone_idle
--   - idx_pages_spell_check_milestone_failed
--   - idx_pages_spell_check_milestone_incomplete
--
-- Pages table composite index (used by get_batch_stats and get_with_page_stats):
--   - idx_pages_book_milestones (book_id + all 5 milestone columns)
--
-- Other essential indexes:
--   - idx_pages_book_id (general book_id lookups)
--   - idx_pages_book_page (book_id + page_number lookups)
--   - idx_pages_retry_count_low (retry logic)
--   - idx_pages_word_index_spell_check_ready (spell check scanner)
