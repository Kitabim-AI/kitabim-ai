-- Migration: Add additional performance indexes for spell check optimization
-- Description: Creates indexes to optimize spell check scanner queries and retry count checks

-- Index for retry count filtering in pipeline driver
-- Speeds up queries looking for pages with retries remaining
CREATE INDEX IF NOT EXISTS idx_pages_retry_count_low
ON pages (retry_count)
WHERE retry_count < 3;

-- Index for spell check scanner to find incomplete pages
-- Useful if spell_check_scanner queries for pages where spell_check_milestone != 'done'
CREATE INDEX IF NOT EXISTS idx_pages_spell_check_milestone_incomplete
ON pages (spell_check_milestone)
WHERE spell_check_milestone IN ('idle', 'in_progress', 'failed', 'error');

-- Composite index for spell check scanner dependency checks
-- Speeds up queries that look for pages ready for spell check after word indexing
CREATE INDEX IF NOT EXISTS idx_pages_word_index_spell_check_ready
ON pages (word_index_milestone, spell_check_milestone)
WHERE word_index_milestone = 'done' AND spell_check_milestone = 'idle';
