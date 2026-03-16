-- Rollback Migration: 033_rollback_reset_spell_check_for_new_logic.sql
-- Description: Rollback the spell check reset (NOTE: This cannot restore deleted issues)
--
-- WARNING:
--   This rollback CANNOT restore the deleted spell check issues.
--   It can only prevent the reset from happening if run before migration 033.
--   If you've already run migration 033, the only way to get issues back is
--   to let the worker reprocess the pages (which is the intended behavior).
--
-- What this rollback does:
--   - Nothing, as the reset is intentional and irreversible
--   - The data deletion is the desired state
--
-- To truly "rollback" after running migration 033:
--   - Let the worker reprocess with the OLD logic (not recommended)
--   - OR restore from a database backup (if available)
--   - OR accept the new state and let worker reprocess with NEW logic (recommended)
--
-- Author: Omarjan
-- Date: 2025-03-16

BEGIN;

RAISE NOTICE '';
RAISE NOTICE '===========================================';
RAISE NOTICE 'Rollback Migration 033: Not Applicable';
RAISE NOTICE '===========================================';
RAISE NOTICE '';
RAISE NOTICE 'This migration reset spell check data intentionally.';
RAISE NOTICE 'The deleted data cannot be automatically restored.';
RAISE NOTICE '';
RAISE NOTICE 'If you need to restore the previous state:';
RAISE NOTICE '  1. Restore from a database backup (if available)';
RAISE NOTICE '  2. Let the worker reprocess pages (recommended)';
RAISE NOTICE '';
RAISE NOTICE 'Current state:';

-- Show current counts
DO $$
DECLARE
    v_pages_idle INTEGER;
    v_books_idle INTEGER;
    v_issues_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_pages_idle FROM pages WHERE spell_check_milestone = 'idle';
    SELECT COUNT(*) INTO v_books_idle FROM books WHERE spell_check_milestone = 'idle';
    SELECT COUNT(*) INTO v_issues_count FROM page_spell_issues;

    RAISE NOTICE '  - Pages in idle state: %', v_pages_idle;
    RAISE NOTICE '  - Books in idle state: %', v_books_idle;
    RAISE NOTICE '  - Spell check issues: %', v_issues_count;
END $$;

RAISE NOTICE '';
RAISE NOTICE 'No rollback action performed.';
RAISE NOTICE '===========================================';
RAISE NOTICE '';

COMMIT;
