-- Rollback: 067_rollback_create_quran_table.sql
-- Description: Drop quran table
-- Author: Omarjan
-- Date: 2026-07-05

BEGIN;
DROP TABLE IF EXISTS public.quran CASCADE;
COMMIT;
