-- Migration 035_remove_word_index_logic.sql
-- This migration completely removes the word index functionality as it is no longer used
-- and causes performance issues on large datasets.

-- 1. Drop the word index related tables
DROP TABLE IF EXISTS book_word_index CASCADE;
DROP TABLE IF EXISTS words CASCADE;

-- 2. Remove word_index_milestone columns from books and pages
ALTER TABLE books DROP COLUMN IF EXISTS word_index_milestone;
ALTER TABLE pages DROP COLUMN IF EXISTS word_index_milestone;

-- 3. Update pipeline_step where it might be pointing to word_index
-- Move any book/page stuck at word_index to spell_check (the next step)
UPDATE books SET pipeline_step = 'spell_check' WHERE pipeline_step = 'word_index';
UPDATE pages SET pipeline_step = 'spell_check' WHERE pipeline_step = 'word_index';

-- Note: We keep the pipeline sequence logic in code to skip the word index step if it's missing.
