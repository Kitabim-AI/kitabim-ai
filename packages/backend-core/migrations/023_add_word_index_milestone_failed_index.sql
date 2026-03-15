-- Migration: Add missing failure index for word_index_milestone
-- Description: Completes the set of failure indexes to ensure all pipeline driver reset conditions are index-backed.

CREATE INDEX IF NOT EXISTS idx_pages_word_index_milestone_failed ON pages (word_index_milestone) WHERE word_index_milestone IN ('failed', 'error');
