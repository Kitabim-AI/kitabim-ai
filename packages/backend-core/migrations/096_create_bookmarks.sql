-- Migration 096: Add bookmarks table (named whole-page or passage bookmarks)
CREATE TABLE IF NOT EXISTS bookmarks (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    book_id VARCHAR(64) NOT NULL REFERENCES books (id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    quote_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_user_book ON bookmarks (user_id, book_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks (user_id);
