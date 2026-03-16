-- Migration: 033_reset_spell_check_for_new_logic.sql
-- Description: Reset spell check data and milestones to use new simplified logic
--
-- Changes:
--   1. Truncate page_spell_issues table (remove all existing issues)
--   2. Reset spell_check_milestone to 'idle' for all processed pages
--   3. Reset book-level spell_check milestones
--
-- Reason:
--   The spell check logic has been updated to only create issues for words
--   that have potential OCR corrections in the dictionary. The old logic also
--   flagged words unique to a book (which caused false positives). This reset
--   allows the new logic to reprocess all books with improved accuracy.
--
-- Impact:
--   - All existing spell check issues will be deleted
--   - All pages will be reprocessed for spell check
--   - Only genuine OCR errors with dictionary corrections will be flagged
--
-- Author: Omarjan
-- Date: 2025-03-16

BEGIN;

-- Show current state before migration
DO $$
DECLARE
    v_issues_count INTEGER;
    v_pages_done INTEGER;
    v_pages_failed INTEGER;
    v_books_succeeded INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_issues_count FROM page_spell_issues;
    SELECT COUNT(*) INTO v_pages_done FROM pages WHERE spell_check_milestone = 'done';
    SELECT COUNT(*) INTO v_pages_failed FROM pages WHERE spell_check_milestone = 'failed';
    SELECT COUNT(*) INTO v_books_succeeded FROM books WHERE spell_check_milestone = 'succeeded';

    RAISE NOTICE '';
    RAISE NOTICE '===========================================';
    RAISE NOTICE 'Migration 033: Reset Spell Check Data';
    RAISE NOTICE '===========================================';
    RAISE NOTICE 'Current state:';
    RAISE NOTICE '  - Spell check issues: %', v_issues_count;
    RAISE NOTICE '  - Pages done: %', v_pages_done;
    RAISE NOTICE '  - Pages failed: %', v_pages_failed;
    RAISE NOTICE '  - Books succeeded: %', v_books_succeeded;
    RAISE NOTICE '';
END $$;

-- Step 1: Truncate all spell check issues
TRUNCATE TABLE page_spell_issues;

-- Step 2: Reset spell_check_milestone to 'idle' for all pages that have been processed
--         This includes pages with 'done', 'failed', 'error', or 'in_progress' status
UPDATE pages
SET spell_check_milestone = 'idle',
    last_updated = NOW()
WHERE spell_check_milestone IN ('done', 'failed', 'error', 'in_progress');

-- Step 3: Reset book-level spell_check milestones to allow reprocessing
UPDATE books
SET spell_check_milestone = 'idle',
    last_updated = NOW()
WHERE spell_check_milestone IN ('succeeded', 'failed', 'in_progress', 'complete', 'done');

-- Show final state after migration
DO $$
DECLARE
    v_pages_reset INTEGER;
    v_books_reset INTEGER;
    v_issues_remaining INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_pages_reset FROM pages WHERE spell_check_milestone = 'idle';
    SELECT COUNT(*) INTO v_books_reset FROM books WHERE spell_check_milestone = 'idle';
    SELECT COUNT(*) INTO v_issues_remaining FROM page_spell_issues;

    RAISE NOTICE '===========================================';
    RAISE NOTICE 'Migration 033: Results';
    RAISE NOTICE '===========================================';
    RAISE NOTICE 'Reset complete:';
    RAISE NOTICE '  - Pages reset to idle: %', v_pages_reset;
    RAISE NOTICE '  - Books reset to idle: %', v_books_reset;
    RAISE NOTICE '  - Issues remaining: %', v_issues_remaining;
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  - Worker will automatically reprocess pages';
    RAISE NOTICE '  - Only words with OCR corrections will be flagged';
    RAISE NOTICE '  - Monitor progress in admin dashboard';
    RAISE NOTICE '===========================================';
    RAISE NOTICE '';
END $$;

COMMIT;
