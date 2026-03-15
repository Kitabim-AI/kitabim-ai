-- Migration: Optimize random book with issues query
-- Description: Adds covering index to dramatically speed up the spell-check random book endpoint

-- Covering index for the random book selection query
-- This index allows Postgres to use an index-only scan for finding books with open spell issues
-- The index includes (page_id, status) which covers the WHERE clause and JOIN conditions
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_spell_issues_page_status_covering
ON page_spell_issues (page_id, status)
WHERE status = 'open';

-- Index on pages.book_id for efficient reverse lookup from page to book
-- This speeds up the DISTINCT ON (p.book_id) operation
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pages_book_id
ON pages (book_id);

-- Analyze tables to update query planner statistics after adding indexes
ANALYZE page_spell_issues;
ANALYZE pages;
ANALYZE books;
