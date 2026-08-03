-- Migration Rollback: 080_rollback_add_history_facts.sql
-- Description: Revert 080_add_history_facts.sql. Cannot restore data the
--   forward migration dropped (original `sources` for staging rows, deleted
--   pending staging rows) — matches the existing lossy-rollback precedent in
--   079_rollback_create_history_dictionary_staging.sql.
-- Author: Omarjan
-- Date: 2026-08-02

BEGIN;

ALTER TABLE public.history_dictionary
    ADD COLUMN IF NOT EXISTS sources JSONB DEFAULT '[]'::jsonb,
    DROP COLUMN IF EXISTS facts;

ALTER TABLE public.history_dictionary_staging
    ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    DROP COLUMN IF EXISTS facts,
    ALTER COLUMN definition SET NOT NULL;

COMMIT;
