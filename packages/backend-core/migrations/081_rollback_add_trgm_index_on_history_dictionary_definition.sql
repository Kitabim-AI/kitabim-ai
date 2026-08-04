-- Rollback Migration: 081_rollback_add_trgm_index_on_history_dictionary_definition.sql
-- Description: Drop GIN trigram index on history_dictionary definition column
-- Author: Omarjan
-- Date: 2026-08-04

BEGIN;

DROP INDEX IF EXISTS public.idx_history_dictionary_def_trgm;

COMMIT;
