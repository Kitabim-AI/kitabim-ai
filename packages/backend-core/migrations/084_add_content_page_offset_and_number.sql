-- Migration: 084_add_content_page_offset_and_number.sql
-- Description: Add content_page_offset to books table and content_page_number to pages table
-- Author: Kitabim.AI
-- Date: 2026-08-08

BEGIN;

ALTER TABLE public.books
    ADD COLUMN IF NOT EXISTS content_page_offset INT NOT NULL DEFAULT 0;

ALTER TABLE public.pages
    ADD COLUMN IF NOT EXISTS content_page_number VARCHAR(20) NULL;

COMMIT;
