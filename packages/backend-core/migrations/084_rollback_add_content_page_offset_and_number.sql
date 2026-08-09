-- Migration Rollback: 084_rollback_add_content_page_offset_and_number.sql
-- Description: Rollback adding content_page_offset to books and content_page_number to pages

BEGIN;

ALTER TABLE public.books
    DROP COLUMN IF EXISTS content_page_offset;

ALTER TABLE public.pages
    DROP COLUMN IF EXISTS content_page_number;

COMMIT;
