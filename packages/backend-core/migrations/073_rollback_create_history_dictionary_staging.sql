-- Migration Rollback: 073_rollback_create_history_dictionary_staging.sql
-- Description: Rollback history_dictionary_staging table and metadata columns
-- Author: Omarjan
-- Date: 2026-08-02

BEGIN;

DROP TABLE IF EXISTS public.history_dictionary_staging CASCADE;

ALTER TABLE public.history_dictionary
    DROP COLUMN IF EXISTS category,
    DROP COLUMN IF EXISTS significance_score,
    DROP COLUMN IF EXISTS is_ai_generated,
    DROP COLUMN IF EXISTS sources;

COMMIT;
