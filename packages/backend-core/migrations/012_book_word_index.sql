-- Migration 012: Book-level word occurrence index for cross-book spell check lookups.
--
-- Population is handled by the word_index_scanner cron job (one book per minute),
-- which indexes all existing and new books incrementally without large bulk scans.

CREATE TABLE IF NOT EXISTS book_word_index (
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    word    TEXT NOT NULL,
    PRIMARY KEY (book_id, word)
);

-- Enables efficient "which other books contain this word?" lookups.
CREATE INDEX IF NOT EXISTS idx_book_word_index_word ON book_word_index(word, book_id);
