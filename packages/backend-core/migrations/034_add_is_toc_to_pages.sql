-- Migration: 034_add_is_toc_to_pages.sql
-- Description: Add is_toc column to identify table of contents pages
-- Author: Antigravity
-- Date: 2026-03-20

BEGIN;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='pages' AND column_name='is_toc') THEN
        ALTER TABLE pages ADD COLUMN is_toc BOOLEAN DEFAULT FALSE NOT NULL;
    END IF;
END $$;

COMMIT;
