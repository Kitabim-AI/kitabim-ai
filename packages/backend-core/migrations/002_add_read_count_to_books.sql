-- Migration: Add read_count column to books table
-- Created: 2026-02-26
-- Description: Tracks how many times a book has been opened by users
--              Incremented asynchronously via BackgroundTask when GET /api/books/{id} is called

ALTER TABLE books
    ADD COLUMN IF NOT EXISTS read_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_books_read_count ON books(read_count DESC);
