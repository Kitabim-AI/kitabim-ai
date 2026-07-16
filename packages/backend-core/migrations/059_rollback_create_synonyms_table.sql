-- Rollback: 059_rollback_create_synonyms_table.sql
-- Description: Drop synonyms table

BEGIN;

DROP TABLE IF EXISTS public.synonyms;

COMMIT;
