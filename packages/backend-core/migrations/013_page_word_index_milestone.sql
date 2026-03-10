-- Migration 013: Per-page word index milestone tracking.
--
-- Adds word_index_milestone to pages so the word_index_scanner can track
-- progress page-by-page and gracefully handle failures / interruptions.
--
-- Values: 'idle' (not yet processed), 'done' (indexed), 'error' (failed).
--
-- Backfill: any page whose book already has rows in book_word_index was
-- fully indexed under the old all-or-nothing scheme, so mark it 'done'.

ALTER TABLE pages
    ADD COLUMN IF NOT EXISTS word_index_milestone VARCHAR(20)
        NOT NULL DEFAULT 'idle';

-- Backfill already-indexed books so the scanner skips their pages.
UPDATE pages
SET word_index_milestone = 'done'
WHERE book_id IN (SELECT DISTINCT book_id FROM book_word_index);

CREATE INDEX IF NOT EXISTS idx_pages_word_index_milestone
    ON pages (word_index_milestone)
    WHERE word_index_milestone = 'idle';
