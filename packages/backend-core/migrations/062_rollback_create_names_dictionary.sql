-- Rollback: 062_rollback_create_names_dictionary.sql
-- Description: Drop names_dictionary table

BEGIN;
DROP TABLE IF EXISTS public.names_dictionary;
COMMIT;
