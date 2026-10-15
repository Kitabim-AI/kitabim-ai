-- Rollback Migration: 099_rollback_normalize_book_categories.sql
-- Description: Restore books.categories from the snapshot migration 099 took,
--   then drop the snapshot. Books created after 099 are not in the snapshot
--   and keep their current categories.
-- Author: Kitabim.AI
-- Date: 2026-10-14

BEGIN;

UPDATE books
SET categories = bk.categories
FROM books_categories_backup_099 bk
WHERE books.id = bk.book_id;

DROP TABLE books_categories_backup_099;

COMMIT;
