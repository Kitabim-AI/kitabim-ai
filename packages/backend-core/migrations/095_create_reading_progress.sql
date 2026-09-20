-- Migration 095: Add reading_progress table (silent per-user, per-book resume position)
CREATE TABLE IF NOT EXISTS reading_progress (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    book_id VARCHAR(64) NOT NULL REFERENCES books (id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_reading_progress_user_book UNIQUE (user_id, book_id)
);

CREATE INDEX IF NOT EXISTS idx_reading_progress_user_updated ON reading_progress (user_id, updated_at DESC);
