-- Migration: Remove 'uploading' from books status constraint
-- Created: 2026-02-27
-- Description: 'uploading' status was never used by any code path. Removing it
--              to keep the constraint accurate and avoid confusion.

ALTER TABLE books DROP CONSTRAINT IF EXISTS books_status_check;

ALTER TABLE books
    ADD CONSTRAINT books_status_check
    CHECK (status IN ('pending', 'ocr_processing', 'ocr_done', 'indexing', 'ready', 'error'));
