-- Migration: Add indexes for spell check API performance
-- Description: Improves the performance of get_random_book_with_issues and other summary queries.

-- Index for fast join between pages and books looking for issues
CREATE INDEX IF NOT EXISTS idx_pages_id_book_id ON pages (id, book_id);

-- Index for status filtering on spell issues
CREATE INDEX IF NOT EXISTS idx_spell_issues_status ON page_spell_issues (status);

-- Composite index for fast joins and filtering by book/status
CREATE INDEX IF NOT EXISTS idx_spell_issues_page_status ON page_spell_issues (page_id, status);
