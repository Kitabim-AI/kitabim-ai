-- Migration: Add partial indexes for pipeline milestones
-- Description: Speeds up pipeline_driver and scanners by allowing index-backed lookups for idle/failed pages.

CREATE INDEX IF NOT EXISTS idx_pages_ocr_milestone_idle ON pages (ocr_milestone) WHERE ocr_milestone = 'idle';
CREATE INDEX IF NOT EXISTS idx_pages_ocr_milestone_failed ON pages (ocr_milestone) WHERE ocr_milestone IN ('failed', 'error');

CREATE INDEX IF NOT EXISTS idx_pages_chunking_milestone_idle ON pages (chunking_milestone) WHERE chunking_milestone = 'idle';
CREATE INDEX IF NOT EXISTS idx_pages_chunking_milestone_failed ON pages (chunking_milestone) WHERE chunking_milestone IN ('failed', 'error');

CREATE INDEX IF NOT EXISTS idx_pages_embedding_milestone_idle ON pages (embedding_milestone) WHERE embedding_milestone = 'idle';
CREATE INDEX IF NOT EXISTS idx_pages_embedding_milestone_failed ON pages (embedding_milestone) WHERE embedding_milestone IN ('failed', 'error');

CREATE INDEX IF NOT EXISTS idx_pages_spell_check_milestone_idle ON pages (spell_check_milestone) WHERE spell_check_milestone = 'idle';
CREATE INDEX IF NOT EXISTS idx_pages_spell_check_milestone_failed ON pages (spell_check_milestone) WHERE spell_check_milestone IN ('failed', 'error');

-- Index for pipeline_driver terminal book detection
CREATE INDEX IF NOT EXISTS idx_pages_book_id_terminal ON pages (book_id, embedding_milestone, retry_count);
