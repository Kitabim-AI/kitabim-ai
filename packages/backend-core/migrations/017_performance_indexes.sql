-- Migration: Add performance indexes for book listing and grouping
-- Created: 2026-03-13
-- Description: Adds indexes to speed up groupByWork queries and category filtering.

-- Index for DISTINCT ON (title, author, volume) and Window Function MAX(upload_date) PARTITION BY (title, author)
CREATE INDEX IF NOT EXISTS idx_books_group_sort 
ON books (title, author, volume, upload_date DESC);

-- GIN index for faster category filtering
CREATE INDEX IF NOT EXISTS idx_books_categories_gin 
ON books USING GIN (categories);

-- Index for searching and sorting by status and visibility (often used together)
CREATE INDEX IF NOT EXISTS idx_books_status_visibility_date 
ON books (status, visibility, upload_date DESC);

-- Trigram indexes for fast case-insensitive search (ILIKE and regex)
CREATE INDEX IF NOT EXISTS idx_books_title_trgm ON books USING GIN (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_books_author_trgm ON books USING GIN (author gin_trgm_ops);
