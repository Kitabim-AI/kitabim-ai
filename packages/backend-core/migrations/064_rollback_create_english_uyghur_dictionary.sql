-- Rollback: 064_rollback_create_english_uyghur_dictionary.sql
-- Description: Drop english_uyghur_dictionary table
-- Author: Omarjan
-- Date: 2026-06-26

BEGIN;

DROP TABLE IF EXISTS public.english_uyghur_dictionary CASCADE;

COMMIT;
