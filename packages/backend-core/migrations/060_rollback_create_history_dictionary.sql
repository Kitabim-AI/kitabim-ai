-- Rollback: 060_rollback_create_history_dictionary.sql
-- Description: Drop history_dictionary table and its indexes
-- Author: Omarjan
-- Date: 2026-06-26

BEGIN;

DROP TABLE IF EXISTS public.history_dictionary CASCADE;

COMMIT;
