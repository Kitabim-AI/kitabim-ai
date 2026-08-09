-- Migration Rollback: 086_rollback_add_aliases_to_history_dictionary.sql
-- Description: Drop aliases column from history_dictionary and history_dictionary_staging tables

ALTER TABLE public.history_dictionary DROP COLUMN IF EXISTS aliases;
ALTER TABLE public.history_dictionary_staging DROP COLUMN IF EXISTS aliases;
